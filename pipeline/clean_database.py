"""
clean_database.py -- Truncate all data from the thesis database while
keeping the schema (tables, indexes, columns) intact.

Reads DB path from fem_input/config.yaml.

Usage:
    python clean_database.py                          # preview row counts
    python clean_database.py --go                     # delete all data
"""

import sqlite3
import os
import sys
import argparse

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(os.path.dirname(PIPELINE_DIR), "fem_input", "config.yaml")

# Tables in deletion order (children first to respect foreign keys)
TABLES = [
    "strain_energy",
    "force_peaks",
    "force_psd_data",
    "miles",
    "psd_data",
    "peaks",
    "parameters",
    "cases",
    "studies",
]


def load_db_path():
    """Read database path from config.yaml."""
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

    db_path = cfg.get("database", {}).get("default_path", "")
    if not db_path:
        db_dir = cfg.get("paths", {}).get("db_dir", "")
        db_path = os.path.join(db_dir, "thesis_results.db")

    return db_path


def main():
    parser = argparse.ArgumentParser(description="Truncate all data from thesis DB (keep schema)")
    parser.add_argument("--go", action="store_true", help="Actually delete (default is preview)")
    args = parser.parse_args()

    db_path = load_db_path()

    if not os.path.isfile(db_path):
        print(f"Database not found: {db_path}")
        print("Run setup_database.py first to create the schema.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Config:   {CONFIG_PATH}")
    print(f"Database: {db_path}")
    print(f"Size:     {os.path.getsize(db_path) / 1024 / 1024:.2f} MB\n")

    total_rows = 0
    print(f"{'Table':<20s} {'Rows':>12s}")
    print("-" * 34)
    for table in TABLES:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            count = 0
        total_rows += count
        print(f"  {table:<18s} {count:>10,d}")
    print("-" * 34)
    print(f"  {'TOTAL':<18s} {total_rows:>10,d}")

    if not args.go:
        print(f"\nDry run. Pass --go to delete all {total_rows:,} rows.")
        conn.close()
        return

    if total_rows == 0:
        print("\nDatabase is already empty.")
        conn.close()
        return

    print(f"\nDeleting all data...")
    for table in TABLES:
        try:
            cursor.execute(f"DELETE FROM {table}")
            print(f"  {table}: {cursor.rowcount:,} rows deleted")
        except sqlite3.OperationalError as e:
            print(f"  {table}: skipped ({e})")

    # Reset autoincrement counters
    cursor.execute("DELETE FROM sqlite_sequence")

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    size_after = os.path.getsize(db_path) / 1024 / 1024
    print(f"\nDone. DB size after VACUUM: {size_after:.2f} MB")
    print("Schema intact -- ready for fresh import.")


if __name__ == "__main__":
    main()
