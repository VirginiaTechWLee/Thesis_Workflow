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
    from sklearn.ensemble import IsolationForest
    _HAS_ISOFOREST = True
except ImportError:
    _HAS_ISOFOREST = False

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

    # Study IDs for IsolationForest (identifies Study E healthy rows)
    study_ids = data["study_ids"] if "study_ids" in data.files else None
    if study_ids is not None:
        unique_sids = np.unique(study_ids)
        print(f"\n  study_ids: {len(unique_sids)} studies {unique_sids.tolist()}")
    else:
        print(f"\n  study_ids: not in npz (IsolationForest will use y==0 fallback)")

    return {
        "X": X,
        "y_bolt": y_bolt,
        "y_severity": y_severity,
        "y_binary": y_binary,
        "feature_names": feature_names,
        "study_ids": study_ids,
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
def _load_pca_threshold() -> float:
    """Read PCA variance threshold from config.yaml. Falls back to 0.95."""
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "fem_input", "config.yaml"
        )
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        thresh = float(cfg.get("pca", {}).get("variance_threshold", 0.95))
        if not 0.5 <= thresh <= 1.0:
            print(f"  WARNING: pca.variance_threshold={thresh} out of range, using 0.95")
            return 0.95
        return thresh
    except Exception:
        return 0.95


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
    pca_threshold = _load_pca_threshold()
    pca = PCA(n_components=pca_threshold, random_state=42)
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
# Lever 4 — Hierarchical binary classifiers (one per bolt)
# ---------------------------------------------------------------------------
def train_binary_classifiers(
    X_pca: np.ndarray,
    y: np.ndarray,
    bolt_ids: np.ndarray = None,
    model_dir: str = None,
) -> dict:
    """
    Train one binary classifier per bolt: "is bolt N loose? yes/no."

    At inference time, run all models and pick the bolt with the highest
    P(loose) score. If no bolt exceeds HEALTHY_THRESHOLD, predict healthy.

    Args:
        X_pca: PCA-transformed feature matrix
        y: bolt labels (0=healthy, N=bolt N loosest)
        bolt_ids: array of bolt IDs to train on (default: unique non-zero in y)
        model_dir: directory to save binary_classifiers.pkl

    Returns:
        dict with per-bolt models, metrics, and ensemble accuracy
    """
    from sklearn.metrics import precision_score, recall_score, f1_score

    print("\n" + "=" * 60)
    print("LEVER 4 -- BINARY CLASSIFIERS (one per bolt)")
    print("=" * 60)

    if bolt_ids is None:
        bolt_ids = sorted(np.unique(y[y != 0]))
    print(f"  Bolts: {bolt_ids}")
    print(f"  Samples: {len(y)} ({(y == 0).sum()} healthy, {(y != 0).sum()} faulty)")

    # CV setup — same as main classifier
    k = _choose_k(y)
    skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)
    print(f"  CV folds: {k}")

    HEALTHY_THRESHOLD = 0.5
    bolt_results = {}

    for bolt in bolt_ids:
        t0 = time.time()
        y_bin = (y == bolt).astype(int)  # 1 = this bolt, 0 = everything else
        n_pos = y_bin.sum()
        n_neg = (y_bin == 0).sum()

        print(f"\n  Bolt {bolt}: {n_pos} positive, {n_neg} negative")

        if n_pos < 2:
            print(f"    SKIP — only {n_pos} positive samples")
            continue

        # Choose model — XGBoost if available, else RF
        if _HAS_XGB:
            model = XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                use_label_encoder=False,
                eval_metric="logloss",
            )
            model_name = "XGBoost"
        else:
            model = RandomForestClassifier(
                n_estimators=200,
                max_depth=None,
                random_state=42,
                n_jobs=-1,
            )
            model_name = "RF"

        try:
            # Cross-validated predictions
            y_pred = cross_val_predict(model, X_pca, y_bin, cv=skf)

            precision = precision_score(y_bin, y_pred, zero_division=0)
            recall = recall_score(y_bin, y_pred, zero_division=0)
            f1 = f1_score(y_bin, y_pred, zero_division=0)
            accuracy = (y_pred == y_bin).mean()

            # SMOTE for final model training
            X_train_final, y_train_final = X_pca, y_bin
            if _HAS_SMOTE and n_pos >= 6:
                target_count = max(n_pos, n_neg)
                strategy = {}
                if n_pos < target_count:
                    strategy[1] = target_count
                if n_neg < target_count:
                    strategy[0] = target_count
                if strategy:
                    k_neighbors = min(5, n_pos - 1)
                    sm = SMOTE(random_state=42, k_neighbors=k_neighbors,
                               sampling_strategy=strategy)
                    X_train_final, y_train_final = sm.fit_resample(X_pca, y_bin)

            # Train final model
            model_full = type(model)(**model.get_params())
            model_full.fit(X_train_final, y_train_final)

            elapsed = time.time() - t0
            print(f"    {model_name}: P={precision:.3f}  R={recall:.3f}  "
                  f"F1={f1:.3f}  acc={accuracy:.3f}  ({elapsed:.1f}s)")

            bolt_results[int(bolt)] = {
                "model": model_full,
                "model_name": model_name,
                "precision_cv": precision,
                "recall_cv": recall,
                "f1_cv": f1,
                "accuracy_cv": accuracy,
                "n_positive": int(n_pos),
                "n_negative": int(n_neg),
            }

        except Exception as exc:
            elapsed = time.time() - t0
            print(f"    *** CRASHED after {elapsed:.1f}s: {exc} ***")
            traceback.print_exc()

    if not bolt_results:
        print("\n  *** ALL BINARY CLASSIFIERS FAILED ***")
        return None

    # --- Ensemble accuracy on full dataset ---
    # Simulate inference: each bolt model scores every sample,
    # pick the bolt with highest P(loose), apply threshold
    print(f"\n  {'=' * 50}")
    print(f"  BINARY ENSEMBLE EVALUATION")
    print(f"  {'=' * 50}")

    ensemble_preds = np.zeros(len(y), dtype=int)
    ensemble_conf = np.zeros(len(y), dtype=float)

    for i in range(len(y)):
        scores = {}
        for bolt, res in bolt_results.items():
            proba = res["model"].predict_proba(X_pca[i:i+1])[0]
            # proba = [P(not loose), P(loose)]
            scores[bolt] = proba[1] if len(proba) > 1 else proba[0]

        best_bolt = max(scores, key=scores.get)
        best_confidence = scores[best_bolt]

        if best_confidence < HEALTHY_THRESHOLD:
            ensemble_preds[i] = 0  # healthy
            ensemble_conf[i] = 1 - best_confidence
        else:
            ensemble_preds[i] = best_bolt
            ensemble_conf[i] = best_confidence

    ensemble_acc = (ensemble_preds == y).mean()
    # Per-class breakdown
    for cls in sorted(np.unique(y)):
        mask = y == cls
        cls_acc = (ensemble_preds[mask] == cls).mean()
        label = "healthy" if cls == 0 else f"bolt {cls}"
        print(f"    {label:>10s}: {cls_acc:.1%} "
              f"({(ensemble_preds[mask] == cls).sum()}/{mask.sum()})")

    print(f"\n    Ensemble accuracy: {ensemble_acc:.4f}")
    print(f"    Healthy threshold: {HEALTHY_THRESHOLD}")

    # --- Summary table ---
    print(f"\n  Per-bolt summary:")
    print(f"    {'Bolt':>6s} {'Prec':>6s} {'Recall':>6s} {'F1':>6s} "
          f"{'Acc':>6s} {'n_pos':>6s}")
    print(f"    {'-'*38}")
    for bolt in sorted(bolt_results.keys()):
        r = bolt_results[bolt]
        print(f"    {bolt:>6d} {r['precision_cv']:>6.3f} {r['recall_cv']:>6.3f} "
              f"{r['f1_cv']:>6.3f} {r['accuracy_cv']:>6.3f} {r['n_positive']:>6d}")

    # --- Save ---
    if model_dir:
        pkl_path = os.path.join(model_dir, "binary_classifiers.pkl")
        bundle = {
            "models": {b: r["model"] for b, r in bolt_results.items()},
            "bolt_results": {
                b: {k: v for k, v in r.items() if k != "model"}
                for b, r in bolt_results.items()
            },
            "ensemble_accuracy": ensemble_acc,
            "healthy_threshold": HEALTHY_THRESHOLD,
            "bolt_ids": sorted(bolt_results.keys()),
        }
        joblib.dump(bundle, pkl_path)
        print(f"\n  Saved: {pkl_path}")

    return {
        "bolt_results": bolt_results,
        "ensemble_accuracy": ensemble_acc,
        "ensemble_preds": ensemble_preds,
        "healthy_threshold": HEALTHY_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# IsolationForest — anomaly detection trained on healthy cases
# ---------------------------------------------------------------------------
def train_isolation_forest(
    X_pca: np.ndarray,
    y: np.ndarray,
    study_ids: np.ndarray = None,
    model_dir: str = None,
) -> dict:
    """
    Train IsolationForest on healthy cases only.

    Healthy cases come from Study E (healthy variation) identified by
    study_ids, or fall back to label==0 cases.

    Study E is REQUIRED for meaningful anomaly detection. Without it,
    falls back to label==0 cases only (baseline + ties -- very few
    samples, degraded performance).

    This is permanent fallback logic -- not temporary. Same pattern as
    SMOTE threshold fallback: works with whatever healthy data exists,
    improves automatically as more is added. Generalizes to any FEM --
    spacecraft may have few healthy cases too.

    Args:
        X_pca: PCA-transformed feature matrix (all cases)
        y: bolt labels (0=healthy, N=bolt N is loosest)
        study_ids: per-row study IDs from npz (None = fallback to y==0)
        model_dir: directory to save isolation_forest.pkl

    Returns:
        dict with model, metrics, and source description, or None
    """
    if not _HAS_ISOFOREST:
        print("\n  IsolationForest: sklearn not available -- skipped")
        return None

    print("\n" + "=" * 60)
    print("ISOLATION FOREST -- ANOMALY DETECTION")
    print("=" * 60)

    MIN_HEALTHY_SAMPLES = 10

    # --- Identify healthy training rows ---
    # Priority: Study E rows (force_label=0, true healthy variation)
    # Fallback: any row with y==0 (baseline, ties -- limited diversity)
    study_e_mask = None
    if study_ids is not None:
        # Study E has force_label=0, so all its rows have y==0.
        # But we specifically want Study E rows because they have
        # controlled healthy stiffness variation (1e11-1e12 range).
        # Discover Study E study_id: it's the study whose rows are ALL y==0
        # AND has the most rows (Study E = 300 designs vs baseline = 1).
        candidate_sids = []
        for sid in np.unique(study_ids):
            mask = study_ids == sid
            if mask.sum() >= MIN_HEALTHY_SAMPLES and np.all(y[mask] == 0):
                candidate_sids.append((sid, mask.sum()))
        if candidate_sids:
            # Pick the largest all-healthy study (= Study E)
            best_sid, best_n = max(candidate_sids, key=lambda x: x[1])
            study_e_mask = study_ids == best_sid
            print(f"  Study E detected: study_id={best_sid} ({best_n} healthy rows)")

    if study_e_mask is not None and study_e_mask.sum() >= MIN_HEALTHY_SAMPLES:
        healthy_idx = np.where(study_e_mask)[0]
        source = f"Study E ({study_e_mask.sum()} healthy designs)"
    elif (y == 0).sum() >= MIN_HEALTHY_SAMPLES:
        healthy_idx = np.where(y == 0)[0]
        source = f"label==0 fallback ({(y == 0).sum()} cases)"
    else:
        n_healthy = (y == 0).sum()
        print(f"  WARNING: IsolationForest skipped -- "
              f"only {n_healthy} healthy cases. "
              f"Need >= {MIN_HEALTHY_SAMPLES}. "
              f"Run Study E (healthy variation) to fix this.")
        return None

    X_healthy = X_pca[healthy_idx]
    print(f"  Training on: {source}")
    print(f"  Healthy samples: {len(healthy_idx)}")
    print(f"  PCA dimensions:  {X_pca.shape[1]}")

    # --- Train ---
    t0 = time.time()
    iso = IsolationForest(
        contamination="auto",
        random_state=42,
        n_estimators=100,
    )
    iso.fit(X_healthy)
    elapsed = time.time() - t0
    print(f"  Fitted in {elapsed:.1f}s")

    # --- Validate on full dataset ---
    scores = iso.decision_function(X_pca)
    preds = iso.predict(X_pca)  # +1 = inlier (healthy), -1 = outlier (fault)

    n_fault = (y != 0).sum()
    n_healthy = (y == 0).sum()

    # True positive: fault case flagged as outlier (-1)
    true_pos = (preds[y != 0] == -1).sum() if n_fault > 0 else 0
    # True negative: healthy case flagged as inlier (+1)
    true_neg = (preds[y == 0] == 1).sum() if n_healthy > 0 else 0
    # False positive: healthy case flagged as outlier (-1)
    false_pos = (preds[y == 0] == -1).sum() if n_healthy > 0 else 0
    # False negative: fault case flagged as inlier (+1)
    false_neg = (preds[y != 0] == 1).sum() if n_fault > 0 else 0

    detection_rate = (true_pos + true_neg) / len(y)
    fault_detection = true_pos / n_fault if n_fault > 0 else 0.0
    false_alarm_rate = false_pos / n_healthy if n_healthy > 0 else 0.0

    print(f"\n  Results (full dataset, {len(y)} cases):")
    print(f"    Detection rate:     {detection_rate:.1%}")
    print(f"    Fault detection:    {fault_detection:.1%} "
          f"({true_pos}/{n_fault} faults caught)")
    print(f"    False alarm rate:   {false_alarm_rate:.1%} "
          f"({false_pos}/{n_healthy} healthy flagged)")
    print(f"    Missed faults:      {false_neg}/{n_fault}")

    # Score distribution summary
    print(f"\n  Score distribution:")
    print(f"    Healthy (y==0): mean={scores[y == 0].mean():.4f}, "
          f"std={scores[y == 0].std():.4f}")
    if n_fault > 0:
        print(f"    Faulty  (y!=0): mean={scores[y != 0].mean():.4f}, "
              f"std={scores[y != 0].std():.4f}")

    # --- Save ---
    if model_dir:
        iso_path = os.path.join(model_dir, "isolation_forest.pkl")
        iso_bundle = {
            "model": iso,
            "source": source,
            "n_healthy_train": len(healthy_idx),
            "detection_rate": detection_rate,
            "fault_detection": fault_detection,
            "false_alarm_rate": false_alarm_rate,
        }
        joblib.dump(iso_bundle, iso_path)
        print(f"\n  Saved: {iso_path}")

    return {
        "model": iso,
        "source": source,
        "detection_rate": detection_rate,
        "fault_detection": fault_detection,
        "false_alarm_rate": false_alarm_rate,
        "scores": scores,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    # Derive default paths from config.yaml when available
    _db_dir = r"D:\thesis_database"  # ultimate fallback
    try:
        import yaml
        _cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "fem_input", "config.yaml"
        )
        if os.path.exists(_cfg_path):
            with open(_cfg_path) as _cf:
                _cfg = yaml.safe_load(_cf) or {}
            _db_path = _cfg.get('database', {}).get('default_path', '')
            if _db_path:
                _db_dir = str(Path(_db_path).parent)
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Train bolt-localization classifiers (generalized)"
    )
    parser.add_argument(
        "--input",
        default=os.path.join(_db_dir, "training_matrix.npz"),
        help="Path to training_matrix.npz",
    )
    parser.add_argument(
        "--model-output",
        default=os.path.join(_db_dir, "bolt_classifier.pkl"),
        help="Path to save best model (.pkl)",
    )
    parser.add_argument(
        "--report",
        default=os.path.join(_db_dir, "classification_report.txt"),
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
    study_ids = bundle["study_ids"]

    # Train supervised classifiers (RF + XGBoost with PCA + SMOTE)
    results, classes, target_names = train_and_evaluate(
        X, y, feature_names, label_prefix="element",
        model_dir=model_dir,
    )

    # Save supervised model + report
    save_outputs(
        results, classes, target_names, y,
        feature_names, args.model_output, args.report,
    )

    # Reuse PCA-transformed features from the best supervised model
    best_name = max(results, key=lambda n: results[n]["mean_acc"])
    best_pca = results[best_name]["pca"]
    best_scaler = results[best_name]["scaler"]
    X_pca = best_pca.transform(best_scaler.transform(X))

    # Lever 4: Binary classifiers (one per bolt)
    binary_result = train_binary_classifiers(
        X_pca, y, model_dir=model_dir,
    )

    # IsolationForest (anomaly detection on healthy cases)

    iso_result = train_isolation_forest(
        X_pca, y, study_ids=study_ids, model_dir=model_dir,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
