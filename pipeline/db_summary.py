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
        cursor.execute('SELECT study_id, study_name, study_type, num_cases, is_baseline, status FROM studies ORDER BY study_id')
        for row in cursor.fetchall():
            bl_tag = ' [BASELINE]' if row[4] else ''
            print('  study_id={} | {} | {} | {} cases | {}{}'.format(row[0], row[1], row[2], row[3], row[5], bl_tag))
    except Exception:
        pass

    # Show baseline
    try:
        cursor.execute(
            'SELECT c.case_id, c.case_name, s.study_name FROM cases c '
            'JOIN studies s ON c.study_id = s.study_id WHERE s.is_baseline = 1 AND c.is_baseline = 1')
        baseline = cursor.fetchone()
        if baseline:
            print('Baseline: case_id={}, name={}, study={}'.format(*baseline))
        else:
            print('WARNING: No baseline found in database')
    except Exception:
        pass

    conn.close()


if __name__ == '__main__':
    main()
