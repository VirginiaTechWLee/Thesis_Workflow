"""
Feature extraction from PSD database for bolt looseness ML classification.

Fully generalized — discovers all structure (nodes, DOFs, data types, bolt
elements, stiffness thresholds) from the database rather than hardcoding
values tied to any specific beam model.

Usage:
    python Scripts/extract_features.py --db D:\\thesis_database\\thesis_results.db
    python Scripts/extract_features.py --db D:\\thesis_database\\thesis_results.db --output my_features.npz
    python Scripts/extract_features.py --db D:\\thesis_database\\thesis_results.db --ratio-threshold 0.1
"""
import argparse
import gc
import os
import sqlite3
import sys
import time

# Force unbuffered output so progress is visible in real-time (logs, MCP, CI)
os.environ["PYTHONUNBUFFERED"] = "1"
from pathlib import Path

import numpy as np
import pandas as pd

# Compat: np.trapz was renamed to np.trapezoid in NumPy 2.0
_trapz = getattr(np, "trapezoid", np.trapz)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def connect(db_path: str) -> sqlite3.Connection:
    if not Path(db_path).exists():
        print(f"ERROR: database not found: {db_path}")
        sys.exit(1)
    return sqlite3.connect(db_path)


def fetch_case_list(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return DataFrame of all cases with case_id, case_number, is_baseline."""
    cur = conn.execute(
        "SELECT case_id, case_number, is_baseline FROM cases ORDER BY case_number"
    )
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["case_id", "case_number", "is_baseline"])
    print(f"  Cases loaded: {len(df)} (baseline={int(df['is_baseline'].sum())})")
    return df


# ---------------------------------------------------------------------------
# Structure discovery — no hardcoded node IDs, DOFs, elements, or thresholds
# ---------------------------------------------------------------------------
def _find_baseline_cid(cases: pd.DataFrame):
    """Return case_id of the baseline case, or None if not found."""
    bl = cases[cases["is_baseline"] == 1]
    if bl.empty:
        bl = cases[cases["case_number"] == 0]
    if bl.empty:
        return None
    return int(bl.iloc[0]["case_id"])


def discover_nodes(conn: sqlite3.Connection, ref_cid: int) -> list:
    """Discover node IDs from a single reference case (avoids full-table scan)."""
    rows = conn.execute(
        "SELECT DISTINCT node_id FROM psd_data WHERE case_id=? ORDER BY node_id",
        (ref_cid,),
    ).fetchall()
    return [r[0] for r in rows]


def detect_primary_channel(conn: sqlite3.Connection, baseline_cid: int) -> tuple:
    """
    Auto-detect the (dof, data_type) combination with the highest total
    energy in the baseline case, using the pre-computed peaks.area column.
    """
    rows = conn.execute(
        "SELECT dof, data_type, SUM(area) AS total "
        "FROM peaks WHERE case_id=? GROUP BY dof, data_type ORDER BY total DESC",
        (baseline_cid,),
    ).fetchall()
    if rows:
        dof, dtype = rows[0][0], rows[0][1]
        print(f"  Auto-detected primary channel: {dof} / {dtype} "
              f"(energy={rows[0][2]:.4g})")
        return dof, dtype
    # Fallback: try to discover from psd_data
    rows = conn.execute(
        "SELECT DISTINCT dof, data_type FROM psd_data WHERE case_id=? LIMIT 1",
        (baseline_cid,),
    ).fetchall()
    if rows:
        return rows[0][0], rows[0][1]
    raise ValueError("No PSD data found for baseline case")


def discover_baseline_params(conn: sqlite3.Connection, baseline_cid: int) -> dict:
    """
    Return {element_id: (K4, K5, K6)} for the baseline case.
    These are the 'healthy' stiffness values — used as the reference for
    detecting loosened bolts, instead of any hardcoded threshold.
    """
    rows = conn.execute(
        "SELECT element_id, K4, K5, K6 FROM parameters WHERE case_id=?",
        (baseline_cid,),
    ).fetchall()
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


# ---------------------------------------------------------------------------
# Label generation — baseline-relative, no hardcoded thresholds
# ---------------------------------------------------------------------------
def build_labels(
    conn: sqlite3.Connection,
    cases: pd.DataFrame,
    baseline_params: dict,
    ratio_threshold: float,
) -> pd.DataFrame:
    """
    Label each case by comparing its bolt stiffness to the baseline.

    A bolt is 'loosened' if any of its K components dropped below
    ``ratio_threshold`` of the baseline value for that component.
    The case label is the element with the largest relative drop.
    """
    records = []
    for _, case in cases.iterrows():
        cid = int(case["case_id"])
        cur = conn.execute(
            "SELECT element_id, K4, K5, K6 FROM parameters WHERE case_id=?",
            (cid,),
        )
        bolt_rows = cur.fetchall()

        worst_elem = 0
        worst_ratio = 1.0       # 1.0 = no change
        worst_min_k = None

        for elem, k4, k5, k6 in bolt_rows:
            if elem not in baseline_params:
                continue
            bl_k4, bl_k5, bl_k6 = baseline_params[elem]
            # Compute per-component ratios (guard against zero baseline)
            ratios = []
            for cur_k, bl_k in [(k4, bl_k4), (k5, bl_k5), (k6, bl_k6)]:
                if bl_k > 0:
                    ratios.append(cur_k / bl_k)
                else:
                    ratios.append(1.0 if cur_k == 0 else 0.0)
            min_ratio = min(ratios)
            if min_ratio < ratio_threshold and min_ratio < worst_ratio:
                worst_elem = elem
                worst_ratio = min_ratio
                worst_min_k = min(k4, k5, k6)

        if worst_elem == 0:
            records.append({
                "case_id": cid,
                "case_number": int(case["case_number"]),
                "loosened_bolt": 0,
                "min_K": 0.0,
                "severity": 0,
                "label_binary": 0,
            })
        else:
            sev = int(round(np.log10(max(worst_min_k, 1.0))))
            records.append({
                "case_id": cid,
                "case_number": int(case["case_number"]),
                "loosened_bolt": worst_elem,
                "min_K": worst_min_k,
                "severity": sev,
                "label_binary": 1,
            })

    labels = pd.DataFrame(records)
    n_healthy = (labels["label_binary"] == 0).sum()
    n_loose = (labels["label_binary"] == 1).sum()
    print(f"  Labels: {n_healthy} healthy, {n_loose} loosened "
          f"(ratio_threshold={ratio_threshold})")
    bolt_dist = (labels[labels["loosened_bolt"] > 0]["loosened_bolt"]
                 .value_counts().sort_index())
    for bolt, cnt in bolt_dist.items():
        print(f"    Element {bolt}: {cnt} cases")
    return labels


# ---------------------------------------------------------------------------
# Peak-based features (fast path — reads pre-computed peaks table)
# ---------------------------------------------------------------------------
def extract_peak_features(
    conn: sqlite3.Connection, cases: pd.DataFrame
) -> pd.DataFrame:
    """
    From the peaks table extract per-case features:
      - area under PSD curve
      - peak1/peak2/peak3 frequency and amplitude
    for every (node, dof, data_type) combination found in the data.
    """
    print("  Extracting peak-based features ...")

    rows = []
    case_ids = cases["case_id"].values
    n_cases = len(case_ids)

    for idx, cid in enumerate(case_ids):
        rec = {"case_id": int(cid)}
        cur = conn.execute(
            "SELECT node_id, dof, data_type, area, "
            "peak1_freq, peak1_psd, peak2_freq, peak2_psd, "
            "peak3_freq, peak3_psd "
            "FROM peaks WHERE case_id=?",
            (int(cid),),
        )
        for p in cur.fetchall():
            node_id, dof, data_type = p[0], p[1], p[2]
            prefix = f"n{node_id}_{dof}_{data_type[:3]}"
            rec[f"{prefix}_area"] = p[3] or 0.0
            rec[f"{prefix}_pk1f"] = p[4] or 0.0
            rec[f"{prefix}_pk1a"] = p[5] or 0.0
            rec[f"{prefix}_pk2f"] = p[6] or 0.0
            rec[f"{prefix}_pk2a"] = p[7] or 0.0
            rec[f"{prefix}_pk3f"] = p[8] or 0.0
            rec[f"{prefix}_pk3a"] = p[9] or 0.0
        rows.append(rec)

        if (idx + 1) % 100 == 0 or (idx + 1) == n_cases:
            print(f"    [{idx+1}/{n_cases}]")

    df = pd.DataFrame(rows).fillna(0.0)
    print(f"    Peak features: {df.shape[1] - 1} columns")
    return df


# ---------------------------------------------------------------------------
# Common frequency grid
# ---------------------------------------------------------------------------
def _common_freq_grid(
    conn: sqlite3.Connection, ref_cid: int, n_points: int = 256
) -> np.ndarray:
    """Build a common frequency grid from the reference case's data range."""
    row = conn.execute(
        "SELECT MIN(frequency), MAX(frequency) FROM psd_data WHERE case_id=?",
        (ref_cid,),
    ).fetchone()
    fmin, fmax = row[0], row[1]
    return np.linspace(fmin, fmax, n_points)


# ---------------------------------------------------------------------------
# Spectral + delta features — single DB pass, fully parameterized
# ---------------------------------------------------------------------------
def extract_spectral_and_delta_features(
    db_path: str,
    cases: pd.DataFrame,
    common_freq: np.ndarray,
    nodes: list,
    primary_dof: str,
    primary_dtype: str,
) -> tuple:
    """
    Single-pass extraction of spectral and delta-from-baseline features.

    Parameters ``nodes``, ``primary_dof``, and ``primary_dtype`` are all
    discovered from the database — nothing is hardcoded.

    Reconnects to the DB every 100 cases to avoid SQLite memory accumulation
    on databases with minor corruption.

    Returns (spectral_df, delta_df).
    """
    BATCH_SIZE = 100  # reconnect interval

    print(f"  Extracting spectral + delta features "
          f"({primary_dof}/{primary_dtype}, {len(nodes)} nodes) ...", flush=True)

    # Build frequency-band masks (4 equal bands spanning the data range)
    fmin, fmax = common_freq[0], common_freq[-1]
    band_edges = np.linspace(fmin, fmax, 5)
    band_masks = []
    for i in range(4):
        mask = (common_freq >= band_edges[i]) & (common_freq < band_edges[i + 1])
        band_masks.append(mask)

    # Identify and pre-fetch baseline curves
    baseline = cases[cases["is_baseline"] == 1]
    if baseline.empty:
        baseline = cases[cases["case_number"] == 0]
    has_baseline = not baseline.empty

    baseline_curves = {}
    if has_baseline:
        baseline_cid = int(baseline.iloc[0]["case_id"])
        conn = connect(db_path)
        try:
            cur = conn.execute(
                "SELECT node_id, frequency, psd_value FROM psd_data "
                "WHERE case_id=? AND dof=? AND data_type=? "
                "ORDER BY node_id, frequency",
                (baseline_cid, primary_dof, primary_dtype),
            )
            bl_data = {}
            for nid, freq, psd_val in cur.fetchall():
                if nid not in bl_data:
                    bl_data[nid] = ([], [])
                bl_data[nid][0].append(freq)
                bl_data[nid][1].append(psd_val)
            for node in nodes:
                if node in bl_data:
                    baseline_curves[node] = np.interp(
                        common_freq,
                        np.array(bl_data[node][0]),
                        np.array(bl_data[node][1]),
                    )
            del bl_data
        except sqlite3.DatabaseError as e:
            print(f"    WARNING: could not load baseline: {e}", flush=True)
            has_baseline = False
        conn.close()

    spectral_rows = []
    delta_rows = []
    n_cases = len(cases)
    t0 = time.time()

    conn = connect(db_path)
    for idx, (_, case) in enumerate(cases.iterrows()):
        # Reconnect every BATCH_SIZE cases to release SQLite memory
        if idx > 0 and idx % BATCH_SIZE == 0:
            conn.close()
            gc.collect()
            conn = connect(db_path)

        cid = int(case["case_id"])
        srec = {"case_id": cid}
        drec = {"case_id": cid}

        try:
            cur = conn.execute(
                "SELECT node_id, frequency, psd_value FROM psd_data "
                "WHERE case_id=? AND dof=? AND data_type=? "
                "ORDER BY node_id, frequency",
                (cid, primary_dof, primary_dtype),
            )
            all_rows = cur.fetchall()
        except sqlite3.DatabaseError as e:
            print(f"    WARNING: DB error on case_id={cid}: {e}", flush=True)
            spectral_rows.append(srec)
            delta_rows.append(drec)
            continue

        # Group by node_id
        node_data = {}
        for nid, freq, psd_val in all_rows:
            if nid not in node_data:
                node_data[nid] = ([], [])
            node_data[nid][0].append(freq)
            node_data[nid][1].append(psd_val)

        for node in nodes:
            if node not in node_data:
                continue
            freqs = np.array(node_data[node][0])
            psds = np.array(node_data[node][1])
            psd_interp = np.interp(common_freq, freqs, psds)

            prefix = f"n{node}"

            # --- Spectral features ---
            total_area = _trapz(psd_interp, common_freq)
            rms = np.sqrt(max(total_area, 0.0))
            srec[f"{prefix}_rms"] = rms

            for bi, mask in enumerate(band_masks):
                bp = (_trapz(psd_interp[mask], common_freq[mask])
                      if mask.sum() > 1 else 0.0)
                srec[f"{prefix}_band{bi}"] = bp

            psd_sum = psd_interp.sum()
            if psd_sum > 0:
                srec[f"{prefix}_centroid"] = (
                    np.dot(common_freq, psd_interp) / psd_sum
                )
            else:
                srec[f"{prefix}_centroid"] = 0.0

            cumsum = np.cumsum(psd_interp)
            if cumsum[-1] > 0:
                ro_idx = np.searchsorted(cumsum, 0.95 * cumsum[-1])
                srec[f"{prefix}_rolloff95"] = common_freq[
                    min(ro_idx, len(common_freq) - 1)
                ]
            else:
                srec[f"{prefix}_rolloff95"] = 0.0

            if psd_sum > 0:
                normed = psd_interp / psd_sum
                mu = np.dot(common_freq, normed)
                var = np.dot((common_freq - mu) ** 2, normed)
                if var > 0:
                    m4 = np.dot((common_freq - mu) ** 4, normed)
                    srec[f"{prefix}_kurtosis"] = m4 / (var ** 2) - 3.0
                else:
                    srec[f"{prefix}_kurtosis"] = 0.0
            else:
                srec[f"{prefix}_kurtosis"] = 0.0

            # --- Delta features ---
            if has_baseline and node in baseline_curves:
                bl = baseline_curves[node]
                bl_area = _trapz(bl, common_freq)
                drec[f"{prefix}_d_rms"] = rms - np.sqrt(max(bl_area, 0.0))

                for bi, mask in enumerate(band_masks):
                    if mask.sum() > 1:
                        bp_bl = _trapz(bl[mask], common_freq[mask])
                        drec[f"{prefix}_d_band{bi}"] = (
                            srec[f"{prefix}_band{bi}"] - bp_bl
                        )
                    else:
                        drec[f"{prefix}_d_band{bi}"] = 0.0

                bl_peak_idx = np.argmax(bl)
                cur_peak_idx = np.argmax(psd_interp)
                drec[f"{prefix}_d_pkshift"] = (
                    common_freq[cur_peak_idx] - common_freq[bl_peak_idx]
                )

        spectral_rows.append(srec)
        delta_rows.append(drec)

        if (idx + 1) % 50 == 0 or (idx + 1) == n_cases:
            elapsed = time.time() - t0
            rate = (idx + 1) / elapsed if elapsed > 0 else 0
            eta = (n_cases - idx - 1) / rate if rate > 0 else 0
            print(f"    [{idx+1}/{n_cases}] {rate:.1f} cases/s, "
                  f"ETA {eta:.0f}s", flush=True)

    conn.close()
    sdf = pd.DataFrame(spectral_rows).fillna(0.0)
    ddf = pd.DataFrame(delta_rows).fillna(0.0)
    print(f"    Spectral features: {sdf.shape[1] - 1} columns")
    print(f"    Delta features: {ddf.shape[1] - 1} columns")
    return sdf, ddf


# ---------------------------------------------------------------------------
# Miles equation features (fn, Q, PSD_fn, grms, bandwidth per mode per node)
# ---------------------------------------------------------------------------
def extract_miles_features(
    conn: sqlite3.Connection, cases: pd.DataFrame,
    baseline_cid: int = None,
) -> pd.DataFrame:
    """
    From the miles table extract per-case features:
      - fn, Q, PSD_fn, grms, bandwidth for each (node, dof, data_type, mode_number)
      - delta_fn: relative frequency shift from baseline (Δfn/fn_baseline)
        This is the most direct indicator of stiffness change per eigenvalue
        perturbation theory: Δfn/fn ≈ ½(φnᵀΔKφn)/(φnᵀKφn)
    Returns a DataFrame with one row per case.
    """
    print("  Extracting Miles equation features ...")

    # Check if miles table exists and has data
    try:
        count = conn.execute("SELECT COUNT(*) FROM miles").fetchone()[0]
        if count == 0:
            print("    Miles table is empty — skipping Miles features")
            return pd.DataFrame({"case_id": cases["case_id"].values})
    except sqlite3.OperationalError:
        print("    Miles table not found — skipping Miles features")
        return pd.DataFrame({"case_id": cases["case_id"].values})

    # Load baseline fn values for delta computation
    bl_fn = {}
    if baseline_cid is not None:
        cur = conn.execute(
            "SELECT node_id, dof, data_type, mode_number, fn "
            "FROM miles WHERE case_id=? AND fn IS NOT NULL",
            (int(baseline_cid),),
        )
        for node_id, dof, data_type, mode_num, fn in cur.fetchall():
            key = f"n{node_id}_{dof}_{data_type[:3]}_m{mode_num}"
            bl_fn[key] = fn
        print(f"    Baseline fn values: {len(bl_fn)} modes")

    rows = []
    case_ids = cases["case_id"].values
    n_cases = len(case_ids)

    for idx, cid in enumerate(case_ids):
        rec = {"case_id": int(cid)}
        cur = conn.execute(
            "SELECT node_id, dof, data_type, mode_number, "
            "fn, Q, PSD_fn, grms, bandwidth "
            "FROM miles WHERE case_id=?",
            (int(cid),),
        )
        for m in cur.fetchall():
            node_id, dof, data_type, mode_num = m[0], m[1], m[2], m[3]
            fn, Q, PSD_fn, grms, bw = m[4], m[5], m[6], m[7], m[8]
            prefix = f"n{node_id}_{dof}_{data_type[:3]}_m{mode_num}"
            rec[f"{prefix}_fn"] = fn or 0.0
            rec[f"{prefix}_Q"] = Q or 0.0
            rec[f"{prefix}_PSDfn"] = PSD_fn or 0.0
            rec[f"{prefix}_grms"] = grms or 0.0
            rec[f"{prefix}_bw"] = bw or 0.0
            # Delta fn: relative frequency shift from baseline
            if prefix in bl_fn and bl_fn[prefix] > 0 and fn:
                rec[f"{prefix}_dfn"] = (fn - bl_fn[prefix]) / bl_fn[prefix]
            else:
                rec[f"{prefix}_dfn"] = 0.0
        rows.append(rec)

        if (idx + 1) % 100 == 0 or (idx + 1) == n_cases:
            print(f"    [{idx+1}/{n_cases}]")

    df = pd.DataFrame(rows).fillna(0.0)
    n_dfn = sum(1 for c in df.columns if c.endswith('_dfn'))
    print(f"    Miles features: {df.shape[1] - 1} columns ({n_dfn} delta-fn)")
    return df


# ---------------------------------------------------------------------------
# Strain energy features — per-bolt energy flow signatures
# ---------------------------------------------------------------------------
def extract_strain_energy_features(
    conn: sqlite3.Connection, cases: pd.DataFrame,
    baseline_cid: int = None,
) -> pd.DataFrame:
    """
    Extract per-bolt strain energy features from the strain_energy table.

    When a bolt loosens, its CBUSH strain energy drops and redistributes
    to neighboring bolts. This redistribution pattern is a direct per-bolt
    fault signature.

    Per bolt element: SE_area (total energy), SE_peak, SE_peak_freq,
                      SE_frac (fraction of total across all bolts),
                      SE_delta (relative change from baseline area).
    All discovered dynamically from DB — no hardcoded element IDs.
    """
    print("  Extracting strain energy per-bolt features ...")

    try:
        count = conn.execute("SELECT COUNT(*) FROM strain_energy").fetchone()[0]
        if count == 0:
            print("    strain_energy table is empty — skipping")
            return pd.DataFrame({"case_id": cases["case_id"].values})
    except sqlite3.OperationalError:
        print("    strain_energy table not found — skipping")
        return pd.DataFrame({"case_id": cases["case_id"].values})

    # Discover bolt elements from DB
    elements = [r[0] for r in conn.execute(
        "SELECT DISTINCT element_id FROM strain_energy ORDER BY element_id"
    ).fetchall()]
    if not elements:
        print("    No elements in strain_energy — skipping")
        return pd.DataFrame({"case_id": cases["case_id"].values})
    print(f"    Bolt elements: {elements}")

    # Baseline SE areas for delta computation
    bl_areas = {}
    if baseline_cid is not None:
        for elem in elements:
            rows = conn.execute(
                "SELECT frequency, strain_energy FROM strain_energy "
                "WHERE case_id=? AND element_id=? ORDER BY frequency",
                (int(baseline_cid), elem),
            ).fetchall()
            if len(rows) >= 2:
                area = sum(
                    0.5 * (rows[i+1][1] + rows[i][1]) * (rows[i+1][0] - rows[i][0])
                    for i in range(len(rows) - 1)
                )
                bl_areas[elem] = area

    case_ids = cases["case_id"].values
    n_cases = len(case_ids)
    result_rows = []

    for idx, cid in enumerate(case_ids):
        rec = {"case_id": int(cid)}

        # Fetch all SE data for this case in one query
        se_data = conn.execute(
            "SELECT element_id, frequency, strain_energy "
            "FROM strain_energy WHERE case_id=? ORDER BY element_id, frequency",
            (int(cid),),
        ).fetchall()

        # Group by element
        elem_data = {}
        for elem, freq, se in se_data:
            elem_data.setdefault(elem, []).append((freq, se))

        total_area = 0.0
        elem_areas = {}
        for elem in elements:
            pts = elem_data.get(elem, [])
            if len(pts) >= 2:
                area = sum(
                    0.5 * (pts[i+1][1] + pts[i][1]) * (pts[i+1][0] - pts[i][0])
                    for i in range(len(pts) - 1)
                )
                peak_se = max(p[1] for p in pts)
                peak_freq = max(pts, key=lambda p: p[1])[0]
            else:
                area, peak_se, peak_freq = 0.0, 0.0, 0.0

            elem_areas[elem] = area
            total_area += area
            rec[f"SE_e{elem}_area"] = area
            rec[f"SE_e{elem}_peak"] = peak_se
            rec[f"SE_e{elem}_peakf"] = peak_freq

        # Fraction of total (redistribution pattern)
        for elem in elements:
            rec[f"SE_e{elem}_frac"] = elem_areas.get(elem, 0.0) / total_area if total_area > 0 else 0.0

        # Delta from baseline
        for elem in elements:
            if elem in bl_areas and bl_areas[elem] > 0:
                rec[f"SE_e{elem}_delta"] = (elem_areas.get(elem, 0.0) - bl_areas[elem]) / bl_areas[elem]
            else:
                rec[f"SE_e{elem}_delta"] = 0.0

        result_rows.append(rec)
        if (idx + 1) % 100 == 0 or (idx + 1) == n_cases:
            print(f"    [{idx+1}/{n_cases}]")

    df = pd.DataFrame(result_rows).fillna(0.0)
    n_feats = df.shape[1] - 1
    print(f"    Strain energy features: {n_feats} columns "
          f"({len(elements)} elements × 5 features + deltas)")
    return df


# ---------------------------------------------------------------------------
# Force PSD per-bolt features
# ---------------------------------------------------------------------------
def extract_force_psd_features(
    conn: sqlite3.Connection, cases: pd.DataFrame,
    baseline_cid: int = None,
) -> pd.DataFrame:
    """
    Extract per-bolt CBUSH force PSD features from force_psd_data / force_peaks.

    Force through each bolt connection changes with looseness — direct load
    path signature. Per bolt per DOF: area, peak force, peak freq, delta area.
    All discovered dynamically from DB.
    """
    print("  Extracting force PSD per-bolt features ...")

    try:
        count = conn.execute("SELECT COUNT(*) FROM force_peaks").fetchone()[0]
        if count == 0:
            print("    force_peaks table is empty — skipping")
            return pd.DataFrame({"case_id": cases["case_id"].values})
    except sqlite3.OperationalError:
        print("    force_peaks table not found — skipping")
        return pd.DataFrame({"case_id": cases["case_id"].values})

    # Discover (element, dof, data_type) combos from force_peaks
    combos = conn.execute(
        "SELECT DISTINCT element_id, dof, data_type FROM force_peaks ORDER BY element_id, dof"
    ).fetchall()
    if not combos:
        print("    No force_peaks data — skipping")
        return pd.DataFrame({"case_id": cases["case_id"].values})
    print(f"    Force PSD combos: {len(combos)} (element × dof × data_type)")

    # Baseline areas for delta
    bl_areas = {}
    if baseline_cid is not None:
        rows = conn.execute(
            "SELECT element_id, dof, data_type, area, peak1_freq, peak1_psd "
            "FROM force_peaks WHERE case_id=?",
            (int(baseline_cid),),
        ).fetchall()
        for elem, dof, dtype, area, _, _ in rows:
            bl_areas[(elem, dof, dtype)] = area

    case_ids = cases["case_id"].values
    n_cases = len(case_ids)
    result_rows = []

    for idx, cid in enumerate(case_ids):
        rec = {"case_id": int(cid)}
        peaks = conn.execute(
            "SELECT element_id, dof, data_type, area, "
            "peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd "
            "FROM force_peaks WHERE case_id=?",
            (int(cid),),
        ).fetchall()

        for row in peaks:
            elem, dof, dtype = row[0], row[1], row[2]
            area = row[3] or 0.0
            pk1f, pk1a = row[4] or 0.0, row[5] or 0.0
            pk2f, pk2a = row[6] or 0.0, row[7] or 0.0
            pk3f, pk3a = row[8] or 0.0, row[9] or 0.0
            prefix = f"FP_e{elem}_{dof}_{dtype[:3]}"
            rec[f"{prefix}_area"] = area
            rec[f"{prefix}_pk1f"] = pk1f
            rec[f"{prefix}_pk1a"] = pk1a
            rec[f"{prefix}_pk2f"] = pk2f
            rec[f"{prefix}_pk2a"] = pk2a
            rec[f"{prefix}_pk3f"] = pk3f
            rec[f"{prefix}_pk3a"] = pk3a

            # Delta area from baseline
            key = (elem, dof, dtype)
            if key in bl_areas and bl_areas[key] > 0:
                rec[f"{prefix}_d_area"] = (area - bl_areas[key]) / bl_areas[key]
            else:
                rec[f"{prefix}_d_area"] = 0.0

        result_rows.append(rec)
        if (idx + 1) % 100 == 0 or (idx + 1) == n_cases:
            print(f"    [{idx+1}/{n_cases}]")

    df = pd.DataFrame(result_rows).fillna(0.0)
    print(f"    Force PSD features: {df.shape[1] - 1} columns")
    return df


# ---------------------------------------------------------------------------
# Assemble full training matrix
# ---------------------------------------------------------------------------
def build_training_matrix(
    db_path: str,
    output_path: str = None,
    ratio_threshold: float = 0.5,
    spectral_dof: str = None,
    spectral_dtype: str = None,
    noise_floor: float = 1e-5,
) -> pd.DataFrame:
    """
    Main entry point.  Discovers structure from the database, extracts
    features, generates labels, and saves the training matrix.
    """
    print("=" * 60, flush=True)
    print("Feature Extraction Pipeline (generalized)", flush=True)
    print(f"  Database: {db_path}", flush=True)
    print("=" * 60, flush=True)
    sys.stdout.flush()
    t_start = time.time()

    # ------------------------------------------------------------------
    # Stage 1: Load cases
    # ------------------------------------------------------------------
    print("\n[1/4] Loading cases ...")
    conn = connect(db_path)
    cases = fetch_case_list(conn)
    baseline_cid = _find_baseline_cid(cases)
    has_baseline = baseline_cid is not None

    if not has_baseline:
        print("  WARNING: No baseline case found — using first case as "
              "reference for structure discovery. Delta features will be "
              "skipped and all labels set to 0 (unknown).")
        # Use first case as reference for node/channel discovery
        ref_cid = int(cases.iloc[0]["case_id"])
    else:
        ref_cid = baseline_cid
    conn.close()

    # ------------------------------------------------------------------
    # Stage 2: Discover structure from the database
    # ------------------------------------------------------------------
    print("\n[2/4] Discovering structure ...")
    conn = connect(db_path)

    nodes = discover_nodes(conn, ref_cid)
    print(f"  Nodes ({len(nodes)}): {nodes}")

    if spectral_dof and spectral_dtype:
        primary_dof, primary_dtype = spectral_dof, spectral_dtype
        print(f"  Primary channel (user override): {primary_dof} / {primary_dtype}")
    else:
        primary_dof, primary_dtype = detect_primary_channel(conn, ref_cid)

    if has_baseline:
        baseline_params = discover_baseline_params(conn, baseline_cid)
        print(f"  Bolt elements ({len(baseline_params)}): "
              f"{sorted(baseline_params.keys())}")
    else:
        baseline_params = {}
        print("  Bolt elements: N/A (no baseline)")
    conn.close()

    # ------------------------------------------------------------------
    # Stage 3: Build labels (baseline-relative)
    # ------------------------------------------------------------------
    print("\n[3/4] Building labels ...")
    conn = connect(db_path)

    # Check for per-study force_label overrides (e.g. Study E healthy variation)
    force_label_map = {}
    try:
        fl_rows = conn.execute(
            "SELECT study_id, force_label FROM studies WHERE force_label IS NOT NULL"
        ).fetchall()
        for sid, fl in fl_rows:
            force_label_map[sid] = fl
        if force_label_map:
            print(f"  Force-label overrides: {force_label_map}")
    except Exception:
        pass  # Column may not exist in older DBs

    if has_baseline:
        labels = build_labels(conn, cases, baseline_params, ratio_threshold)
        # Apply force_label overrides: studies with force_label get that label
        # regardless of stiffness ratio computation
        if force_label_map:
            # Build case_id -> study_id lookup
            cid_to_sid = dict(conn.execute(
                "SELECT case_id, study_id FROM cases"
            ).fetchall())
            n_overridden = 0
            for idx, row in labels.iterrows():
                sid = cid_to_sid.get(int(row["case_id"]))
                if sid in force_label_map:
                    fl = force_label_map[sid]
                    labels.at[idx, "loosened_bolt"] = fl
                    labels.at[idx, "min_K"] = 0.0
                    labels.at[idx, "severity"] = 0
                    labels.at[idx, "label_binary"] = 0 if fl == 0 else 1
                    n_overridden += 1
            print(f"  Force-label applied to {n_overridden} cases")
    else:
        # No baseline — assign all labels to 0 (unknown/healthy)
        labels = pd.DataFrame({
            "case_id": cases["case_id"].values,
            "case_number": cases["case_number"].values,
            "loosened_bolt": 0,
            "min_K": 0.0,
            "severity": 0,
            "label_binary": 0,
        })
        print(f"  Labels: all {len(labels)} cases set to healthy (no baseline)")
    conn.close()

    # ------------------------------------------------------------------
    # Stage 4a: Peak features
    # ------------------------------------------------------------------
    print("\n[4/4] Extracting features ...")
    conn = connect(db_path)
    peak_feats = extract_peak_features(conn, cases)
    conn.close()
    gc.collect()

    # ------------------------------------------------------------------
    # Stage 4b: Spectral + delta features
    # ------------------------------------------------------------------
    conn = connect(db_path)
    common_freq = _common_freq_grid(conn, ref_cid, n_points=256)
    conn.close()

    spectral_feats, delta_feats = extract_spectral_and_delta_features(
        db_path, cases, common_freq, nodes, primary_dof, primary_dtype,
    )
    gc.collect()

    # ------------------------------------------------------------------
    # Stage 4c: Miles equation features (+ delta-fn from baseline)
    # ------------------------------------------------------------------
    conn = connect(db_path)
    miles_feats = extract_miles_features(conn, cases, baseline_cid=baseline_cid)
    conn.close()
    gc.collect()

    # ------------------------------------------------------------------
    # Stage 4d: Strain energy per-bolt features
    # ------------------------------------------------------------------
    conn = connect(db_path)
    se_feats = extract_strain_energy_features(conn, cases, baseline_cid=baseline_cid)
    conn.close()
    gc.collect()

    # ------------------------------------------------------------------
    # Stage 4e: Force PSD per-bolt features
    # ------------------------------------------------------------------
    conn = connect(db_path)
    fp_feats = extract_force_psd_features(conn, cases, baseline_cid=baseline_cid)
    conn.close()
    gc.collect()

    # ------------------------------------------------------------------
    # Merge and finalize
    # ------------------------------------------------------------------
    merged = labels.merge(peak_feats, on="case_id", how="left")
    merged = merged.merge(spectral_feats, on="case_id", how="left")
    merged = merged.merge(delta_feats, on="case_id", how="left")
    merged = merged.merge(miles_feats, on="case_id", how="left")
    merged = merged.merge(se_feats, on="case_id", how="left")
    merged = merged.merge(fp_feats, on="case_id", how="left")
    merged = merged.fillna(0.0)

    # Add study_id per row (needed for IsolationForest to identify Study E)
    conn2 = connect(db_path)
    cid_sid = dict(conn2.execute("SELECT case_id, study_id FROM cases").fetchall())
    merged["study_id"] = merged["case_id"].map(cid_sid).fillna(-1).astype(int)
    conn2.close()

    meta_cols = [
        "case_id", "case_number", "loosened_bolt",
        "min_K", "severity", "label_binary", "study_id",
    ]
    feature_cols = [c for c in merged.columns if c not in meta_cols]

    X = merged[feature_cols].values.astype(np.float64)
    y_bolt = merged["loosened_bolt"].values.astype(int)
    y_severity = merged["severity"].values.astype(int)
    y_binary = merged["label_binary"].values.astype(int)

    # ------------------------------------------------------------------
    # Data cleaning: apply noise floor
    # Values below the noise floor are physically meaningless (numerical
    # artifacts from near-zero PSD channels). Setting them to zero prevents
    # the classifier from training on sensor-unmeasurable signals.
    # The noise floor is applied to amplitude features only (areas, peaks,
    # PSD values, GRMS) — NOT to frequency or Q features.
    # ------------------------------------------------------------------
    amplitude_tags = ['_area', '_pk1a', '_pk2a', '_pk3a', '_PSDfn', '_grms',
                      '_rms', '_band', '_d_area', '_peak']
    n_cleaned = 0
    n_values_zeroed = 0
    for i, col in enumerate(feature_cols):
        if any(tag in col for tag in amplitude_tags):
            below = np.abs(X[:, i]) < noise_floor
            n_values_zeroed += below.sum()
            X[:, i] = np.where(below, 0.0, X[:, i])
            if below.any():
                n_cleaned += 1
    print(f"  Noise floor applied: {noise_floor:.0e}")
    print(f"    {n_cleaned} columns affected, {n_values_zeroed:,d} values zeroed")

    # Drop zero-variance columns
    variances = X.var(axis=0)
    keep_mask = variances > 0
    n_dropped = (~keep_mask).sum()
    X = X[:, keep_mask]
    feature_cols = [c for i, c in enumerate(feature_cols) if keep_mask[i]]

    # Log-transform amplitude features (rms, band power) to compress
    # orders-of-magnitude ranges (1e-42 to 1e+08) into classifier-friendly scale.
    # Uses sign-preserving log: sign(x) * log10(|x| + 1) so negatives survive.
    # Values that were zeroed by noise floor → log10(0 + 1) = 0, which is clean.
    n_log = 0
    for i, col in enumerate(feature_cols):
        if any(tag in col for tag in ['_rms', '_band', '_d_rms', '_d_band',
                                        '_PSDfn', '_grms', '_bw',
                                        '_area', '_peak', '_pk1a', '_pk2a', '_pk3a']):
            X[:, i] = np.sign(X[:, i]) * np.log10(np.abs(X[:, i]) + 1)
            n_log += 1
    print(f"  Log-transformed: {n_log} amplitude columns")

    # Standardize all features to zero mean, unit variance
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    X = scaler.fit_transform(X)
    print(f"  StandardScaler applied: mean~0, std~1 across all {X.shape[1]} features")

    elapsed = time.time() - t_start

    # Summary
    print(f"\n{'=' * 60}")
    print("TRAINING MATRIX SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Samples        : {X.shape[0]}")
    print(f"  Features       : {X.shape[1]} ({n_dropped} zero-variance dropped)")
    print(f"  Primary channel: {primary_dof} / {primary_dtype}")
    print(f"  Label arrays   : y_bolt, y_severity, y_binary")
    print(f"  Bolt classes   : {np.unique(y_bolt)}")
    if y_binary.sum() > 0:
        sev_vals = y_severity[y_binary == 1]
        print(f"  Severity range : {sev_vals.min()} - {sev_vals.max()}")
    print(f"  Time elapsed   : {elapsed:.1f}s")

    # Save
    if output_path is None:
        output_path = str(Path(db_path).parent / "training_matrix.npz")
    csv_path = output_path.replace(".npz", ".csv")

    np.savez_compressed(
        output_path,
        X=X,
        y_bolt=y_bolt,
        y_severity=y_severity,
        y_binary=y_binary,
        feature_names=np.array(feature_cols),
        case_numbers=merged["case_number"].values,
        study_ids=merged["study_id"].values,
        freq_grid=common_freq,
        scaler_mean=scaler.mean_,
        scaler_scale=scaler.scale_,
    )
    print(f"\n  Saved: {output_path}")
    print(f"         Arrays: X, y_bolt, y_severity, y_binary, "
          f"feature_names, case_numbers, study_ids, freq_grid, "
          f"scaler_mean, scaler_scale")

    try:
        merged.to_csv(csv_path, index=False, float_format="%.8g")
        print(f"  Saved: {csv_path}")
    except Exception as e:
        print(f"  WARNING: CSV save failed: {e}")

    print("\nDone.", flush=True)
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract ML features from PSD database (generalized)"
    )
    parser.add_argument(
        "--db",
        default=r"D:\thesis_database\thesis_results.db",
        help="Path to thesis_results.db",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output .npz path (default: <db_dir>/training_matrix.npz)",
    )
    parser.add_argument(
        "--ratio-threshold",
        type=float,
        default=0.5,
        help="K/K_baseline ratio below which a bolt is 'loosened' (default: 0.5)",
    )
    parser.add_argument(
        "--spectral-dof",
        default=None,
        help="Override primary DOF for spectral features (default: auto-detect)",
    )
    parser.add_argument(
        "--spectral-dtype",
        default=None,
        help="Override primary data type for spectral features (default: auto-detect)",
    )
    parser.add_argument(
        "--noise-floor",
        type=float,
        default=1e-5,
        help="Amplitude values below this threshold are zeroed during cleaning. "
             "Prevents classifier from training on sensor-unmeasurable numerical "
             "artifacts. Aligned with typical sensor noise floors. Default: 1e-5.",
    )
    args = parser.parse_args()

    try:
        build_training_matrix(
            args.db,
            args.output,
            ratio_threshold=args.ratio_threshold,
            spectral_dof=args.spectral_dof,
            spectral_dtype=args.spectral_dtype,
            noise_floor=args.noise_floor,
        )
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
