"""
Stress-test the bolt-localization classifier for thesis-grade confidence.

Tests:
  1. 80/20 stratified train/test split
  2. Permutation test (shuffled labels baseline)
  3. Feature leakage audit
  4. Full confusion matrix on held-out test set
  5. Per-class metrics on held-out test set

Usage:
    python Scripts/stress_test_classifier.py --input D:\thesis_database\training_matrix.npz
"""
import argparse
import sys
import time

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler


def load_data(npz_path: str) -> dict:
    data = np.load(npz_path, allow_pickle=True)
    return {
        "X": data["X"],
        "y_bolt": data["y_bolt"],
        "y_binary": data["y_binary"],
        "feature_names": data["feature_names"],
    }


def main():
    parser = argparse.ArgumentParser(description="Stress-test classifier")
    parser.add_argument("--input", required=True, help="Path to training_matrix.npz")
    args = parser.parse_args()

    bundle = load_data(args.input)
    X_raw = bundle["X"]
    y_all = bundle["y_bolt"]
    feature_names = bundle["feature_names"]

    # ---------------------------------------------------------------
    # Drop the 1-sample baseline class (element 0) — it cannot be
    # meaningfully trained or evaluated and was dragging CV down to
    # 2-fold for every other class.
    # ---------------------------------------------------------------
    mask = y_all != 0
    X = X_raw[mask]
    y = y_all[mask]
    print("=" * 65)
    print("STRESS TEST — bolt localization classifier")
    print("=" * 65)
    print(f"  Dropped element-0 class (1 healthy baseline sample)")
    print(f"  Working set: {X.shape[0]} samples, {X.shape[1]} features, "
          f"{len(np.unique(y))} classes")
    print(f"  Classes: {sorted(np.unique(y))}")
    for cls in sorted(np.unique(y)):
        print(f"    element {cls}: {(y == cls).sum()} samples")

    # ---------------------------------------------------------------
    # TEST 1: Proper 5-fold stratified CV (now feasible)
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("TEST 1: 5-fold stratified cross-validation")
    print("=" * 65)

    scaler = StandardScaler()
    X_scaled = np.ascontiguousarray(scaler.fit_transform(X), dtype=np.float64)
    y = np.asarray(y, dtype=np.intp)

    rf = RandomForestClassifier(
        n_estimators=200, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(rf, X_scaled, y, cv=cv, scoring="accuracy")
    print(f"  Fold accuracies: {[f'{s:.4f}' for s in scores]}")
    print(f"  Mean: {scores.mean():.4f} +/- {scores.std():.4f}")

    # ---------------------------------------------------------------
    # TEST 2: 80/20 stratified train/test split
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("TEST 2: 80/20 stratified hold-out split")
    print("=" * 65)

    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.20, stratify=y, random_state=42,
    )
    print(f"  Train: {X_train.shape[0]}  Test: {X_test.shape[0]}")

    rf_split = RandomForestClassifier(
        n_estimators=200, class_weight="balanced",
        random_state=42, n_jobs=-1,
    )
    rf_split.fit(X_train, y_train)
    y_pred = rf_split.predict(X_test)
    test_acc = accuracy_score(y_test, y_pred)
    print(f"  Hold-out accuracy: {test_acc:.4f}")

    # Per-class report
    classes = sorted(np.unique(y))
    target_names = [f"element_{c}" for c in classes]
    report = classification_report(
        y_test, y_pred, target_names=target_names, zero_division=0,
    )
    print(f"\n  Classification Report (hold-out):\n")
    for line in report.strip().split("\n"):
        print(f"    {line}")

    # ---------------------------------------------------------------
    # TEST 3: Full confusion matrix on held-out test set
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("TEST 3: Confusion matrix (hold-out test set)")
    print("=" * 65)

    cm = confusion_matrix(y_test, y_pred, labels=classes)
    header = "        " + "".join(f"{c:>7}" for c in classes)
    print(f"    {header}")
    for i, cls in enumerate(classes):
        row_str = "".join(f"{cm[i, j]:>7}" for j in range(len(classes)))
        n_total = cm[i].sum()
        n_correct = cm[i, i]
        print(f"    {cls:>6}: {row_str}   ({n_correct}/{n_total})")

    # ---------------------------------------------------------------
    # TEST 4: Permutation test — how good is chance?
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("TEST 4: Permutation test (5 random shuffles)")
    print("=" * 65)

    rng = np.random.RandomState(123)
    perm_accs = []
    for i in range(5):
        y_shuffled = rng.permutation(y)
        rf_perm = RandomForestClassifier(
            n_estimators=100, class_weight="balanced",
            random_state=42, n_jobs=-1,
        )
        perm_scores = cross_val_score(
            rf_perm, X_scaled, y_shuffled, cv=cv, scoring="accuracy",
        )
        perm_acc = perm_scores.mean()
        perm_accs.append(perm_acc)
        print(f"  Shuffle {i+1}: {perm_acc:.4f}")

    mean_perm = np.mean(perm_accs)
    print(f"  Mean chance accuracy: {mean_perm:.4f}")
    print(f"  Real accuracy:        {scores.mean():.4f}")
    print(f"  Lift over chance:     {scores.mean() - mean_perm:.4f} "
          f"({scores.mean() / mean_perm:.1f}x)")

    # ---------------------------------------------------------------
    # TEST 5: Feature leakage audit
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("TEST 5: Feature leakage audit")
    print("=" * 65)

    # Check 1: any feature names that look like labels
    suspicious_names = []
    leak_keywords = [
        "label", "target", "bolt", "element", "case_id", "case_number",
        "loosened", "severity", "class", "y_",
    ]
    for fname in feature_names:
        fname_lower = fname.lower()
        for kw in leak_keywords:
            if kw in fname_lower:
                suspicious_names.append((fname, kw))
                break
    if suspicious_names:
        print(f"  WARNING — suspicious feature names:")
        for fname, kw in suspicious_names:
            print(f"    '{fname}' contains '{kw}'")
    else:
        print(f"  No suspicious feature names found (checked {len(feature_names)} features)")

    # Check 2: any single feature with near-perfect correlation to label
    # Use ANOVA F-statistic (fast, no model fitting) instead of per-feature CV
    print(f"\n  Checking single-feature predictive power (ANOVA F-test) ...")
    from sklearn.feature_selection import f_classif

    f_scores, p_values = f_classif(X_scaled, y)
    # Convert F-scores to a rough single-feature accuracy proxy via a
    # simple threshold classifier on the top features only
    from sklearn.tree import DecisionTreeClassifier

    top_f_idx = np.argsort(f_scores)[::-1][:20]  # only check top 20
    single_feat_accs = []
    for i in top_f_idx:
        dt = DecisionTreeClassifier(max_depth=3, random_state=42)
        dt_scores = cross_val_score(
            dt, X_scaled[:, i:i+1], y, cv=cv, scoring="accuracy",
        )
        single_feat_accs.append((dt_scores.mean(), feature_names[i]))

    single_feat_accs.sort(reverse=True)
    print(f"  Top 10 single-feature accuracies (should be << ensemble accuracy):")
    any_suspicious = False
    for acc, fname in single_feat_accs[:10]:
        flag = " *** SUSPICIOUS" if acc > 0.7 else ""
        if acc > 0.7:
            any_suspicious = True
        print(f"    {fname:<30s} {acc:.4f}{flag}")

    if not any_suspicious:
        print(f"\n  No single feature exceeds 0.70 accuracy — no obvious leakage")
    else:
        print(f"\n  WARNING: Some features have high single-feature accuracy — "
              f"investigate for leakage")

    # ---------------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("SUMMARY")
    print("=" * 65)
    print(f"  5-fold CV accuracy:     {scores.mean():.4f} +/- {scores.std():.4f}")
    print(f"  Hold-out accuracy:      {test_acc:.4f}")
    print(f"  Chance baseline:        {mean_perm:.4f}")
    print(f"  Lift over chance:       {scores.mean() / mean_perm:.1f}x")
    print(f"  Feature leakage:        {'POSSIBLE — investigate' if any_suspicious else 'None detected'}")

    if scores.mean() > mean_perm + 0.10 and not any_suspicious:
        print(f"\n  VERDICT: Result appears genuine — safe to report in thesis")
    elif any_suspicious:
        print(f"\n  VERDICT: Investigate suspicious features before reporting")
    else:
        print(f"\n  VERDICT: Accuracy is close to chance — model may not be meaningful")

    print()


if __name__ == "__main__":
    main()
