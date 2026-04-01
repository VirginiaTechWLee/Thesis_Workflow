#!/usr/bin/env python
"""
validate_classifier.py
======================
End-to-end validation of the bolt looseness detection classifier.

This standalone script demonstrates the full inference pipeline by loading
the training matrix, fitting a GradientBoostingClassifier (matching the
main pipeline), and running predictions on synthetically-noised versions
of known cases. It serves as both a sanity check and a thesis-quality
demonstration of classifier robustness to measurement noise.

Modes
-----
single       Pick one known case (default: Element 3 loosened), add Gaussian
             noise, and report the predicted label with confidence.
all_classes  Pick one random case from every class in the training set, add
             noise, run predictions, and display a summary table.

Usage
-----
    python validate_classifier.py --mode single --noise_level 0.02
    python validate_classifier.py --mode all_classes
    python validate_classifier.py --help

Author:  Wayne Lee
Project: Spacecraft Bolt Looseness Detection (Virginia Tech)
"""

import argparse
import sys
import textwrap
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import accuracy_score
except ImportError:
    print("ERROR: scikit-learn is required.  Install with:  pip install scikit-learn",
          flush=True)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _default_db_dir():
    """Discover the DB directory from config.yaml, falling back to D:\\thesis_database."""
    try:
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "fem_input" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            db_path = cfg.get('database', {}).get('default_path', '')
            if db_path:
                return Path(db_path).parent
    except Exception:
        pass
    return Path(r"D:\thesis_database")

_DB_DIR = _default_db_dir()
TRAINING_MATRIX = _DB_DIR / "training_matrix.npz"
CLASSIFICATION_REPORT = _DB_DIR / "classification_report.txt"
OUTPUT_PATH = _DB_DIR / "validation_results.txt"

# ---------------------------------------------------------------------------
# Dynamic LABEL_MAP — discovered from DB, no hardcoded beam geometry
# ---------------------------------------------------------------------------
LABEL_MAP = None  # populated lazily by _build_label_map()


def _build_label_map(db_path=None):
    """Build human-readable label map by querying unique element IDs from the DB.

    Falls back to a minimal {0: "Healthy"} map if the DB is unavailable.
    Discovers bolt-to-node mapping from config.yaml output_nodes when available.
    """
    global LABEL_MAP
    if LABEL_MAP is not None:
        return LABEL_MAP

    label_map = {0: "Healthy"}

    # Try to discover element IDs from the database
    if db_path is None:
        try:
            import yaml
            cfg_path = Path(__file__).resolve().parent.parent / "fem_input" / "config.yaml"
            if cfg_path.exists():
                with open(cfg_path) as f:
                    cfg = yaml.safe_load(f) or {}
                db_path = cfg.get('database', {}).get('default_path')
        except Exception:
            pass

    # Try loading output_nodes from config for node mapping
    output_nodes = None
    try:
        import yaml
        cfg_path = Path(__file__).resolve().parent.parent / "fem_input" / "config.yaml"
        if cfg_path.exists():
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f) or {}
            output_nodes = cfg.get('output_nodes', [])
    except Exception:
        pass

    # Query DB for unique element IDs
    element_ids = set()
    if db_path and Path(db_path).exists():
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.execute("SELECT DISTINCT element_id FROM parameters")
            element_ids = {row[0] for row in cursor.fetchall()}
            conn.close()
        except Exception:
            pass

    # Build node map: element N -> node pair.
    # If output_nodes available, find the node that is element_id * 111.
    # Otherwise just label as "CBUSH {N}".
    node_set = set(output_nodes) if output_nodes else set()
    for eid in sorted(element_ids):
        if eid == 0:
            continue
        # Convention: CBUSH element N connects node N to node N*111
        companion = eid * 111
        if node_set and companion in node_set:
            label_map[eid] = f"CBUSH {eid} (Nodes {eid}-{companion})"
        else:
            label_map[eid] = f"CBUSH {eid}"

    # Fallback: if DB had no elements, discover from training data labels
    if len(label_map) == 1:
        # Will be populated later from y labels in load_training_data
        pass

    LABEL_MAP = label_map
    return LABEL_MAP


def _ensure_label_map_covers(y):
    """Ensure LABEL_MAP covers all labels found in training data y."""
    global LABEL_MAP
    if LABEL_MAP is None:
        _build_label_map()
    for lbl in set(y):
        lbl = int(lbl)
        if lbl not in LABEL_MAP:
            LABEL_MAP[lbl] = f"CBUSH {lbl}"


def label_name(lbl):
    """Convert numeric label to human-readable name."""
    if LABEL_MAP is None:
        _build_label_map()
    return LABEL_MAP.get(lbl, f"CBUSH {lbl}")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _print(msg="", end="\n"):
    """Print wrapper that always flushes."""
    print(msg, end=end, flush=True)


def load_training_data(path: Path):
    """Load the training matrix (.npz) containing 'X' and 'y_bolt' arrays.

    Parameters
    ----------
    path : Path
        Location of the .npz file produced by the feature-extraction stage.

    Returns
    -------
    X : np.ndarray, shape (n_samples, n_features)
    y : np.ndarray, shape (n_samples,)
    feature_names : np.ndarray or None
    """
    _print(f"Loading training matrix from {path} ...")
    if not path.exists():
        _print(f"ERROR: Training matrix not found at {path}")
        sys.exit(1)

    data = np.load(path, allow_pickle=True)
    X = data["X"]
    # The pipeline stores bolt labels as 'y_bolt', not 'y'
    if "y_bolt" in data:
        y = data["y_bolt"]
    elif "y" in data:
        y = data["y"]
    else:
        _print(f"ERROR: No label array found. Available keys: {list(data.keys())}")
        sys.exit(1)
    feature_names = data["feature_names"] if "feature_names" in data else None
    _print(f"  Loaded {X.shape[0]} samples, {X.shape[1]} features, "
           f"{len(np.unique(y))} classes.")
    _print(f"  Classes: {sorted(np.unique(y))}")
    _ensure_label_map_covers(y)
    return X, y, feature_names


def read_model_info(path: Path):
    """Read the classification report for context logging.

    Returns the file contents as a string, or a placeholder if not found.
    """
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    return "(classification_report.txt not found -- training info unavailable)"


def build_classifier(X, y, random_state=42):
    """Train a GradientBoostingClassifier on an 80/20 split.

    Uses a stratified train/test split so the validation tests on
    held-out data the classifier has never seen — this is a more
    honest evaluation than testing on noised training samples.

    Parameters
    ----------
    X : np.ndarray
    y : np.ndarray
    random_state : int

    Returns
    -------
    clf : GradientBoostingClassifier (fitted on train split)
    scaler : StandardScaler (fitted on train split)
    X_test : np.ndarray (held-out test features, unscaled)
    y_test : np.ndarray (held-out test labels)
    train_acc : float
    test_acc : float
    """
    from sklearn.model_selection import train_test_split

    _print("Splitting data 80/20 (stratified) ...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=random_state, stratify=y
    )
    _print(f"  Train: {X_train.shape[0]} samples, Test: {X_test.shape[0]} samples")

    _print("Training GradientBoostingClassifier ...")

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    clf = GradientBoostingClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        random_state=random_state,
    )
    clf.fit(X_train_scaled, y_train)

    train_acc = accuracy_score(y_train, clf.predict(X_train_scaled))
    X_test_scaled = scaler.transform(X_test)
    test_acc = accuracy_score(y_test, clf.predict(X_test_scaled))
    _print(f"  Training accuracy: {train_acc:.4f}")
    _print(f"  Test accuracy (no noise): {test_acc:.4f}")
    return clf, scaler, X_test, y_test, train_acc, test_acc


def add_noise(x, noise_level, rng):
    """Add element-wise Gaussian noise scaled to each feature's magnitude.

    Parameters
    ----------
    x : np.ndarray, shape (n_features,)
        Original feature vector.
    noise_level : float
        Standard deviation of noise as a fraction of |feature value|.
    rng : np.random.Generator

    Returns
    -------
    x_noisy : np.ndarray
    """
    scale = np.abs(x) * noise_level
    # For zero-valued features, fall back to global scale so noise is nonzero
    global_scale = np.mean(np.abs(x)) * noise_level
    scale[scale == 0] = global_scale
    noise = rng.normal(0.0, scale)
    return x + noise


def predict_single(clf, scaler, x_noisy):
    """Return predicted label and per-class probabilities for one sample."""
    x_scaled = scaler.transform(x_noisy.reshape(1, -1))
    pred = clf.predict(x_scaled)[0]
    proba = clf.predict_proba(x_scaled)[0]
    return pred, proba


# ---------------------------------------------------------------------------
# Mode: single
# ---------------------------------------------------------------------------
def run_single(X, y, clf, scaler, noise_level, rng):
    """Demonstrate prediction on a single noised case.

    Picks the first sample whose label matches the most common non-baseline
    class (typically an Element loosened case).  Falls back to index 0 if
    the heuristic fails.
    """
    _print("\n" + "=" * 70)
    _print("MODE: single")
    _print("=" * 70)

    classes = np.unique(y)
    # Prefer Element 2 (dominant feature), then Element 3
    target_class = None
    for preferred in [2, 3, 4, 5]:
        if preferred in classes:
            target_class = preferred
            break
    if target_class is None:
        target_class = classes[min(1, len(classes) - 1)]

    indices = np.where(y == target_class)[0]
    idx = rng.choice(indices)
    x_orig = X[idx]
    true_label = y[idx]

    _print(f"\nSelected sample index {idx}  |  True label: {true_label}")
    _print(f"Noise level: {noise_level * 100:.1f}%")

    x_noisy = add_noise(x_orig, noise_level, rng)
    pred, proba = predict_single(clf, scaler, x_noisy)
    confidence = np.max(proba) * 100.0

    pred_name = label_name(pred)
    true_name = label_name(true_label)
    _print(f"\n>>> Given this measurement, the classifier predicts:")
    _print(f"    {pred_name} is loosened with {confidence:.1f}% confidence.")
    _print(f"    (True condition: {true_name})")

    if pred == true_label:
        _print("    Result: CORRECT")
    else:
        _print(f"    Result: MISMATCH (true label was {true_label})")

    _print(f"\n  Class probabilities:")
    for cls, p in zip(clf.classes_, proba):
        bar = "#" * int(p * 40)
        _print(f"    {label_name(cls):>28s}  {p:6.3f}  {bar}")

    return [(true_label, pred, confidence)]


# ---------------------------------------------------------------------------
# Mode: all_classes
# ---------------------------------------------------------------------------
def run_all_classes(X, y, clf, scaler, noise_level, rng):
    """Pick one random sample from each class, noise it, predict, summarise."""
    _print("\n" + "=" * 70)
    _print("MODE: all_classes  (one random sample per class)")
    _print("=" * 70)
    _print(f"Noise level: {noise_level * 100:.1f}%\n")

    classes = np.unique(y)
    results = []

    # Header
    _print(f"{'True Condition':>28s}  {'Predicted':>28s}  {'Conf%':>7s}  {'Match':>5s}")
    _print("-" * 76)

    for cls in classes:
        indices = np.where(y == cls)[0]
        idx = rng.choice(indices)
        x_orig = X[idx]
        x_noisy = add_noise(x_orig, noise_level, rng)

        pred, proba = predict_single(clf, scaler, x_noisy)
        confidence = np.max(proba) * 100.0
        match = "OK" if pred == cls else "MISS"
        results.append((cls, pred, confidence))

        _print(f"{label_name(cls):>28s}  {label_name(pred):>28s}  {confidence:6.1f}%  {match:>5s}")

    # Summary
    n_correct = sum(1 for t, p, _ in results if t == p)
    _print("-" * 70)
    _print(f"Accuracy on noised samples: {n_correct}/{len(results)} "
           f"({n_correct / len(results) * 100:.1f}%)")

    return results


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------
def write_results(output_path, results, mode, noise_level, model_info):
    """Persist validation results to a plain-text file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("BOLT LOOSENESS CLASSIFIER -- VALIDATION RESULTS")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Mode:        {mode}")
    lines.append(f"Noise level: {noise_level * 100:.1f}%")
    lines.append(f"Samples:     {len(results)}")
    lines.append("")

    lines.append(f"{'True Condition':>28s}  {'Predicted':>28s}  {'Conf%':>7s}  {'Match':>5s}")
    lines.append("-" * 76)
    for true_lbl, pred_lbl, conf in results:
        match = "OK" if true_lbl == pred_lbl else "MISS"
        lines.append(f"{label_name(true_lbl):>28s}  {label_name(pred_lbl):>28s}  {conf:6.1f}%  {match:>5s}")

    n_correct = sum(1 for t, p, _ in results if t == p)
    lines.append("-" * 70)
    lines.append(f"Accuracy: {n_correct}/{len(results)} "
                 f"({n_correct / len(results) * 100:.1f}%)")
    lines.append("")
    lines.append("MODEL CONTEXT (from classification_report.txt)")
    lines.append("-" * 60)
    # Include first 40 lines of model info for context
    info_lines = model_info.splitlines()[:40]
    lines.extend(info_lines)
    if len(model_info.splitlines()) > 40:
        lines.append("... (truncated)")

    text = "\n".join(lines) + "\n"
    output_path.write_text(text, encoding="utf-8")
    _print(f"\nResults written to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate the bolt looseness GradientBoosting classifier "
                    "by running noised copies of known training cases through "
                    "the full inference pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples
            --------
              python validate_classifier.py --mode single
              python validate_classifier.py --mode all_classes --noise_level 0.05
        """),
    )
    parser.add_argument(
        "--mode",
        choices=["single", "all_classes"],
        default="single",
        help="'single' demonstrates one case; 'all_classes' tests one sample "
             "per class. Default: single.",
    )
    parser.add_argument(
        "--noise_level",
        type=float,
        default=0.01,
        help="Gaussian noise standard deviation as a fraction of feature "
             "magnitude (e.g. 0.01 = 1%%). Default: 0.01.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility. Default: None (random).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUT_PATH),
        help=f"Path for the results file. Default: {OUTPUT_PATH}",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    _print("=" * 70)
    _print("  Bolt Looseness Classifier Validation")
    _print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    _print("=" * 70)

    # 1. Load data
    X, y, feature_names = load_training_data(TRAINING_MATRIX)

    # 2. Read model context
    model_info = read_model_info(CLASSIFICATION_REPORT)
    _print(f"Classification report: {'found' if CLASSIFICATION_REPORT.exists() else 'not found'}")

    # 3. Train classifier on 80% split (mirrors pipeline)
    clf, scaler, X_test, y_test, train_acc, test_acc = build_classifier(X, y, random_state=42)

    # 4. Run selected mode — use HELD-OUT test data, not training data
    if args.mode == "single":
        results = run_single(X_test, y_test, clf, scaler, args.noise_level, rng)
    else:
        results = run_all_classes(X_test, y_test, clf, scaler, args.noise_level, rng)

    # 5. Write results
    write_results(Path(args.output), results, args.mode, args.noise_level,
                  model_info)

    _print("\nValidation complete.")


if __name__ == "__main__":
    main()
