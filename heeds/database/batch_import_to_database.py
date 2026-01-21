"""
batch_import_to_database.py - Workflow 3.5: Batch import HEEDS results
"""
import sqlite3
import os
import argparse
import re
import numpy as np
from pathlib import Path

DEFAULT_DB_PATH = r'D:\thesis_database\thesis_results.db'

def parse_pch_file(pch_path):
    data = {'acceleration': {}, 'displacement': {}}
    dof_mapping = {3: 'T1', 4: 'T2', 5: 'T3', 6: 'R1', 7: 'R2', 8: 'R3'}
    with open(pch_path, 'r') as f:
        lines = f.readlines()
    current_type, current_node, current_dof, current_data = None, None, None, []
    for line in lines:
        if line.startswith('$ACCE'):
            if current_type and current_node and current_dof and current_data:
                data[current_type][(current_node, current_dof)] = current_data
            parts = line.split()
            if len(parts) >= 5:
                current_type, current_node = 'acceleration', int(parts[2])
                current_dof, current_data = dof_mapping.get(int(parts[3]), 'DOF'), []
        elif line.startswith('$DISP'):
            if current_type and current_node and current_dof and current_data:
                data[current_type][(current_node, current_dof)] = current_data
            parts = line.split()
            if len(parts) >= 5:
                current_type, current_node = 'displacement', int(parts[2])
                current_dof, current_data = dof_mapping.get(int(parts[3]), 'DOF'), []
        elif line.startswith('$'):
            if current_type and current_node and current_dof and current_data:
                data[current_type][(current_node, current_dof)] = current_data
            current_type, current_data = None, []
        elif current_type and line.strip():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    current_data.append((float(parts[1]), float(parts[2])))
                except:
                    pass
    if current_type and current_node and current_dof and current_data:
        data[current_type][(current_node, current_dof)] = current_data
    return data

def nastran_float(s):
    s = s.strip()
    s = re.sub(r'(\d)\.([+-])(\d)', r'\1.E\2\3', s)
    s = re.sub(r'(\d\.\d+)([+-])(\d)', r'\1E\2\3', s)
    s = re.sub(r'(\d)([+-])(\d)', r'\1E\2\3', s)
    return float(s)

def parse_bush_file(bush_path):
    parameters = {}
    if not os.path.exists(bush_path):
        return parameters
    with open(bush_path, 'r') as f:
        lines = f.readlines()
    for line in lines:
        if line.startswith('$'):
            continue
        if line.startswith('PBUSH'):
            parts = line.split()
            if len(parts) >= 5:
                try:
                    elem_id = int(parts[1])
                    k4 = nastran_float(parts[-3])
                    k5 = nastran_float(parts[-2])
                    k6 = nastran_float(parts[-1])
                    parameters[elem_id] = {'K4': k4, 'K5': k5, 'K6': k6}
                except Exception as e:
                    print(f"  Warning: {e}")
    return parameters

def find_peaks(freq_psd_list, n_peaks=3):
    if not freq_psd_list or len(freq_psd_list) < 3:
        return [(None, None)] * n_peaks
    frequencies = np.array([x[0] for x in freq_psd_list])
    psd_values = np.array([x[1] for x in freq_psd_list])
    peaks = []
    for i in range(1, len(psd_values) - 1):
        if psd_values[i] > psd_values[i-1] and psd_values[i] > psd_values[i+1]:
            peaks.append((frequencies[i], psd_values[i]))
    if not peaks:
        max_idx = np.argmax(psd_values)
        peaks.append((frequencies[max_idx], psd_values[max_idx]))
    peaks.sort(key=lambda x: x[1], reverse=True)
    peaks = peaks[:n_peaks]
    while len(peaks) < n_peaks:
        peaks.append((None, None))
    return peaks

def calculate_area(freq_psd_list):
    if len(freq_psd_list) < 2:
        return 0.0
    frequencies = np.array([x[0] for x in freq_psd_list])
    psd_values = np.array([x[1] for x in freq_psd_list])
    return float(np.trapz(psd_values, frequencies))

def get_or_create_study(conn, study_name):
    cursor = conn.cursor()
    cursor.execute('SELECT study_id FROM studies WHERE study_name = ?', (study_name,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute('INSERT INTO studies (study_name) VALUES (?)', (study_name,))
    conn.commit()
    return cursor.lastrowid

def reset_study_data(conn, study_id):
    cursor = conn.cursor()
    cursor.execute('SELECT case_id FROM cases WHERE study_id = ?', (study_id,))
    case_ids = [row[0] for row in cursor.fetchall()]
    if case_ids:
        ph = ','.join('?' * len(case_ids))
        cursor.execute(f'DELETE FROM psd_data WHERE case_id IN ({ph})', case_ids)
        cursor.execute(f'DELETE FROM peaks WHERE case_id IN ({ph})', case_ids)
        cursor.execute(f'DELETE FROM parameters WHERE case_id IN ({ph})', case_ids)
        cursor.execute('DELETE FROM cases WHERE study_id = ?', (study_id,))
    conn.commit()
    return len(case_ids)

def insert_case(conn, study_id, design_num, pch_file):
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cases (study_id, case_name, case_number, is_baseline, pch_file) VALUES (?, ?, ?, ?, ?)',
                   (study_id, f"Design_{design_num}", design_num, False, pch_file))
    conn.commit()
    return cursor.lastrowid

def insert_parameters_batch(conn, case_id, parameters):
    cursor = conn.cursor()
    rows = [(case_id, eid, s['K4'], s['K5'], s['K6']) for eid, s in parameters.items()]
    cursor.executemany('INSERT INTO parameters (case_id, element_id, K4, K5, K6) VALUES (?, ?, ?, ?, ?)', rows)
    conn.commit()
    return len(rows)

def insert_psd_data_batch(conn, case_id, psd_data):
    cursor = conn.cursor()
    rows = []
    for dt in ['acceleration', 'displacement']:
        for (node_id, dof), fpl in psd_data[dt].items():
            for freq, psd in fpl:
                rows.append((case_id, node_id, dof, freq, psd, dt))
    cursor.executemany('INSERT INTO psd_data (case_id, node_id, dof, frequency, psd_value, data_type) VALUES (?, ?, ?, ?, ?, ?)', rows)
    conn.commit()
    return len(rows)

def insert_peaks_batch(conn, case_id, psd_data):
    cursor = conn.cursor()
    rows = []
    for dt in ['acceleration', 'displacement']:
        for (node_id, dof), fpl in psd_data[dt].items():
            area = calculate_area(fpl)
            peaks = find_peaks(fpl, 3)
            rows.append((case_id, node_id, dof, dt, area, peaks[0][0], peaks[0][1], peaks[1][0], peaks[1][1], peaks[2][0], peaks[2][1]))
    cursor.executemany('INSERT INTO peaks (case_id, node_id, dof, data_type, area, peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', rows)
    conn.commit()
    return len(rows)

def scan_post0_folder(post0_dir):
    designs = []
    post0_path = Path(post0_dir)
    if not post0_path.exists():
        print(f"Error: not found: {post0_dir}")
        return designs
    for df in sorted(post0_path.glob('Design*')):
        if not df.is_dir():
            continue
        match = re.search(r'Design(\d+)', df.name)
        if not match:
            continue
        dn = int(match.group(1))
        af = df / 'Analysis_1'
        if not af.exists():
            continue
        bp, pp = af / 'Bush.blk', af / 'randombeamx.pch'
        if not pp.exists():
            continue
        designs.append((dn, str(bp), str(pp)))
    return designs

def batch_import(post0_dir, study_name, db_path, reset_study=False, dry_run=False):
    print("=" * 60)
    print("  WORKFLOW 3.5: BATCH DATABASE IMPORT")
    print("=" * 60)
    print(f"POST_0: {post0_dir}")
    print(f"Study: {study_name}")
    print(f"Database: {db_path}")
    print("=" * 60)
    designs = scan_post0_folder(post0_dir)
    if not designs:
        print("No designs found!")
        return False
    print(f"Found {len(designs)} designs")
    dwb = sum(1 for d in designs if os.path.exists(d[1]))
    print(f"  - {dwb} with Bush.blk")
    if dry_run:
        print("\n[DRY RUN]")
        for dn, bp, pp in designs:
            bs = "Y" if os.path.exists(bp) else "N"
            print(f"  Design {dn}: Bush [{bs}], PCH [Y]")
        return True
    if not os.path.exists(db_path):
        print(f"Error: DB not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        study_id = get_or_create_study(conn, study_name)
        print(f"\nStudy ID: {study_id}")
        if reset_study:
            d = reset_study_data(conn, study_id)
            print(f"Reset: deleted {d} cases")
        tpsd, tpeak, tparam = 0, 0, 0
        print(f"\nImporting...")
        for i, (dn, bp, pp) in enumerate(designs, 1):
            print(f"[{i}/{len(designs)}] Design {dn}...", end=" ", flush=True)
            cid = insert_case(conn, study_id, dn, pp)
            if os.path.exists(bp):
                params = parse_bush_file(bp)
                if params:
                    tparam += insert_parameters_batch(conn, cid, params)
            psd = parse_pch_file(pp)
            tpsd += insert_psd_data_batch(conn, cid, psd)
            tpeak += insert_peaks_batch(conn, cid, psd)
            print("OK")
        print(f"\nDone! Cases:{len(designs)} Params:{tparam} PSD:{tpsd:,} Peaks:{tpeak}")
        print(f"DB size: {os.path.getsize(db_path)/1024/1024:.2f} MB")
        return True
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--post0_dir', required=True)
    p.add_argument('--study', required=True)
    p.add_argument('--db_path', default=DEFAULT_DB_PATH)
    p.add_argument('--reset_study', action='store_true')
    p.add_argument('--dry_run', action='store_true')
    a = p.parse_args()
    return 0 if batch_import(a.post0_dir, a.study, a.db_path, a.reset_study, a.dry_run) else 1

if __name__ == "__main__":
    exit(main())
