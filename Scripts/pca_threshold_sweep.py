"""
PCA variance threshold sweep — Lever 8 calibration tool.

Tests multiple PCA variance retention thresholds and reports CV accuracy
for each. Use this to find the optimal threshold for a new FEM, then
update config.yaml pca.variance_threshold with the winning value.

Usage:
    python Scripts/pca_threshold_sweep.py
    python Scripts/pca_threshold_sweep.py --input D:\\thesis_database\\training_matrix.npz
    python Scripts/pca_threshold_sweep.py --thresholds 0.80 0.85 0.90 0.95 0.99

Workflow for a new FEM:
    1. Run full pipeline (extract features, etc.)
    2. Run this script to find optimal PCA threshold
    3. Update config.yaml: pca.variance_threshold: 0.XX
    4. Run train_classifier.py with the optimized threshold

This script does NOT:
    - Save any model files
    - Modify config.yaml
    - Train final models
It only prints a comparison table for human review.
"""
import argparse
import os
import sys
import time

os.environ["PYTHONUNBUFFERED"] = "1"

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import LabelEncoder, StandardScaler

try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from imblearn.over_sampling import SMOTE
    _HAS_SMOTE = True
except ImportError:
    _HAS_SMOTE = False


def _choose_k(y):
    """Same logic as train_classifier.py — adapt folds to smallest class."""
    _, counts = np.unique(y, return_counts=True)
    min_class = counts.min()
    if min_class < 2:
        return 2
    if min_class < 5:
        return min(min_class, 3)
    if min_class < 10:
        return 5
    return 10


def sweep(npz_path, thresholds):
    """Run PCA + CV accuracy for each threshold. Returns list of result dicts."""
    data = np.load(npz_path, allow_pickle=True)
    X = data["X"]
    y = data["y_bolt"]
    feature_names = data["feature_names"]

    print("=" * 65)
    print("PCA VARIANCE THRESHOLD SWEEP (Lever 8)")
    print("=" * 65)
    print(f"  Input:      {npz_path}")
    print(f"  Samples:    {X.shape[0]}")
    print(f"  Features:   {X.shape[1]}")
    print(f"  Classes:    {len(np.unique(y))}")
    print(f"  Thresholds: {thresholds}")
    print(f"  XGBoost:    {'yes' if _HAS_XGB else 'no (using RF only)'}")
    print(f"  SMOTE:      {'yes' if _HAS_SMOTE else 'no'}")

    # Scale once — PCA thresholds share the same scaler
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    k = _choose_k(y)
    print(f"  CV folds:   {k}")
    print()

    results = []

    for thresh in thresholds:
        print(f"--- Threshold: {thresh:.0%} ---")
        t0 = time.time()

        # PCA
        pca = PCA(n_components=thresh, random_state=42)
        X_pca = pca.fit_transform(X_scaled)
        n_components = X_pca.shape[1]
        var_retained = pca.explained_variance_ratio_.sum()
        ratio = X_pca.shape[0] / n_components

        print(f"  PCA: {X.shape[1]} -> {n_components} components "
              f"({var_retained:.2%} variance)")
        print(f"  Sample:feature ratio: {ratio:.1f}:1")

        # CV with best available model
        skf = StratifiedKFold(n_splits=k, shuffle=True, random_state=42)

        model_results = {}

        # RF
        rf = RandomForestClassifier(
            n_estimators=200, class_weight="balanced",
            random_state=42, n_jobs=-1,
        )
        y_pred_rf = _cv_with_smote(rf, X_pca, y, skf)
        rf_acc = (y_pred_rf == y).mean()
        model_results["RF"] = rf_acc
        print(f"  RF  CV accuracy: {rf_acc:.4f}")

        # XGBoost
        if _HAS_XGB:
            le = LabelEncoder()
            y_enc = le.fit_transform(y)
            xgb = XGBClassifier(
                n_estimators=200, max_depth=6, learning_rate=0.1,
                random_state=42, use_label_encoder=False,
                eval_metric="logloss", n_jobs=-1,
            )
            y_pred_xgb_enc = _cv_with_smote(xgb, X_pca, y_enc, skf)
            y_pred_xgb = le.inverse_transform(y_pred_xgb_enc)
            xgb_acc = (y_pred_xgb == y).mean()
            model_results["XGB"] = xgb_acc
            print(f"  XGB CV accuracy: {xgb_acc:.4f}")

        best_model = max(model_results, key=model_results.get)
        best_acc = model_results[best_model]
        elapsed = time.time() - t0

        results.append({
            "threshold": thresh,
            "n_components": n_components,
            "var_retained": var_retained,
            "ratio": ratio,
            "rf_acc": model_results.get("RF", 0),
            "xgb_acc": model_results.get("XGB", 0),
            "best_model": best_model,
            "best_acc": best_acc,
            "elapsed": elapsed,
        })
        print(f"  Best: {best_model} ({best_acc:.4f})  [{elapsed:.1f}s]")
        print()

    return results


def _cv_with_smote(model, X_pca, y, skf):
    """Run cross-validated predictions with per-fold SMOTE."""
    if not _HAS_SMOTE:
        return cross_val_predict(model, X_pca, y, cv=skf)

    y_pred = np.empty_like(y)
    for train_idx, test_idx in skf.split(X_pca, y):
        X_tr, y_tr = X_pca[train_idx], y[train_idx]
        X_te = X_pca[test_idx]

        # SMOTE on train fold
        MIN_SMOTE = 6
        vals, counts = np.unique(y_tr, return_counts=True)
        eligible = counts >= MIN_SMOTE
        if eligible.any():
            target = int(counts[eligible].max())
            strategy = {
                int(cls): target
                for cls, cnt in zip(vals, counts)
                if cnt >= MIN_SMOTE and cnt < target
            }
            if strategy:
                k_neighbors = min(5, int(counts[eligible].min()) - 1)
                sm = SMOTE(random_state=42, k_neighbors=k_neighbors,
                           sampling_strategy=strategy)
                X_tr, y_tr = sm.fit_resample(X_tr, y_tr)

        m = type(model)(**model.get_params())
        m.fit(X_tr, y_tr)
        y_pred[test_idx] = m.predict(X_te)

    return y_pred


def print_summary(results):
    """Print comparison table and recommendation."""
    print("=" * 65)
    print("SWEEP RESULTS")
    print("=" * 65)
    print(f"{'Thresh':>7s} {'Comp':>5s} {'Var':>7s} {'Ratio':>6s} "
          f"{'RF':>7s} {'XGB':>7s} {'Best':>7s} {'Time':>6s}")
    print("-" * 65)

    for r in results:
        xgb_str = f"{r['xgb_acc']:.4f}" if r['xgb_acc'] > 0 else "  n/a "
        print(f"{r['threshold']:>6.0%}  {r['n_components']:>5d} "
              f"{r['var_retained']:>6.2%} {r['ratio']:>6.1f} "
              f"{r['rf_acc']:>7.4f} {xgb_str:>7s} {r['best_acc']:>7.4f} "
              f"{r['elapsed']:>5.1f}s")

    # Recommendation
    best = max(results, key=lambda r: r["best_acc"])
    print()
    print(f"RECOMMENDATION: {best['threshold']:.0%} variance threshold")
    print(f"  {best['best_model']} accuracy: {best['best_acc']:.4f}")
    print(f"  PCA components: {best['n_components']}")
    print(f"  Sample:feature ratio: {best['ratio']:.1f}:1")
    print()
    print(f"To apply: update config.yaml")
    print(f"  pca:")
    print(f"    variance_threshold: {best['threshold']}")
    print()
    print("Then re-run train_classifier.py to train final models.")


def main():
    parser = argparse.ArgumentParser(
        description="PCA variance threshold sweep (Lever 8)"
    )
    parser.add_argument(
        "--input",
        default=r"D:\thesis_database\training_matrix.npz",
        help="Path to training_matrix.npz",
    )
    parser.add_argument(
        "--thresholds",
        nargs="+",
        type=float,
        default=[0.85, 0.90, 0.95],
        help="Variance thresholds to test (default: 0.85 0.90 0.95)",
    )
    args = parser.parse_args()

    results = sweep(args.input, sorted(args.thresholds))
    print_summary(results)


if __name__ == "__main__":
    main()
