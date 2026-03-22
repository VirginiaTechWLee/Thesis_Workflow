"""Print database summary statistics."""
import argparse
import sqlite3
import os
import sys


def main():
    parser = argparse.ArgumentParser(description='Print database summary')
    parser.add_argument('--db_path', required=True, help='Path to SQLite database')
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print('Database not found: ' + args.db_path)
        sys.exit(0)

    conn = sqlite3.connect(args.db_path)
    cursor = conn.cursor()

    size_mb = os.path.getsize(args.db_path) / (1024 * 1024)
    print('Database: ' + args.db_path)
    print('Size: {:.2f} MB'.format(size_mb))

    tables = [('studies', None), ('cases', None), ('psd_data', None),
              ('peaks', None), ('parameters', None)]
    for table, _ in tables:
        try:
            cursor.execute('SELECT COUNT(*) FROM ' + table)
            count = cursor.fetchone()[0]
            print('{}: {} rows'.format(table, count))
        except Exception:
            pass

    # Show studies
    try:
        cursor.execute('SELECT study_name, study_type, num_cases, status FROM studies')
        for row in cursor.fetchall():
            print('  Study: {} ({}, {} cases, {})'.format(*row))
    except Exception:
        pass

    # Show baseline
    try:
        cursor.execute('SELECT case_id, case_name FROM cases WHERE is_baseline = 1')
        baseline = cursor.fetchone()
        if baseline:
            print('Baseline: case_id={}, name={}'.format(*baseline))
    except Exception:
        pass

    conn.close()


if __name__ == '__main__':
    main()
