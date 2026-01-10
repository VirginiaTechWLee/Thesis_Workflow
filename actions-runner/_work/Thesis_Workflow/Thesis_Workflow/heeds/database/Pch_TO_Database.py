"""
Pch_TO_Database.py
Parses Nastran PCH files and inserts full PSD data into SQLite database.

This script extracts ALL frequency points (not just peaks) for comprehensive
machine learning analysis of bolt looseness detection.

Usage:
    # Insert baseline case
    python Pch_TO_Database.py --pch randombeamx.pch --study "Bolt_Looseness_Study_1" --case_name "baseline" --case_number 0 --is_baseline
    
    # Insert HEEDS case
    python Pch_TO_Database.py --pch randombeamx.pch --study "Bolt_Looseness_Study_1" --case_name "case_045" --case_number 45
    
    # With Bush.blk parameters
    python Pch_TO_Database.py --pch randombeamx.pch --study "Bolt_Looseness_Study_1" --case_name "case_045" --case_number 45 --bush_file Bush.blk
    
    # Replace existing case
    python Pch_TO_Database.py --pch randombeamx.pch --study "Bolt_Looseness_Study_1" --case_name "baseline" --case_number 0 --is_baseline --replace
"""

import sqlite3
import os
import argparse
import re
import numpy as np
from datetime import datetime


# Default database path
DEFAULT_DB_PATH = 'D:\\thesis_database\\thesis_results.db'


def parse_pch_file(pch_path):
    """
    Parse Nastran PCH file and extract all PSD data.
    
    Returns:
        dict: {
            'acceleration': {(node_id, dof): [(freq, psd), ...]},
            'displacement': {(node_id, dof): [(freq, psd), ...]}
        }
    """
    data = {
        'acceleration': {},
        'displacement': {}
    }
    
    dof_mapping = {
        3: 'T1', 4: 'T2', 5: 'T3',
        6: 'R1', 7: 'R2', 8: 'R3'
    }
    
    with open(pch_path, 'r') as f:
        lines = f.readlines()
    
    current_type = None
    current_node = None
    current_dof = None
    current_data = []
    
    for line in lines:
        # Check for ACCE or DISP header
        if line.startswith('$ACCE'):
            # Save previous data block if exists
            if current_type and current_node and current_dof and current_data:
                key = (current_node, current_dof)
                data[current_type][key] = current_data
            
            # Parse header: $ACCE  0  node_id  dof_num  ...
            parts = line.split()
            if len(parts) >= 5:
                current_type = 'acceleration'
                current_node = int(parts[2])
                dof_num = int(parts[3])
                current_dof = dof_mapping.get(dof_num, f'DOF{dof_num}')
                current_data = []
                
        elif line.startswith('$DISP'):
            # Save previous data block if exists
            if current_type and current_node and current_dof and current_data:
                key = (current_node, current_dof)
                data[current_type][key] = current_data
            
            # Parse header
            parts = line.split()
            if len(parts) >= 5:
                current_type = 'displacement'
                current_node = int(parts[2])
                dof_num = int(parts[3])
                current_dof = dof_mapping.get(dof_num, f'DOF{dof_num}')
                current_data = []
                
        elif line.startswith('$'):
            # Other header line, save current data
            if current_type and current_node and current_dof and current_data:
                key = (current_node, current_dof)
                data[current_type][key] = current_data
            current_type = None
            current_node = None
            current_dof = None
            current_data = []
            
        elif current_type and line.strip():
            # Data line: index  frequency  psd_value  line_number
            parts = line.split()
            if len(parts) >= 3:
                try:
                    frequency = float(parts[1])
                    psd_value = float(parts[2])
                    current_data.append((frequency, psd_value))
                except (ValueError, IndexError):
                    pass
    
    # Save last data block
    if current_type and current_node and current_dof and current_data:
        key = (current_node, current_dof)
        data[current_type][key] = current_data
    
    return data


def nastran_float(s):
    """
    Convert Nastran shorthand notation to Python float.
    Examples:
        '1.+8' -> 1.0e8
        '1.-8' -> 1.0e-8
        '1.5+6' -> 1.5e6
        '1.0E+8' -> 1.0e8 (already standard)
    """
    s = s.strip()
    # Replace shorthand with decimal: 1.+8 -> 1.E+8, 1.-8 -> 1.E-8
    s = re.sub(r'(\d)\.([+-])(\d)', r'\1.E\2\3', s)
    # Replace shorthand with decimal and digits: 1.5+6 -> 1.5E+6
    s = re.sub(r'(\d\.\d+)([+-])(\d)', r'\1E\2\3', s)
    # Replace shorthand without decimal: 1+8 -> 1E+8
    s = re.sub(r'(\d)([+-])(\d)', r'\1E\2\3', s)
    return float(s)


def parse_bush_file(bush_path):
    """
    Parse Bush.blk file to extract CBUSH stiffness parameters.
    Handles Nastran shorthand notation (1.+8 = 1.0E+8).
    
    Returns:
        dict: {element_id: {'K4': value, 'K5': value, 'K6': value}}
    """
    parameters = {}
    
    if not os.path.exists(bush_path):
        print(f"Warning: Bush file not found: {bush_path}")
        return parameters
    
    with open(bush_path, 'r') as f:
        content = f.read()
    
    # Parse PBUSH cards - format varies, this handles common patterns
    # PBUSH  ID  K  K1  K2  K3  K4  K5  K6
    pbush_pattern = r'PBUSH\s+(\d+)\s+K\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)'
    
    for match in re.finditer(pbush_pattern, content, re.IGNORECASE):
        elem_id = int(match.group(1))
        # K1, K2, K3 are translational, K4, K5, K6 are rotational
        try:
            parameters[elem_id] = {
                'K4': nastran_float(match.group(5)),
                'K5': nastran_float(match.group(6)),
                'K6': nastran_float(match.group(7))
            }
        except ValueError as e:
            print(f"Warning: Could not parse stiffness for element {elem_id}: {e}")
    
    return parameters


def find_peaks(freq_psd_list, n_peaks=3):
    """Find top N peaks in PSD data."""
    if not freq_psd_list:
        return []
    
    frequencies = np.array([x[0] for x in freq_psd_list])
    psd_values = np.array([x[1] for x in freq_psd_list])
    
    # Simple peak finding - local maxima
    peaks = []
    for i in range(1, len(psd_values) - 1):
        if psd_values[i] > psd_values[i-1] and psd_values[i] > psd_values[i+1]:
            peaks.append((frequencies[i], psd_values[i]))
    
    # Sort by PSD value (descending) and take top N
    peaks.sort(key=lambda x: x[1], reverse=True)
    return peaks[:n_peaks]


def calculate_area(freq_psd_list):
    """Calculate area under PSD curve using trapezoidal rule."""
    if len(freq_psd_list) < 2:
        return 0.0
    
    frequencies = np.array([x[0] for x in freq_psd_list])
    psd_values = np.array([x[1] for x in freq_psd_list])
    
    return np.trapezoid(psd_values, frequencies)


def get_or_create_study(conn, study_name, study_type='manual', description=None):
    """Get study_id or create new study."""
    cursor = conn.cursor()
    
    cursor.execute('SELECT study_id FROM studies WHERE study_name = ?', (study_name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    
    cursor.execute(
        'INSERT INTO studies (study_name, study_type, description) VALUES (?, ?, ?)',
        (study_name, study_type, description))
    conn.commit()
    return cursor.lastrowid


def delete_case_data(conn, case_id):
    """Delete all data for a case (for replacement)."""
    cursor = conn.cursor()
    cursor.execute('DELETE FROM psd_data WHERE case_id = ?', (case_id,))
    cursor.execute('DELETE FROM peaks WHERE case_id = ?', (case_id,))
    cursor.execute('DELETE FROM parameters WHERE case_id = ?', (case_id,))
    conn.commit()


def insert_case(conn, study_id, case_name, case_number, is_baseline, pch_file, replace=False):
    """Insert or get case record."""
    cursor = conn.cursor()
    
    # Check if case exists
    cursor.execute(
        'SELECT case_id FROM cases WHERE study_id = ? AND case_number = ?',
        (study_id, case_number)
    )
    result = cursor.fetchone()
    
    if result:
        case_id = result[0]
        if replace:
            print(f"Replacing existing case {case_number} (case_id={case_id})")
            delete_case_data(conn, case_id)
            # Update case record
            cursor.execute(
                'UPDATE cases SET case_name = ?, pch_file = ?, created_at = CURRENT_TIMESTAMP WHERE case_id = ?',
                (case_name, pch_file, case_id)
            )
            conn.commit()
        else:
            print(f"Case {case_number} already exists (case_id={case_id}). Use --replace to overwrite.")
            return None
        return case_id
    
    # Insert new case
    cursor.execute(
        '''INSERT INTO cases (study_id, case_name, case_number, is_baseline, pch_file)
           VALUES (?, ?, ?, ?, ?)''',
        (study_id, case_name, case_number, is_baseline, pch_file)
    )
    conn.commit()
    return cursor.lastrowid


def insert_psd_data(conn, case_id, psd_data):
    """Insert full PSD data into database."""
    cursor = conn.cursor()
    
    rows_inserted = 0
    for data_type in ['acceleration', 'displacement']:
        for (node_id, dof), freq_psd_list in psd_data[data_type].items():
            # Prepare batch insert
            rows = [
                (case_id, node_id, dof, freq, psd, data_type)
                for freq, psd in freq_psd_list
            ]
            
            cursor.executemany(
                '''INSERT INTO psd_data (case_id, node_id, dof, frequency, psd_value, data_type)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                rows
            )
            rows_inserted += len(rows)
    
    conn.commit()
    return rows_inserted


def insert_peaks(conn, case_id, psd_data):
    """Calculate and insert peak summary data."""
    cursor = conn.cursor()
    
    for data_type in ['acceleration', 'displacement']:
        for (node_id, dof), freq_psd_list in psd_data[data_type].items():
            # Calculate area
            area = calculate_area(freq_psd_list)
            
            # Find peaks
            peaks = find_peaks(freq_psd_list, n_peaks=3)
            
            # Pad with None if fewer than 3 peaks
            while len(peaks) < 3:
                peaks.append((None, None))
            
            cursor.execute(
                '''INSERT INTO peaks 
                   (case_id, node_id, dof, data_type, area, 
                    peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (case_id, node_id, dof, data_type, area,
                 peaks[0][0], peaks[0][1],
                 peaks[1][0], peaks[1][1],
                 peaks[2][0], peaks[2][1])
            )
    
    conn.commit()


def insert_parameters(conn, case_id, parameters):
    """Insert CBUSH stiffness parameters."""
    cursor = conn.cursor()
    
    for elem_id, stiffness in parameters.items():
        cursor.execute(
            '''INSERT INTO parameters (case_id, element_id, K4, K5, K6)
               VALUES (?, ?, ?, ?, ?)''',
            (case_id, elem_id, stiffness['K4'], stiffness['K5'], stiffness['K6'])
        )
    
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description='Parse PCH file and insert into database')
    parser.add_argument('--pch', type=str, required=True, help='Path to PCH file')
    parser.add_argument('--study', type=str, required=True, help='Study name (e.g., "Bolt_Looseness_Study_1")')
    parser.add_argument('--study_type', type=str, default='manual', help='Study type: sweep, doe, monte_carlo, manual')
    parser.add_argument('--case_name', type=str, required=True, help='Case name (e.g., "baseline", "case_045")')
    parser.add_argument('--case_number', type=int, required=True, help='Case number (0 for baseline)')
    parser.add_argument('--is_baseline', action='store_true', help='Mark as baseline case')
    parser.add_argument('--bush_file', type=str, default=None, help='Path to Bush.blk file for parameters')
    parser.add_argument('--db_path', type=str, default=DEFAULT_DB_PATH, help='Path to database')
    parser.add_argument('--replace', action='store_true', help='Replace existing case data')
    parser.add_argument('--description', type=str, default=None, help='Study description')
    
    args = parser.parse_args()
    
    # Validate PCH file exists
    if not os.path.exists(args.pch):
        print(f"Error: PCH file not found: {args.pch}")
        return 1
    
    # Check database exists
    if not os.path.exists(args.db_path):
        print(f"Error: Database not found: {args.db_path}")
        print("Run setup_database.py first to create the database.")
        return 1
    
    # Connect to database
    conn = sqlite3.connect(args.db_path)
    
    try:
        # Get or create study
        study_id = get_or_create_study(conn, args.study, args.study_type, args.description)
        print(f"Study: {args.study} (study_id={study_id})")
        
        # Insert case
        case_id = insert_case(
            conn, study_id, args.case_name, args.case_number, 
            args.is_baseline, args.pch, args.replace
        )
        
        if case_id is None:
            conn.close()
            return 1
        
        print(f"Case: {args.case_name} (case_id={case_id}, case_number={args.case_number})")
        
        # Parse PCH file
        print(f"Parsing PCH file: {args.pch}")
        psd_data = parse_pch_file(args.pch)
        
        # Count what we found
        acce_count = len(psd_data['acceleration'])
        disp_count = len(psd_data['displacement'])
        print(f"Found {acce_count} acceleration channels, {disp_count} displacement channels")
        
        # Insert full PSD data
        print("Inserting full PSD data...")
        rows_inserted = insert_psd_data(conn, case_id, psd_data)
        print(f"Inserted {rows_inserted:,} PSD data points")
        
        # Insert peaks summary
        print("Calculating and inserting peaks summary...")
        insert_peaks(conn, case_id, psd_data)
        
        # Parse and insert Bush.blk parameters if provided
        if args.bush_file:
            print(f"Parsing Bush file: {args.bush_file}")
            parameters = parse_bush_file(args.bush_file)
            if parameters:
                insert_parameters(conn, case_id, parameters)
                print(f"Inserted parameters for {len(parameters)} CBUSH elements")
        
        print("\nSuccess!")
        print(f"Database: {args.db_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        conn.close()
    
    return 0


if __name__ == "__main__":
    exit(main())
