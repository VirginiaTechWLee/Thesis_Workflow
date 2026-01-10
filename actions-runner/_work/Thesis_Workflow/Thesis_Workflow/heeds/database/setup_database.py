"""
setup_database.py
Creates the SQLite database schema for thesis PSD data storage.

Run once to initialize the database, or run again to reset (will prompt for confirmation).

Usage:
    python setup_database.py
    python setup_database.py --reset  # Force reset without prompt
    python setup_database.py --db_path D:\thesis_database\thesis_results.db
"""

import sqlite3
import os
import argparse
from datetime import datetime


def create_schema(conn):
    """Create all database tables."""
    cursor = conn.cursor()
    
    # Studies table - groups of HEEDS runs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS studies (
            study_id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Cases table - individual analysis runs
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cases (
            case_id INTEGER PRIMARY KEY AUTOINCREMENT,
            study_id INTEGER,
            case_name TEXT NOT NULL,
            case_number INTEGER,
            is_baseline BOOLEAN DEFAULT FALSE,
            status TEXT DEFAULT 'completed',
            pch_file TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (study_id) REFERENCES studies(study_id),
            UNIQUE(study_id, case_number)
        )
    ''')
    
    # Parameters table - CBUSH stiffness values for each case
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            K4 REAL,
            K5 REAL,
            K6 REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            UNIQUE(case_id, element_id)
        )
    ''')
    
    # Full PSD data table - all frequency points
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS psd_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            dof TEXT NOT NULL,
            frequency REAL NOT NULL,
            psd_value REAL NOT NULL,
            data_type TEXT DEFAULT 'acceleration',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(case_id)
        )
    ''')
    
    # Peaks summary table - top 3 peaks per node/DOF (for quick queries)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS peaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            node_id INTEGER NOT NULL,
            dof TEXT NOT NULL,
            data_type TEXT DEFAULT 'acceleration',
            area REAL,
            peak1_freq REAL,
            peak1_psd REAL,
            peak2_freq REAL,
            peak2_psd REAL,
            peak3_freq REAL,
            peak3_psd REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (case_id) REFERENCES cases(case_id),
            UNIQUE(case_id, node_id, dof, data_type)
        )
    ''')
    
    # Create indexes for faster queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_psd_case ON psd_data(case_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_psd_node ON psd_data(node_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_psd_case_node_dof ON psd_data(case_id, node_id, dof)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_peaks_case ON peaks(case_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_parameters_case ON parameters(case_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cases_study ON cases(study_id)')
    
    conn.commit()
    print("Database schema created successfully.")


def reset_database(conn):
    """Drop all tables and recreate schema."""
    cursor = conn.cursor()
    
    tables = ['psd_data', 'peaks', 'parameters', 'cases', 'studies']
    for table in tables:
        cursor.execute(f'DROP TABLE IF EXISTS {table}')
    
    conn.commit()
    print("All tables dropped.")
    create_schema(conn)


def get_db_stats(conn):
    """Print database statistics."""
    cursor = conn.cursor()
    
    print("\n=== Database Statistics ===")
    
    tables = ['studies', 'cases', 'parameters', 'psd_data', 'peaks']
    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            print(f"  {table}: {count:,} rows")
        except sqlite3.OperationalError:
            print(f"  {table}: (table not found)")
    
    # Show studies summary
    try:
        cursor.execute('''
            SELECT s.study_name, COUNT(c.case_id) as case_count
            FROM studies s
            LEFT JOIN cases c ON s.study_id = c.study_id
            GROUP BY s.study_id
        ''')
        studies = cursor.fetchall()
        if studies:
            print("\n=== Studies ===")
            for study_name, case_count in studies:
                print(f"  {study_name}: {case_count} cases")
    except sqlite3.OperationalError:
        pass


def main():
    parser = argparse.ArgumentParser(description='Setup thesis database')
    parser.add_argument('--db_path', type=str, 
                        default='D:\\thesis_database\\thesis_results.db',
                        help='Path to database file')
    parser.add_argument('--reset', action='store_true',
                        help='Reset database (drop all tables)')
    args = parser.parse_args()
    
    # Create directory if needed
    db_dir = os.path.dirname(args.db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"Created directory: {db_dir}")
    
    # Check if database exists
    db_exists = os.path.exists(args.db_path)
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    if args.reset:
        if db_exists:
            confirm = input(f"Are you sure you want to reset {args.db_path}? This will DELETE ALL DATA. (yes/no): ")
            if confirm.lower() == 'yes':
                reset_database(conn)
            else:
                print("Reset cancelled.")
        else:
            create_schema(conn)
    elif db_exists:
        print(f"Database exists: {args.db_path}")
        get_db_stats(conn)
        print("\nTo reset, run with --reset flag")
    else:
        print(f"Creating new database: {args.db_path}")
        create_schema(conn)
    
    conn.close()
    print(f"\nDatabase location: {args.db_path}")


if __name__ == "__main__":
    main()
