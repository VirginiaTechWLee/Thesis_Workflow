r"""
clean_heeds.py -- Delete old HEEDS study folders and .heeds files so the
pipeline generates fresh ones from config.yaml.

Reads all paths from fem_input/config.yaml — no hardcoded paths.

Usage:
    python clean_heeds.py          # preview only (dry run)
    python clean_heeds.py --go     # actually delete
"""

import os
import shutil
import argparse
import sys

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(PIPELINE_DIR), "fem_input", "config.yaml")

# Study names used by the chain preset in run_pipeline.py
STUDIES = [
    "study_A_single_bolt_sweep",
    "study_B_two_bolt_sweep",
    "study_C_three_bolt_sweep",
    "study_D_monte_carlo",
]


def load_paths():
    """Read paths from config.yaml."""
    try:
        import yaml
    except ImportError:
        print("ERROR: PyYAML not installed. Run: pip install pyyaml")
        sys.exit(1)

    if not os.path.isfile(CONFIG_PATH):
        print(f"ERROR: config.yaml not found: {CONFIG_PATH}")
        sys.exit(1)

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}

    heeds_dir = cfg.get("paths", {}).get("heeds_working_dir", "")
    db_dir = cfg.get("paths", {}).get("db_dir", "")
    db_path = cfg.get("database", {}).get("default_path", os.path.join(db_dir, "thesis_results.db"))
    reports_dir = os.path.join(os.path.dirname(PIPELINE_DIR), "reports")

    if not heeds_dir:
        print("ERROR: paths.heeds_working_dir not set in config.yaml")
        sys.exit(1)
    if not db_dir:
        print("ERROR: paths.db_dir not set in config.yaml")
        sys.exit(1)

    return heeds_dir, db_dir, db_path, reports_dir


def main():
    parser = argparse.ArgumentParser(description="Clean old HEEDS data for fresh pipeline run")
    parser.add_argument("--go", action="store_true", help="Actually delete (default is dry run)")
    args = parser.parse_args()

    heeds_dir, db_dir, db_path, reports_dir = load_paths()

    print(f"Config:     {CONFIG_PATH}")
    print(f"HEEDS dir:  {heeds_dir}")
    print(f"DB dir:     {db_dir}")
    print(f"Reports:    {reports_dir}\n")

    targets = []

    # HEEDS study folders and .heeds project files
    for study in STUDIES:
        folder = os.path.join(heeds_dir, f"{study}_Study_1")
        heeds_file = os.path.join(heeds_dir, f"{study}.heeds")
        if os.path.isdir(folder):
            targets.append(("dir", folder))
        if os.path.isfile(heeds_file):
            targets.append(("file", heeds_file))

    # Database files
    for ext in ["", "-wal", "-shm", "-journal"]:
        db_file = f"{db_path}{ext}"
        if os.path.isfile(db_file):
            targets.append(("file", db_file))

    # Training matrix + classifier
    for fname in ["training_matrix.npz", "training_matrix.csv",
                   "bolt_classifier.pkl", "classification_report.txt"]:
        fp = os.path.join(db_dir, fname)
        if os.path.isfile(fp):
            targets.append(("file", fp))

    # Reports directory contents
    if os.path.isdir(reports_dir):
        for f in os.listdir(reports_dir):
            fp = os.path.join(reports_dir, f)
            if os.path.isfile(fp):
                targets.append(("file", fp))
            elif os.path.isdir(fp):
                targets.append(("dir", fp))

    if not targets:
        print("Nothing to clean.")
        return

    print(f"{'DELETE' if args.go else 'WOULD DELETE'} {len(targets)} items:\n")
    for kind, path in targets:
        tag = "[DIR ]" if kind == "dir" else "[FILE]"
        print(f"  {tag} {path}")

    if not args.go:
        print(f"\nDry run. Pass --go to actually delete.")
        return

    # Delete
    deleted = 0
    for kind, path in targets:
        try:
            if kind == "dir":
                shutil.rmtree(path)
            else:
                os.remove(path)
            deleted += 1
            print(f"  DELETED: {path}")
        except Exception as e:
            print(f"  FAILED:  {path} -- {e}")

    print(f"\nDone. Deleted {deleted}/{len(targets)} items.")


if __name__ == "__main__":
    main()
