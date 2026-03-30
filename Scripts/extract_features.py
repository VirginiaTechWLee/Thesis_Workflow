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
import sqlite3
import sys
import time
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
    conn: sqlite3.Connection, cases: pd.DataFrame
) -> pd.DataFrame:
    """
    From the miles table extract per-case features:
      - fn, Q, PSD_fn, grms, bandwidth for each (node, dof, data_type, mode_number)
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
        rows.append(rec)

        if (idx + 1) % 100 == 0 or (idx + 1) == n_cases:
            print(f"    [{idx+1}/{n_cases}]")

    df = pd.DataFrame(rows).fillna(0.0)
    print(f"    Miles features: {df.shape[1] - 1} columns")
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
    if has_baseline:
        labels = build_labels(conn, cases, baseline_params, ratio_threshold)
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
    # Stage 4c: Miles equation features
    # ------------------------------------------------------------------
    conn = connect(db_path)
    miles_feats = extract_miles_features(conn, cases)
    conn.close()
    gc.collect()

    # ------------------------------------------------------------------
    # Merge and finalize
    # ------------------------------------------------------------------
    merged = labels.merge(peak_feats, on="case_id", how="left")
    merged = merged.merge(spectral_feats, on="case_id", how="left")
    merged = merged.merge(delta_feats, on="case_id", how="left")
    merged = merged.merge(miles_feats, on="case_id", how="left")
    merged = merged.fillna(0.0)

    meta_cols = [
        "case_id", "case_number", "loosened_bolt",
        "min_K", "severity", "label_binary",
    ]
    feature_cols = [c for c in merged.columns if c not in meta_cols]

    X = merged[feature_cols].values.astype(np.float64)
    y_bolt = merged["loosened_bolt"].values.astype(int)
    y_severity = merged["severity"].values.astype(int)
    y_binary = merged["label_binary"].values.astype(int)

    # Drop zero-variance columns
    variances = X.var(axis=0)
    keep_mask = variances > 0
    n_dropped = (~keep_mask).sum()
    X = X[:, keep_mask]
    feature_cols = [c for i, c in enumerate(feature_cols) if keep_mask[i]]

    # Log-transform amplitude features (rms, band power) to compress
    # orders-of-magnitude ranges (1e-42 to 1e+08) into classifier-friendly scale.
    # Uses sign-preserving log: sign(x) * log10(|x| + 1) so negatives survive.
    n_log = 0
    for i, col in enumerate(feature_cols):
        if any(tag in col for tag in ['_rms', '_band', '_d_rms', '_d_band',
                                        '_PSDfn', '_grms', '_bw']):
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
        freq_grid=common_freq,
        scaler_mean=scaler.mean_,
        scaler_scale=scaler.scale_,
    )
    print(f"\n  Saved: {output_path}")
    print(f"         Arrays: X, y_bolt, y_severity, y_binary, "
          f"feature_names, case_numbers, freq_grid, scaler_mean, scaler_scale")

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
    args = parser.parse_args()

    try:
        build_training_matrix(
            args.db,
            args.output,
            ratio_threshold=args.ratio_threshold,
            spectral_dof=args.spectral_dof,
            spectral_dtype=args.spectral_dtype,
        )
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
