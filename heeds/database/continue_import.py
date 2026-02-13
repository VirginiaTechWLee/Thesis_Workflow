import sqlite3
import os
import re
import numpy as np
from pathlib import Path

DB_PATH = r'D:\thesis_database\thesis_results.db'
POST0 = r'C:\Users\waynelee\Documents\full_sweep_Study_1\POST_0'

def nastran_float(s):
    s = s.strip()
    s = re.sub(r'(\d)\.([+-])(\d)', r'\1.E\2\3', s)
    s = re.sub(r'(\d\.\d+)([+-])(\d)', r'\1E\2\3', s)
    s = re.sub(r'(\d)([+-])(\d)', r'\1E\2\3', s)
    return float(s)

def parse_bush_file(bush_path):
    parameters = {}
    with open(bush_path, 'r') as f:
        for line in f:
            if line.startswith('PBUSH'):
                parts = line.split()
                if len(parts) >= 5:
                    elem_id = int(parts[1])
                    k4 = nastran_float(parts[-3])
                    k5 = nastran_float(parts[-2])
                    k6 = nastran_float(parts[-1])
                    parameters[elem_id] = {'K4': k4, 'K5': k5, 'K6': k6}
    return parameters

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

def find_peaks(fpl, n=3):
    if len(fpl) < 3:
        return [(None, None)] * n
    freqs = np.array([x[0] for x in fpl])
    psds = np.array([x[1] for x in fpl])
    peaks = []
    for i in range(1, len(psds) - 1):
        if psds[i] > psds[i-1] and psds[i] > psds[i+1]:
            peaks.append((freqs[i], psds[i]))
    if not peaks:
        idx = np.argmax(psds)
        peaks.append((freqs[idx], psds[idx]))
    peaks.sort(key=lambda x: x[1], reverse=True)
    while len(peaks) < n:
        peaks.append((None, None))
    return peaks[:n]

def calc_area(fpl):
    if len(fpl) < 2:
        return 0.0
    return float(np.trapezoid(np.array([x[1] for x in fpl]), np.array([x[0] for x in fpl])))

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Get study_id for full_sweep
    c.execute('SELECT study_id FROM studies WHERE study_name = ?', ('full_sweep',))
    row = c.fetchone()
    if row:
        study_id = row[0]
    else:
        c.execute('INSERT INTO studies (study_name) VALUES (?)', ('full_sweep',))
        study_id = c.lastrowid
        conn.commit()

    # Get already imported
    c.execute('SELECT case_number FROM cases WHERE study_id = ?', (study_id,))
    imported = set(r[0] for r in c.fetchall())
    print(f'Already imported: {len(imported)}')

    # Find designs to import
    post0 = Path(POST0)
    to_import = []
    for d in sorted(post0.glob('Design*')):
        m = re.search(r'Design(\d+)', d.name)
        if not m:
            continue
        dn = int(m.group(1))
        if dn in imported:
            continue
        bush = d / 'Analysis_1' / 'Bush.blk'
        pch = d / 'Analysis_1' / 'randombeamx.pch'
        if bush.exists() and pch.exists():
            to_import.append((dn, str(bush), str(pch)))

    print(f'To import: {len(to_import)}')
    
    if not to_import:
        print('Nothing to import!')
        conn.close()
        return

    count = 0
    for dn, bush_path, pch_path in to_import:
        try:
            c.execute('INSERT INTO cases (study_id, case_name, case_number, is_baseline, pch_file) VALUES (?, ?, ?, ?, ?)',
                      (study_id, f'Design_{dn}', dn, False, pch_path))
            case_id = c.lastrowid
            
            params = parse_bush_file(bush_path)
            for eid, vals in params.items():
                c.execute('INSERT INTO parameters (case_id, element_id, K4, K5, K6) VALUES (?, ?, ?, ?, ?)',
                          (case_id, eid, vals['K4'], vals['K5'], vals['K6']))
            
            psd = parse_pch_file(pch_path)
            for dtype in ['acceleration', 'displacement']:
                for (node_id, dof), fpl in psd[dtype].items():
                    for freq, psd_val in fpl:
                        c.execute('INSERT INTO psd_data (case_id, node_id, dof, frequency, psd_value, data_type) VALUES (?, ?, ?, ?, ?, ?)',
                                  (case_id, node_id, dof, freq, psd_val, dtype))
                    area = calc_area(fpl)
                    peaks = find_peaks(fpl, 3)
                    c.execute('INSERT INTO peaks (case_id, node_id, dof, data_type, area, peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                              (case_id, node_id, dof, dtype, area, peaks[0][0], peaks[0][1], peaks[1][0], peaks[1][1], peaks[2][0], peaks[2][1]))
            
            conn.commit()
            count += 1
            print(f'[{count}/{len(to_import)}] Design {dn} OK')
        except Exception as e:
            print(f'Design {dn} ERROR: {e}')
            conn.rollback()

    print(f'Done! Imported {count} new designs')
    conn.close()

if __name__ == '__main__':
    main()
