"""
batch_import_to_database.py - Workflow 3.5: Batch import HEEDS results
"""
import sqlite3
import os
import argparse

# Force unbuffered output so progress is visible in real-time (logs, MCP, CI)
os.environ["PYTHONUNBUFFERED"] = "1"
import re
from pathlib import Path

DEFAULT_DB_PATH = r'D:\thesis_database\thesis_results.db'

def parse_pch_file(pch_path):
    """Parse a Nastran PCH (punch) file.

    Returns dict with keys:
        'acceleration'  -> {(node_id, dof_name): [(freq, psd), ...]}
        'displacement'  -> {(node_id, dof_name): [(freq, psd), ...]}
        'force'         -> {(element_id, dof_name): [(freq, psd), ...]}
    """
    data = {'acceleration': {}, 'displacement': {}, 'force': {}}

    # Grid-point DOF mapping (column 4 in $ACCE/$DISP header)
    grid_dof_map = {3: 'T1', 4: 'T2', 5: 'T3', 6: 'R1', 7: 'R2', 8: 'R3'}

    # CBUSH element-force DOF mapping (column 4 in $EL FOR header)
    # Nastran XYPUNCH component codes: 2=Fx, 3=Fy, 4=Fz, 5=Mx, 6=My, 7=Mz
    force_dof_map = {2: 'Fx', 3: 'Fy', 4: 'Fz', 5: 'Mx', 6: 'My', 7: 'Mz'}

    with open(pch_path, 'r') as f:
        lines = f.readlines()

    current_type, current_id, current_dof, current_data = None, None, None, []

    def _flush():
        """Save the current curve into data dict."""
        if current_type and current_id is not None and current_dof and current_data:
            data[current_type][(current_id, current_dof)] = current_data

    for line in lines:
        if line.startswith('$ACCE'):
            _flush()
            parts = line.split()
            if len(parts) >= 5:
                current_type = 'acceleration'
                current_id = int(parts[2])
                current_dof = grid_dof_map.get(int(parts[3]), 'DOF')
                current_data = []
        elif line.startswith('$DISP'):
            _flush()
            parts = line.split()
            if len(parts) >= 5:
                current_type = 'displacement'
                current_id = int(parts[2])
                current_dof = grid_dof_map.get(int(parts[3]), 'DOF')
                current_data = []
        elif line.startswith('$EL FOR'):
            _flush()
            parts = line.split()
            # $EL FOR splits into: ['$EL', 'FOR', subcase, elem_id, component, ...]
            if len(parts) >= 6:
                current_type = 'force'
                current_id = int(parts[3])           # element ID
                current_dof = force_dof_map.get(int(parts[4]), 'DOF')
                current_data = []
        elif line.startswith('$'):
            # Any other $ header — flush and reset
            _flush()
            current_type, current_data = None, []
        elif current_type and line.strip():
            parts = line.split()
            if len(parts) >= 3:
                try:
                    current_data.append((float(parts[1]), float(parts[2])))
                except Exception:
                    pass

    _flush()  # don't forget the last curve
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
    """Find top N peaks in a PSD curve (pure Python — no numpy)."""
    if not freq_psd_list or len(freq_psd_list) < 3:
        return [(None, None)] * n_peaks
    frequencies = [float(x[0]) for x in freq_psd_list]
    psd_values = [float(x[1]) for x in freq_psd_list]
    peaks = []
    for i in range(1, len(psd_values) - 1):
        if psd_values[i] > psd_values[i - 1] and psd_values[i] > psd_values[i + 1]:
            peaks.append((frequencies[i], psd_values[i]))
    if not peaks:
        # No local maxima — use global max
        max_val = max(psd_values)
        max_idx = psd_values.index(max_val)
        peaks.append((frequencies[max_idx], max_val))
    peaks.sort(key=lambda x: x[1], reverse=True)
    peaks = peaks[:n_peaks]
    while len(peaks) < n_peaks:
        peaks.append((None, None))
    return peaks

def calculate_area(freq_psd_list):
    """Trapezoidal integration of a PSD curve (pure Python — no numpy)."""
    if len(freq_psd_list) < 2:
        return 0.0
    frequencies = [float(x[0]) for x in freq_psd_list]
    psd_values = [float(x[1]) for x in freq_psd_list]
    area = 0.0
    for i in range(1, len(frequencies)):
        area += 0.5 * (psd_values[i] + psd_values[i - 1]) * (frequencies[i] - frequencies[i - 1])
    return area

def apply_performance_pragmas(conn):
    """Apply SQLite pragmas for fast bulk inserts. Call once after connect."""
    conn.execute('PRAGMA synchronous = NORMAL')  # fsync at critical moments — safe + fast
    conn.execute('PRAGMA journal_mode = DELETE')  # rollback journal — most compatible
    conn.execute('PRAGMA cache_size = -32768')   # 32 MB page cache (conservative)
    conn.execute('PRAGMA temp_store = MEMORY')

def get_or_create_study(conn, study_name):
    cursor = conn.cursor()
    cursor.execute('SELECT study_id FROM studies WHERE study_name = ?', (study_name,))
    result = cursor.fetchone()
    if result:
        return result[0]
    cursor.execute('INSERT INTO studies (study_name, is_baseline) VALUES (?, 0)', (study_name,))
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
        cursor.execute(f'DELETE FROM force_psd_data WHERE case_id IN ({ph})', case_ids)
        cursor.execute(f'DELETE FROM force_peaks WHERE case_id IN ({ph})', case_ids)
        cursor.execute(f'DELETE FROM strain_energy WHERE case_id IN ({ph})', case_ids)
        cursor.execute(f'DELETE FROM parameters WHERE case_id IN ({ph})', case_ids)
        cursor.execute('DELETE FROM cases WHERE study_id = ?', (study_id,))
    conn.commit()
    return len(case_ids)

def detect_baseline_design(designs):
    """Detect baseline design: Design1 has all bolts at baseline stiffness.

    In HEEDS sweep studies, Design1 is always the baseline case where all
    variable bolts are at their healthy (maximum) stiffness level.
    Returns the design_number of the baseline, or None if not found.
    """
    if not designs:
        return None
    # Design1 is always baseline in HEEDS parametric studies
    for dn, bp, pp, f06 in designs:
        if dn == 1:
            return dn
    return None


def insert_case(conn, study_id, design_num, pch_file, is_baseline=False):
    cursor = conn.cursor()
    cursor.execute('INSERT INTO cases (study_id, case_name, case_number, is_baseline, pch_file) VALUES (?, ?, ?, ?, ?)',
                   (study_id, f"Design_{design_num}", design_num, is_baseline, pch_file))
    return cursor.lastrowid  # no commit — caller handles transaction

def insert_parameters_batch(conn, case_id, parameters):
    cursor = conn.cursor()
    sql = 'INSERT INTO parameters (case_id, element_id, K4, K5, K6) VALUES (?, ?, ?, ?, ?)'
    for eid, s in parameters.items():
        cursor.execute(sql, (case_id, eid, float(s['K4']), float(s['K5']), float(s['K6'])))
    return len(parameters)  # no commit — caller handles transaction

def insert_psd_data_batch(conn, case_id, psd_data):
    cursor = conn.cursor()
    sql = 'INSERT INTO psd_data (case_id, node_id, dof, frequency, psd_value, data_type) VALUES (?, ?, ?, ?, ?, ?)'
    total = 0
    # Insert per-curve; use execute in loop to avoid Python 3.13 executemany crash
    for dt in ['acceleration', 'displacement']:
        for (node_id, dof), fpl in psd_data[dt].items():
            for freq, psd in fpl:
                cursor.execute(sql, (case_id, node_id, dof, float(freq), float(psd), dt))
                total += 1
    return total  # no commit — caller handles transaction

def insert_peaks_batch(conn, case_id, psd_data):
    cursor = conn.cursor()
    sql = ('INSERT INTO peaks (case_id, node_id, dof, data_type, area, '
           'peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) '
           'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
    total = 0
    for dt in ['acceleration', 'displacement']:
        for (node_id, dof), fpl in psd_data[dt].items():
            area = calculate_area(fpl)
            peaks = find_peaks(fpl, 3)
            cursor.execute(sql, (case_id, node_id, dof, dt, area,
                                 peaks[0][0], peaks[0][1], peaks[1][0], peaks[1][1],
                                 peaks[2][0], peaks[2][1]))
            total += 1
    return total  # no commit — caller handles transaction

def insert_force_psd_batch(conn, case_id, psd_data):
    """Insert CBUSH element force PSD curves into force_psd_data table."""
    cursor = conn.cursor()
    sql = ('INSERT INTO force_psd_data (case_id, element_id, dof, frequency, psd_value, data_type) '
           'VALUES (?, ?, ?, ?, ?, ?)')
    total = 0
    for (element_id, dof), fpl in psd_data.get('force', {}).items():
        for freq, psd in fpl:
            cursor.execute(sql, (case_id, element_id, dof, float(freq), float(psd), 'force'))
            total += 1
    return total


def insert_force_peaks_batch(conn, case_id, psd_data):
    """Insert CBUSH element force peak data into force_peaks table."""
    cursor = conn.cursor()
    sql = ('INSERT INTO force_peaks (case_id, element_id, dof, data_type, area, '
           'peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) '
           'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
    total = 0
    for (element_id, dof), fpl in psd_data.get('force', {}).items():
        area = calculate_area(fpl)
        peaks = find_peaks(fpl, 3)
        cursor.execute(sql, (case_id, element_id, dof, 'force', area,
                             peaks[0][0], peaks[0][1],
                             peaks[1][0], peaks[1][1],
                             peaks[2][0], peaks[2][1]))
        total += 1
    return total


def parse_f06_strain_energy(f06_path):
    """Parse element strain energy from the f06 file.

    SOL 111 writes ESE at every frequency step. Each block has:
      FREQUENCY = X.XXXE+XX
      ELEMENT-TYPE = BUSH/BEAM
      element_id  strain_energy  percent_total  density

    Returns list of dicts: [{element_id, element_type, subcase_id,
                              frequency, strain_energy, percent_total}, ...]
    """
    results = []
    if not os.path.exists(f06_path):
        return results

    current_elem_type = None
    current_subcase = 1
    current_freq = None
    in_ese_block = False

    with open(f06_path, 'r', errors='ignore') as f:
        for line in f:
            # Detect frequency header (comes before ESE blocks)
            freq_match = re.match(r'\s+FREQUENCY\s*=\s*([\d.E+\-]+)', line)
            if freq_match:
                try:
                    current_freq = float(freq_match.group(1))
                except ValueError:
                    pass

            # Detect element type header
            if 'ELEMENT-TYPE =' in line:
                parts = line.split('ELEMENT-TYPE =')
                if len(parts) >= 2:
                    current_elem_type = parts[1].split()[0].strip()
                    in_ese_block = True

            # Detect subcase
            if 'SUBCASE' in line and in_ese_block:
                match = re.search(r'SUBCASE\s+(\d+)', line)
                if match:
                    current_subcase = int(match.group(1))

            # Data rows: element_id, strain_energy, percent, density
            # Only store BUSH elements (bolts 1-10) — BEAMs are structural noise
            if in_ese_block and current_elem_type == 'BUSH':
                match = re.match(
                    r'\s+(\d+)\s+([\d.E+\-]+)\s+([\d.E+\-]+)',
                    line
                )
                if match:
                    try:
                        results.append({
                            'element_id': int(match.group(1)),
                            'element_type': current_elem_type,
                            'subcase_id': current_subcase,
                            'frequency': current_freq,
                            'strain_energy': float(match.group(2)),
                            'percent_total': float(match.group(3)),
                        })
                    except (ValueError, IndexError):
                        pass

            # End of ESE block
            if in_ese_block and line.strip() == '':
                in_ese_block = False

    return results


def insert_strain_energy_batch(conn, case_id, ese_data):
    """Insert strain energy data into strain_energy table."""
    cursor = conn.cursor()
    sql = ('INSERT INTO strain_energy (case_id, element_id, element_type, '
           'subcase_id, frequency, strain_energy, percent_total) '
           'VALUES (?, ?, ?, ?, ?, ?, ?)')
    total = 0
    for e in ese_data:
        cursor.execute(sql, (case_id, e['element_id'], e['element_type'],
                             e['subcase_id'], e.get('frequency'), e['strain_energy'], e['percent_total']))
        total += 1
    return total


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
        bp = af / 'Bush.blk'
        pp = af / 'randombeamx.pch'
        f06 = af / 'randombeamx.f06'
        if not pp.exists():
            continue
        designs.append((dn, str(bp), str(pp), str(f06)))
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
        for dn, bp, pp, f06 in designs:
            bs = "Y" if os.path.exists(bp) else "N"
            fs = "Y" if os.path.exists(f06) else "N"
            print(f"  Design {dn}: Bush [{bs}], PCH [Y], F06 [{fs}]")
        return True
    if not os.path.exists(db_path):
        print(f"Error: DB not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)

    # Check DB integrity before import
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()
        if result[0] != 'ok':
            raise sqlite3.DatabaseError(f"integrity_check: {result[0]}")
    except sqlite3.DatabaseError as e:
        conn.close()
        print(f"ERROR: Database integrity check failed: {e}")
        print(f"ERROR: Will NOT auto-delete. Investigate before proceeding: {db_path}")
        print(f"ERROR: If the DB is truly corrupt, manually delete it and re-run setup_database.py")
        return False
    apply_performance_pragmas(conn)

    # Python 3.13 sqlite3 C extension crashes after ~20 designs of heavy inserts.
    # Workaround: close and reopen the connection every RECONNECT_EVERY designs
    # to reset C-level state and prevent memory corruption.
    RECONNECT_EVERY = 10

    try:
        import time as _time
        study_id = get_or_create_study(conn, study_name)
        print(f"\nStudy ID: {study_id}")
        if reset_study:
            d = reset_study_data(conn, study_id)
            print(f"Reset: deleted {d} cases")

        # Detect baseline design (Design1 in HEEDS = all bolts at baseline)
        baseline_dn = detect_baseline_design(designs)
        if baseline_dn:
            print(f"Baseline detected: Design {baseline_dn}")
        else:
            print("WARNING: No baseline design detected")

        tpsd, tpeak, tparam, tforce, tfpeak, tese = 0, 0, 0, 0, 0, 0
        t0 = _time.time()
        print(f"\nImporting {len(designs)} designs (reconnect every {RECONNECT_EVERY})...")
        for i, (dn, bp, pp, f06) in enumerate(designs, 1):
            print(f"[{i}/{len(designs)}] Design {dn}...", end=" ", flush=True)
            is_bl = (dn == baseline_dn)
            cid = insert_case(conn, study_id, dn, pp, is_baseline=is_bl)

            # Bush parameters (K4, K5, K6 stiffness)
            if os.path.exists(bp):
                params = parse_bush_file(bp)
                if params:
                    tparam += insert_parameters_batch(conn, cid, params)

            # Parse PCH — acceleration, displacement, AND force PSD curves
            psd = parse_pch_file(pp)
            tpsd += insert_psd_data_batch(conn, cid, psd)
            tpeak += insert_peaks_batch(conn, cid, psd)

            # CBUSH element force PSD (new)
            tforce += insert_force_psd_batch(conn, cid, psd)
            tfpeak += insert_force_peaks_batch(conn, cid, psd)

            # Strain energy from f06 (new)
            if os.path.exists(f06):
                ese = parse_f06_strain_energy(f06)
                if ese:
                    tese += insert_strain_energy_batch(conn, cid, ese)

            elapsed = _time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(designs) - i) / rate if rate > 0 else 0
            print(f"OK  ({elapsed:.0f}s elapsed, {rate:.2f} designs/s, ETA {eta:.0f}s)")

            # Commit + reconnect every N designs to reset sqlite3 C-level state
            if i % RECONNECT_EVERY == 0:
                conn.commit()
                conn.close()
                conn = sqlite3.connect(db_path)
                apply_performance_pragmas(conn)
                print(f"  [COMMIT+RECONNECT at {i}/{len(designs)}]", flush=True)

        conn.commit()  # final commit
        total = _time.time() - t0
        print(f"\nDone! Cases:{len(designs)} Params:{tparam} "
              f"PSD:{tpsd:,} Peaks:{tpeak} "
              f"Force:{tforce:,} ForcePeaks:{tfpeak} ESE:{tese}")
        print(f"Total time: {total:.1f}s ({total/len(designs):.2f}s/design)")
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
