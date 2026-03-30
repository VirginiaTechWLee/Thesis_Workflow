"""
Compute Miles equation parameters from PSD data and populate the miles table.

For each case, node, DOF, and resonance peak:
  1. fn  = peak frequency (from peaks table)
  2. Q   = quality factor = fn / half-power bandwidth
  3. PSD_fn = PSD amplitude at fn
  4. GRMS = sqrt(pi/2 * fn * Q * PSD_fn)
  5. bandwidth = fn / Q (half-power bandwidth in Hz)

Usage:
    python compute_miles.py --db_path D:\\thesis_database\\thesis_results.db
    python compute_miles.py --db_path D:\\thesis_database\\thesis_results.db --study study_A_single_bolt_sweep
"""

import argparse
import math
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np


def half_power_bandwidth(freqs, psd_values, peak_idx):
    """
    Compute the half-power (-3dB) bandwidth around a peak.

    The half-power points are where PSD drops to PSD_peak / 2.
    Bandwidth = f_upper - f_lower at the half-power level.

    Returns (bandwidth_hz, f_lower, f_upper) or (None, None, None) if
    the half-power points can't be found (peak at edge, flat spectrum, etc.)
    """
    peak_psd = psd_values[peak_idx]
    if peak_psd <= 0:
        return None, None, None

    half_power = peak_psd / 2.0

    # Search left from peak for half-power crossing
    f_lower = None
    for i in range(peak_idx, 0, -1):
        if psd_values[i] <= half_power:
            # Linear interpolation between i and i+1
            frac = (half_power - psd_values[i]) / (psd_values[i + 1] - psd_values[i])
            f_lower = freqs[i] + frac * (freqs[i + 1] - freqs[i])
            break

    # Search right from peak for half-power crossing
    f_upper = None
    for i in range(peak_idx, len(freqs) - 1):
        if psd_values[i] <= half_power:
            # Linear interpolation between i-1 and i
            frac = (half_power - psd_values[i - 1]) / (psd_values[i] - psd_values[i - 1])
            f_upper = freqs[i - 1] + frac * (freqs[i] - freqs[i - 1])
            break

    if f_lower is not None and f_upper is not None:
        return f_upper - f_lower, f_lower, f_upper
    return None, None, None


def compute_miles_for_case(conn, case_id, max_peaks=3):
    """
    Compute Miles equation values for all node/DOF channels of a single case.

    Returns list of dicts ready for INSERT into miles table.
    """
    c = conn.cursor()
    rows = []

    # Get all peaks for this case (tells us where resonances are)
    c.execute(
        "SELECT node_id, dof, data_type, peak1_freq, peak1_psd, "
        "peak2_freq, peak2_psd, peak3_freq, peak3_psd "
        "FROM peaks WHERE case_id = ?",
        (case_id,),
    )
    peak_records = c.fetchall()

    for node_id, dof, data_type, p1f, p1p, p2f, p2p, p3f, p3p in peak_records:
        # Collect the peaks for this channel
        channel_peaks = []
        if p1f is not None and p1p is not None and p1p > 0:
            channel_peaks.append((1, p1f, p1p))
        if p2f is not None and p2p is not None and p2p > 0:
            channel_peaks.append((2, p2f, p2p))
        if p3f is not None and p3p is not None and p3p > 0:
            channel_peaks.append((3, p3f, p3p))

        if not channel_peaks:
            continue

        # Load the full PSD curve for this channel to compute Q
        c.execute(
            "SELECT frequency, psd_value FROM psd_data "
            "WHERE case_id = ? AND node_id = ? AND dof = ? AND data_type = ? "
            "ORDER BY frequency",
            (case_id, node_id, dof, data_type),
        )
        psd_raw = c.fetchall()
        if len(psd_raw) < 10:
            continue

        freqs = np.array([r[0] for r in psd_raw])
        psds = np.array([r[1] for r in psd_raw])

        for mode_num, fn, psd_fn in channel_peaks:
            # Find the closest index to fn in the PSD curve
            peak_idx = np.argmin(np.abs(freqs - fn))

            # Compute half-power bandwidth → Q
            bw, f_lo, f_hi = half_power_bandwidth(freqs, psds, peak_idx)

            if bw is not None and bw > 0 and fn > 0:
                Q = fn / bw
                # Miles equation: GRMS = sqrt(pi/2 * fn * Q * PSD(fn))
                grms = math.sqrt(math.pi / 2.0 * fn * Q * psd_fn)
            else:
                # Can't compute Q — store fn and PSD_fn but leave Q/grms as None
                Q = None
                grms = None
                bw = None

            rows.append({
                "case_id": case_id,
                "node_id": node_id,
                "dof": dof,
                "data_type": data_type,
                "mode_number": mode_num,
                "fn": fn,
                "Q": Q,
                "PSD_fn": psd_fn,
                "grms": grms,
                "bandwidth": bw,
            })

    return rows


def populate_miles_table(db_path, study_name=None, reset=False):
    """
    Compute and insert Miles equation data for all cases in the database.

    Args:
        db_path: Path to SQLite database
        study_name: Optional — only process cases from this study
        reset: If True, delete existing miles data before inserting
    """
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Optional reset
    if reset:
        if study_name:
            c.execute(
                "DELETE FROM miles WHERE case_id IN "
                "(SELECT case_id FROM cases JOIN studies ON cases.study_id = studies.study_id "
                "WHERE studies.study_name = ?)",
                (study_name,),
            )
            print(f"Reset: deleted {c.rowcount} miles rows for {study_name}")
        else:
            c.execute("DELETE FROM miles")
            print(f"Reset: deleted {c.rowcount} miles rows")
        conn.commit()

    # Get cases to process
    if study_name:
        c.execute(
            "SELECT c.case_id, c.case_name FROM cases c "
            "JOIN studies s ON c.study_id = s.study_id "
            "WHERE s.study_name = ? ORDER BY c.case_number",
            (study_name,),
        )
    else:
        c.execute("SELECT case_id, case_name FROM cases ORDER BY case_id")
    cases = c.fetchall()

    print(f"Computing Miles equation for {len(cases)} cases...")
    t0 = time.time()
    total_inserted = 0
    COMMIT_EVERY = 50

    for i, (case_id, case_name) in enumerate(cases, 1):
        rows = compute_miles_for_case(conn, case_id)

        for row in rows:
            c.execute(
                "INSERT OR REPLACE INTO miles "
                "(case_id, node_id, dof, data_type, mode_number, fn, Q, PSD_fn, grms, bandwidth) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["case_id"], row["node_id"], row["dof"], row["data_type"],
                 row["mode_number"], row["fn"], row["Q"], row["PSD_fn"],
                 row["grms"], row["bandwidth"]),
            )
        total_inserted += len(rows)

        elapsed = time.time() - t0
        rate = i / elapsed if elapsed > 0 else 0
        eta = (len(cases) - i) / rate if rate > 0 else 0

        if i % 50 == 0 or i == len(cases):
            print(f"  [{i}/{len(cases)}] {rate:.1f} cases/s, "
                  f"ETA {eta:.0f}s, {total_inserted} miles rows", flush=True)

        if i % COMMIT_EVERY == 0:
            conn.commit()

    conn.commit()
    elapsed = time.time() - t0
    print(f"\nDone! {total_inserted} miles rows inserted in {elapsed:.1f}s")

    # Summary
    c.execute("SELECT COUNT(*) FROM miles")
    print(f"Total miles rows in DB: {c.fetchone()[0]}")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute Miles equation from PSD data")
    parser.add_argument("--db_path", required=True, help="Path to SQLite database")
    parser.add_argument("--study", default=None, help="Study name (optional, processes all if omitted)")
    parser.add_argument("--reset", action="store_true", help="Delete existing miles data before computing")
    args = parser.parse_args()

    if not Path(args.db_path).exists():
        print(f"ERROR: Database not found: {args.db_path}")
        sys.exit(1)

    populate_miles_table(args.db_path, study_name=args.study, reset=args.reset)
