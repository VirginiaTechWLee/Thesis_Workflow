"""
Train bolt-localization classifiers from a feature matrix (.npz).

Fully generalized — derives all class counts, feature counts, label
mappings, and CV strategy from the data.  Works with any beam model,
any number of bolts, any number of severity levels.

Usage:
    python Scripts/train_classifier.py --input D:\\thesis_database\\training_matrix.npz
    python Scripts/train_classifier.py --input data.npz --model-output model.pkl --report report.txt
"""
import argparse
import sys
import textwrap
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler


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
    """Return the largest k <= max_k such that every class has >= k samples."""
    _, counts = np.unique(y, return_counts=True)
    min_count = counts.min()
    k = min(max_k, min_count)
    return max(k, 2)  # at least 2-fold


# ---------------------------------------------------------------------------
# Training + evaluation
# ---------------------------------------------------------------------------
def train_and_evaluate(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: np.ndarray,
    label_prefix: str = "element",
) -> dict:
    """
    Train Random Forest and GradientBoosting with stratified k-fold CV.
    Returns dict with best model, reports, confusion matrices, importances.
    """
    k = _choose_k(y)
    classes = sorted(np.unique(y))
    target_names = [f"{label_prefix}_{c}" for c in classes]

    print(f"\n{'=' * 60}")
    print(f"TRAINING — {len(classes)} classes, {k}-fold stratified CV")
    print(f"{'=' * 60}")

    # Scale features — enforce float64 C-contiguous for sklearn Cython routines
    # (works around NumPy 2.x / sklearn dtype dispatch issues)
    scaler = StandardScaler()
    X_scaled = np.ascontiguousarray(scaler.fit_transform(X), dtype=np.float64)
    y = np.asarray(y, dtype=np.intp)  # native int for sklearn

    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)

    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.1,
            random_state=42,
        ),
    }

    results = {}
    for name, model in models.items():
        print(f"\n--- {name} ---")
        t0 = time.time()

        # Cross-val predictions (gives per-sample predictions for full report)
        y_pred = cross_val_predict(model, X_scaled, y, cv=cv)
        elapsed = time.time() - t0

        # Per-fold accuracy for mean/std
        fold_accs = []
        for train_idx, test_idx in cv.split(X_scaled, y):
            fold_accs.append((y_pred[test_idx] == y[test_idx]).mean())
        mean_acc = np.mean(fold_accs)
        std_acc = np.std(fold_accs)

        print(f"  CV accuracy: {mean_acc:.4f} +/- {std_acc:.4f}  ({elapsed:.1f}s)")

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
        # Header
        header = "        " + "".join(f"{c:>7}" for c in classes)
        print(f"    {header}")
        for i, cls in enumerate(classes):
            row_str = "".join(f"{cm[i, j]:>7}" for j in range(len(classes)))
            print(f"    {cls:>6}: {row_str}")

        # Fit on full data for feature importance and final model
        model.fit(X_scaled, y)
        importances = model.feature_importances_
        top_idx = np.argsort(importances)[::-1][:20]
        print(f"\n  Top 20 features:")
        for rank, fi in enumerate(top_idx, 1):
            print(f"    {rank:>2}. {feature_names[fi]:<25s} {importances[fi]:.6f}")

        results[name] = {
            "model": model,
            "scaler": scaler,
            "mean_acc": mean_acc,
            "std_acc": std_acc,
            "report": report,
            "confusion_matrix": cm,
            "importances": importances,
            "y_pred": y_pred,
        }

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

    # Save model bundle
    bundle = {
        "model": best["model"],
        "scaler": best["scaler"],
        "model_name": best_name,
        "classes": classes,
        "target_names": target_names,
        "feature_names": list(feature_names),
        "mean_accuracy": best["mean_acc"],
        "std_accuracy": best["std_acc"],
    }
    joblib.dump(bundle, model_output)
    print(f"  Saved model: {model_output}")

    # Save report
    lines = []
    lines.append("BOLT LOCALIZATION — CLASSIFICATION REPORT")
    lines.append("=" * 60)
    lines.append(f"Samples: {len(y)}")
    lines.append(f"Features: {len(feature_names)}")
    lines.append(f"Classes: {len(classes)} — {classes}")
    lines.append("")

    for name, res in results.items():
        lines.append(f"{'=' * 60}")
        lines.append(f"MODEL: {name}")
        lines.append(f"{'=' * 60}")
        lines.append(f"CV accuracy: {res['mean_acc']:.4f} +/- {res['std_acc']:.4f}")
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
        lines.append("Top 20 features:")
        for rank, fi in enumerate(top_idx, 1):
            lines.append(
                f"  {rank:>2}. {feature_names[fi]:<25s} "
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

    # Load
    bundle = load_data(args.input)
    X = bundle["X"]
    y = bundle["y_bolt"]
    feature_names = bundle["feature_names"]

    # Train
    results, classes, target_names = train_and_evaluate(
        X, y, feature_names, label_prefix="element"
    )

    # Save
    save_outputs(
        results, classes, target_names, y,
        feature_names, args.model_output, args.report,
    )

    print("\nDone.")


if __name__ == "__main__":
    main()
