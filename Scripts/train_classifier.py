"""
Train bolt-localization classifiers from a feature matrix (.npz).

Fully generalized — derives all class counts, feature counts, label
mappings, and CV strategy from the data.  Works with any beam model,
any number of bolts, any number of severity levels.

Pipeline order (critical — do not rearrange):
  1. StandardScaler   — PCA is sensitive to feature scale
  2. PCA (95% var)    — reduces curse-of-dimensionality before SMOTE
  3. SMOTE            — synthetic oversampling in PCA space (train folds only)
  4. RF + XGB + GB    — ensemble training with try-except per model

Usage:
    python Scripts/train_classifier.py --input D:\\thesis_database\\training_matrix.npz
    python Scripts/train_classifier.py --input data.npz --model-output model.pkl --report report.txt
"""
import argparse
import os
import sys
import textwrap
import time
import traceback

# Force unbuffered output so progress is visible in real-time (logs, MCP, CI)
os.environ["PYTHONUNBUFFERED"] = "1"
from pathlib import Path

import joblib
import numpy as np
from sklearn.decomposition import PCA                          # Task 1b
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import LabelEncoder, StandardScaler

# --- Optional dependencies (graceful fallback) ---
try:
    from xgboost import XGBClassifier                          # Task 1c
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from imblearn.over_sampling import SMOTE                   # Task 1d
    _HAS_SMOTE = True
except ImportError:
    _HAS_SMOTE = False


# ---------------------------------------------------------------------------
# Data loading — everything derived from the .npz file
# ---------------------------------------------------------------------------
def load_data(npz_path: str) -> dict:
    """Load training matrix and print a diagnostic summary."""
    data = np.load(npz_path, allow_pickle=True)
    X = data["X"]
    y_bolt = data["y_bolt"]
    y_severity = data["y_severity"]
    y_binary = data["y_binary"]
    feature_names = data["feature_names"]

    print("=" * 60)
    print("DATA INSPECTION")
    print("=" * 60)
    print(f"  X shape        : {X.shape}")
    print(f"  Features       : {len(feature_names)}")
    print(f"  Samples        : {X.shape[0]}")

    print(f"\n  y_bolt classes ({len(np.unique(y_bolt))}):")
    for cls in sorted(np.unique(y_bolt)):
        n = (y_bolt == cls).sum()
        print(f"    element {cls}: {n} samples ({100*n/len(y_bolt):.1f}%)")

    print(f"\n  y_binary classes ({len(np.unique(y_binary))}):")
    for cls in sorted(np.unique(y_binary)):
        label = "healthy" if cls == 0 else "loosened"
        n = (y_binary == cls).sum()
        print(f"    {cls} ({label}): {n} samples ({100*n/len(y_binary):.1f}%)")

    print(f"\n  y_severity classes ({len(np.unique(y_severity))}):")
    for cls in sorted(np.unique(y_severity)):
        n = (y_severity == cls).sum()
        print(f"    severity {cls}: {n} samples ({100*n/len(y_severity):.1f}%)")

    return {
        "X": X,
        "y_bolt": y_bolt,
        "y_severity": y_severity,
        "y_binary": y_binary,
        "feature_names": feature_names,
    }


# ---------------------------------------------------------------------------
# CV fold selection — adapts to the smallest class
# ---------------------------------------------------------------------------
def _choose_k(y: np.ndarray, max_k: int = 5) -> int:
    """Return the largest k <= max_k for eligible classes (>= MIN_SAMPLES).

    Classes with fewer than MIN_SAMPLES are excluded from controlling
    CV fold count — they still participate in training.  Prevents a
    tiny class (e.g. healthy baseline before Study E) from forcing
    2-fold CV for the entire dataset.  Auto-includes when class grows
    past threshold (e.g. after Study E import — no code change needed).
    """
    MIN_SAMPLES = 6
    _, counts = np.unique(y, return_counts=True)
    eligible = counts[counts >= MIN_SAMPLES]
    if len(eligible) == 0:
        return 2
    k = min(max_k, int(eligible.min()))
    return max(k, 2)


# ---------------------------------------------------------------------------
# Training + evaluation
# ---------------------------------------------------------------------------
def train_and_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: np.ndarray,
    label_prefix: str = "element",
    model_dir: str = None,
) -> dict:
    """
    Train RF and XGBoost with stratified k-fold CV.

    Pipeline order (critical — do not rearrange):
      StandardScaler → PCA → SMOTE (train folds only) → classifiers

    Returns dict with best model, reports, confusion matrices, importances,
    plus saved artifacts: standard_scaler.pkl, pca_transform.pkl, feature_names.pkl
    """
    k = _choose_k(y)
    classes = sorted(np.unique(y))
    target_names = [f"{label_prefix}_{c}" for c in classes]

    print(f"\n{'=' * 60}")
    print(f"TRAINING — {len(classes)} classes, {k}-fold stratified CV")
    print(f"{'=' * 60}")

    # ── Task 1a: StandardScaler ──────────────────────────────────────────
    # PCA is sensitive to feature scale — unscaled features with large
    # magnitude dominate principal components regardless of variance.
    scaler = StandardScaler()
    X_scaled = np.ascontiguousarray(scaler.fit_transform(X), dtype=np.float64)
    y = np.asarray(y, dtype=np.intp)  # native int for sklearn
    print(f"  StandardScaler: {X.shape[1]} features, mean~0 std~1")

    # ── Task 1b: PCA — dimensionality reduction ─────────────────────────
    # Reduces 2,347 features to ~100 components retaining 95% variance.
    # Fixes: CRASH (smaller matrix avoids sklearn Cython SIGILL),
    #        RATIO (sample:feature from 0.65:1 to ~15:1),
    #        SCALE (mandatory at spacecraft's ~98,000 features)
    pca = PCA(n_components=0.95, random_state=42)
    X_pca = pca.fit_transform(X_scaled)
    n_orig = X_scaled.shape[1]
    n_pca = X_pca.shape[1]
    var_kept = pca.explained_variance_ratio_.sum()
    ratio = X_pca.shape[0] / X_pca.shape[1]
    print(f"  PCA: {n_orig} features -> {n_pca} components "
          f"({var_kept:.1%} variance retained)")
    print(f"  Sample:feature ratio: {ratio:.1f}:1 "
          f"(was {X_scaled.shape[0]/n_orig:.2f}:1)")

    # ── Save artifacts (Task 1a, 1b, 1f) ────────────────────────────────
    if model_dir:
        scaler_path = os.path.join(model_dir, "standard_scaler.pkl")
        pca_path = os.path.join(model_dir, "pca_transform.pkl")
        fnames_path = os.path.join(model_dir, "feature_names.pkl")
        joblib.dump(scaler, scaler_path)
        joblib.dump(pca, pca_path)
        joblib.dump(list(feature_names), fnames_path)
        print(f"  Saved: {scaler_path}")
        print(f"  Saved: {pca_path}")
        print(f"  Saved: {fnames_path}")

    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)

    # ── Task 1c: Model definitions ──────────────────────────────────────
    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
    }

    if _HAS_XGB:
        models["XGBoost"] = XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
            eval_metric="mlogloss",
            verbosity=0,
        )
    else:
        print("  WARNING: xgboost not installed — skipping XGBClassifier")


    # ── SMOTE status message (Task 1d) ──────────────────────────────────
    if _HAS_SMOTE:
        print(f"  SMOTE: available (imbalanced-learn)")
    else:
        print(f"  SMOTE: NOT available — using class_weight fallback only")

    results = {}
    for name, model in models.items():
        print(f"\n--- {name} ---", flush=True)
        t0 = time.time()

        # ── Task 1e: try-except around entire model training ────────────
        try:
            # Manual fold loop with progress reporting
            y_pred = np.full_like(y, fill_value=-1)
            fold_accs = []
            for fold_i, (train_idx, test_idx) in enumerate(cv.split(X_pca, y), 1):
                fold_t0 = time.time()

                X_train_fold = X_pca[train_idx]
                y_train_fold = y[train_idx]

                # ── Task 1d: SMOTE on training fold only ────────────────
                # SMOTE goes AFTER PCA, never before.
                # In 2,347-d space all points are ~equidistant (curse of
                # dimensionality) — nearest-neighbor interpolation is
                # meaningless. In ~100 PCA dimensions, neighbors are
                # genuine and interpolation produces valid synthetic samples.
                # SMOTE NEVER touches the test fold — that would be data leakage.
                smote_applied = False
                if _HAS_SMOTE:
                    MIN_SMOTE = 6
                    vals, counts = np.unique(y_train_fold, return_counts=True)
                    eligible_mask = counts >= MIN_SMOTE
                    if eligible_mask.any():
                        target = int(counts[eligible_mask].max())
                        strategy = {
                            int(cls): target
                            for cls, cnt in zip(vals, counts)
                            if cnt >= MIN_SMOTE and cnt < target
                        }
                        if strategy:
                            k_neighbors = min(5, int(counts[eligible_mask].min()) - 1)
                            sm = SMOTE(random_state=42, k_neighbors=k_neighbors,
                                       sampling_strategy=strategy)
                            X_train_fold, y_train_fold = sm.fit_resample(
                                X_train_fold, y_train_fold)
                            smote_applied = True

                print(f"  Fold {fold_i}/{k}: train={len(X_train_fold)}"
                      f"{'(SMOTE)' if smote_applied else ''}, "
                      f"test={len(test_idx)} ...", end="", flush=True)

                clone = type(model)(**model.get_params())
                # XGBoost requires contiguous 0-indexed labels
                if name == "XGBoost":
                    le = LabelEncoder()
                    y_fit = le.fit_transform(y_train_fold)
                    clone.fit(X_train_fold, y_fit)
                    y_pred[test_idx] = le.inverse_transform(
                        clone.predict(X_pca[test_idx]))
                else:
                    clone.fit(X_train_fold, y_train_fold)
                    y_pred[test_idx] = clone.predict(X_pca[test_idx])
                fold_acc = (y_pred[test_idx] == y[test_idx]).mean()
                fold_accs.append(fold_acc)
                fold_elapsed = time.time() - fold_t0
                print(f" acc={fold_acc:.4f} ({fold_elapsed:.1f}s)", flush=True)

            elapsed = time.time() - t0
            mean_acc = np.mean(fold_accs)
            std_acc = np.std(fold_accs)

            print(f"  CV accuracy: {mean_acc:.4f} +/- {std_acc:.4f}  ({elapsed:.1f}s)")

            # Train accuracy (detect overfitting)
            model_full = type(model)(**model.get_params())

            # SMOTE on full training data for final model
            X_train_final, y_train_final = X_pca, y
            if _HAS_SMOTE:
                MIN_SMOTE = 6
                vals, counts = np.unique(y, return_counts=True)
                eligible_mask = counts >= MIN_SMOTE
                if eligible_mask.any():
                    target = int(counts[eligible_mask].max())
                    strategy = {
                        int(cls): target
                        for cls, cnt in zip(vals, counts)
                        if cnt >= MIN_SMOTE and cnt < target
                    }
                    if strategy:
                        k_neighbors = min(5, int(counts[eligible_mask].min()) - 1)
                        sm = SMOTE(random_state=42, k_neighbors=k_neighbors,
                                   sampling_strategy=strategy)
                        X_train_final, y_train_final = sm.fit_resample(X_pca, y)
                        print(f"  SMOTE (full data): {len(y)} -> {len(y_train_final)} samples")

            # XGBoost requires contiguous 0-indexed labels
            if name == "XGBoost":
                le_full = LabelEncoder()
                y_fit_full = le_full.fit_transform(y_train_final)
                model_full.fit(X_train_final, y_fit_full)
                train_acc = (le_full.inverse_transform(
                    model_full.predict(X_pca)) == y).mean()
                if model_dir:
                    le_path = os.path.join(model_dir, "label_encoder.pkl")
                    joblib.dump(le_full, le_path)
                    print(f"  Saved: {le_path}")
            else:
                model_full.fit(X_train_final, y_train_final)
                train_acc = (model_full.predict(X_pca) == y).mean()
            overfit_gap = train_acc - mean_acc
            print(f"  Train accuracy: {train_acc:.4f}  "
                  f"(overfit gap: {overfit_gap:+.4f})")

            # Classification report
            report = classification_report(
                y, y_pred, target_names=target_names, zero_division=0
            )
            print(f"\n  Classification Report:\n")
            for line in report.strip().split("\n"):
                print(f"    {line}")

            # Confusion matrix
            cm = confusion_matrix(y, y_pred, labels=classes)
            print(f"\n  Confusion Matrix (rows=true, cols=pred):")
            header = "        " + "".join(f"{c:>7}" for c in classes)
            print(f"    {header}")
            for i, cls in enumerate(classes):
                row_str = "".join(f"{cm[i, j]:>7}" for j in range(len(classes)))
                print(f"    {cls:>6}: {row_str}")

            # Feature importance (in PCA space)
            importances = model_full.feature_importances_
            top_idx = np.argsort(importances)[::-1][:20]
            print(f"\n  Top 20 PCA components by importance:")
            for rank, fi in enumerate(top_idx, 1):
                print(f"    {rank:>2}. PC{fi:<4d} {importances[fi]:.6f}")

            results[name] = {
                "model": model_full,
                "scaler": scaler,
                "pca": pca,
                "mean_acc": mean_acc,
                "std_acc": std_acc,
                "train_acc": train_acc,
                "overfit_gap": overfit_gap,
                "report": report,
                "confusion_matrix": cm,
                "importances": importances,
                "y_pred": y_pred,
            }

        except Exception as exc:
            # ── Task 1e: no single classifier crash kills the pipeline ──
            elapsed = time.time() - t0
            print(f"\n  *** {name} CRASHED after {elapsed:.1f}s ***")
            print(f"  Error: {exc}")
            traceback.print_exc()
            print(f"  Continuing with remaining classifiers...\n")

    if not results:
        print("\n*** ALL CLASSIFIERS CRASHED — no model saved ***")
        sys.exit(1)

    return results, classes, target_names


# ---------------------------------------------------------------------------
# Save outputs
# ---------------------------------------------------------------------------
def save_outputs(
    results: dict,
    classes: list,
    target_names: list,
    y: np.ndarray,
    feature_names: np.ndarray,
    model_output: str,
    report_output: str,
):
    """Save the best model (.pkl) and classification report (.txt)."""

    # Pick best model by CV accuracy
    best_name = max(results, key=lambda n: results[n]["mean_acc"])
    best = results[best_name]
    print(f"\nBest model: {best_name} "
          f"(accuracy={best['mean_acc']:.4f} +/- {best['std_acc']:.4f})")

    # Save model bundle (includes PCA reference for predict.py)
    bundle = {
        "model": best["model"],
        "scaler": best["scaler"],
        "pca": best["pca"],
        "model_name": best_name,
        "classes": classes,
        "target_names": target_names,
        "feature_names": list(feature_names),
        "mean_accuracy": best["mean_acc"],
        "std_accuracy": best["std_acc"],
        "train_accuracy": best["train_acc"],
        "overfit_gap": best["overfit_gap"],
        "n_pca_components": best["pca"].n_components_,
        "pca_variance_retained": best["pca"].explained_variance_ratio_.sum(),
        "smote_available": _HAS_SMOTE,
        "xgboost_available": _HAS_XGB,
    }
    joblib.dump(bundle, model_output)
    print(f"  Saved model: {model_output}")

    # Save report
    lines = []
    lines.append("BOLT LOCALIZATION — CLASSIFICATION REPORT")
    lines.append("=" * 60)
    lines.append(f"Samples: {len(y)}")
    lines.append(f"Raw features: {len(feature_names)}")
    lines.append(f"PCA components: {best['pca'].n_components_} "
                 f"({best['pca'].explained_variance_ratio_.sum():.1%} variance)")
    lines.append(f"Sample:feature ratio: "
                 f"{len(y)/best['pca'].n_components_:.1f}:1")
    lines.append(f"Classes: {len(classes)} — {classes}")
    lines.append(f"SMOTE: {'available' if _HAS_SMOTE else 'NOT available'}")
    lines.append(f"XGBoost: {'available' if _HAS_XGB else 'NOT available'}")
    lines.append("")

    for name, res in results.items():
        lines.append(f"{'=' * 60}")
        lines.append(f"MODEL: {name}")
        lines.append(f"{'=' * 60}")
        lines.append(f"CV accuracy:    {res['mean_acc']:.4f} +/- {res['std_acc']:.4f}")
        lines.append(f"Train accuracy: {res['train_acc']:.4f}")
        lines.append(f"Overfit gap:    {res['overfit_gap']:+.4f}")
        lines.append("")
        lines.append("Classification Report:")
        lines.append(res["report"])
        lines.append("")
        lines.append("Confusion Matrix (rows=true, cols=pred):")
        header = "        " + "".join(f"{c:>7}" for c in classes)
        lines.append(header)
        cm = res["confusion_matrix"]
        for i, cls in enumerate(classes):
            row_str = "".join(f"{cm[i, j]:>7}" for j in range(len(classes)))
            lines.append(f"{cls:>6}: {row_str}")
        lines.append("")

        top_idx = np.argsort(res["importances"])[::-1][:20]
        lines.append("Top 20 PCA components by importance:")
        for rank, fi in enumerate(top_idx, 1):
            lines.append(
                f"  {rank:>2}. PC{fi:<4d} "
                f"{res['importances'][fi]:.6f}"
            )
        lines.append("")

    lines.append(f"\nBest model: {best_name}")
    lines.append(f"Saved to: {model_output}")

    report_text = "\n".join(lines)
    Path(report_output).write_text(report_text, encoding="utf-8")
    print(f"  Saved report: {report_output}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Train bolt-localization classifiers (generalized)"
    )
    parser.add_argument(
        "--input",
        default=r"D:\thesis_database\training_matrix.npz",
        help="Path to training_matrix.npz",
    )
    parser.add_argument(
        "--model-output",
        default=r"D:\thesis_database\bolt_classifier.pkl",
        help="Path to save best model (.pkl)",
    )
    parser.add_argument(
        "--report",
        default=r"D:\thesis_database\classification_report.txt",
        help="Path to save classification report (.txt)",
    )
    args = parser.parse_args()

    # Model directory = same directory as model output
    model_dir = str(Path(args.model_output).parent)

    # Load
    bundle = load_data(args.input)
    X = bundle["X"]
    y = bundle["y_bolt"]
    feature_names = bundle["feature_names"]

    # Train (with PCA + SMOTE + XGBoost + try-except)
    results, classes, target_names = train_and_evaluate(
        X, y, feature_names, label_prefix="element",
        model_dir=model_dir,
    )

    # Save
    save_outputs(
        results, classes, target_names, y,
        feature_names, args.model_output, args.report,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
