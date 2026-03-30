"""
Nastran Utility Runner — standalone FEM validation and troubleshooting.

Creates a timestamped folder under FEM_Utility/, copies FEM inputs,
runs Nastran (SOL 103 / SOL 111 / full DBALL chain), and collects
all outputs in one flat folder.

Usage:
    python pipeline/run_nastran_utility.py
    python pipeline/run_nastran_utility.py --config path/to/config.yaml
    python pipeline/run_nastran_utility.py --type sol103
"""

import sys
import os
import shutil
import subprocess
import time
import glob as globmod
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def _wait_for_nastran(f06_path, timeout=600, poll_interval=5):
    """Wait for Nastran to finish by polling the .f06 file for END OF JOB.

    nastranw.exe is a launcher — it spawns Nastran and returns immediately
    with exit code 0. We must poll for completion markers in the output.

    Returns True if Nastran completed, False if timed out.
    """
    log(f"  Waiting for Nastran to finish (polling {f06_path})...")
    start = time.time()
    last_size = 0

    while time.time() - start < timeout:
        time.sleep(poll_interval)

        if not os.path.exists(f06_path):
            elapsed = int(time.time() - start)
            log(f"  [{elapsed}s] f06 not yet created...")
            continue

        size = os.path.getsize(f06_path)
        if size != last_size:
            last_size = size

        # Check for completion marker
        try:
            with open(f06_path, 'r', errors='ignore') as f:
                content = f.read()
            if '* * * END OF JOB * * *' in content:
                elapsed = int(time.time() - start)
                log(f"  Nastran completed in {elapsed}s")
                # Check for fatal errors
                if 'USER FATAL MESSAGE' in content:
                    log("  WARNING: FATAL messages found in f06!")
                    # Extract fatal lines
                    for line in content.splitlines():
                        if 'FATAL' in line:
                            log(f"    {line.strip()}")
                    return False
                return True
        except Exception:
            pass

        elapsed = int(time.time() - start)
        log(f"  [{elapsed}s] Still running... (f06 size: {size:,} bytes)")

    log(f"  TIMEOUT: Nastran did not finish within {timeout}s")
    return False


def _cleanup_old_runs(base_dir, study_name, keep_last):
    """Delete oldest run folders for this study, keeping only the most recent `keep_last`."""
    # Find all timestamped folders matching this study name
    prefix = f"{study_name}_"
    folders = []
    for entry in os.listdir(base_dir):
        full_path = os.path.join(base_dir, entry)
        if os.path.isdir(full_path) and entry.startswith(prefix):
            folders.append(full_path)

    # Sort by name (timestamp suffix ensures chronological order)
    folders.sort()

    # Delete oldest, keeping `keep_last` slots (minus 1 for the new run about to be created)
    to_delete = folders[:max(0, len(folders) - keep_last + 1)]
    for folder in to_delete:
        log(f"Cleaning up old run: {os.path.basename(folder)}")
        shutil.rmtree(folder, ignore_errors=True)


def run_nastran_utility(config_path=None, analysis_type_override=None):
    """Run standalone Nastran utility. Returns path to timestamped output folder."""
    config = load_config(config_path)

    # --- Paths ---
    nastran_exe = config['paths']['nastran_exe']
    fem_dir = config['files'].get('fem_input_dir', 'fem_input')
    structural_model = config['files'].get('structural_model', 'Fixed_base_beam.dat')
    random_response = config['files'].get('random_response', 'RandomBeamX.dat')
    bush_file = config['files'].get('bush_template', 'Bush.blk')
    study_name = config['study'].get('name', 'utility_run')

    # Analysis type: CLI override > config > default
    analysis_type = analysis_type_override or config.get('analysis', {}).get('type', 'full')

    # FEM_Utility base directory
    fem_utility_base = os.path.join(os.environ.get('USERPROFILE', r'C:\Users\waynelee'),
                                     'Documents', 'FEM_Utility')
    os.makedirs(fem_utility_base, exist_ok=True)

    # --- Cleanup old runs ---
    keep_last = int(config.get('analysis', {}).get('keep_last_runs', 5))
    if keep_last > 0:
        _cleanup_old_runs(fem_utility_base, study_name, keep_last)

    # --- Create timestamped folder ---
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_folder = os.path.join(fem_utility_base, f"{study_name}_{timestamp}")
    os.makedirs(run_folder)
    log(f"Created run folder: {run_folder}")

    # --- Copy input files ---
    files_to_copy = []

    # Structural model — check fem_input/ first, then templates/
    dat_src = os.path.join(fem_dir, structural_model)
    if not os.path.exists(dat_src):
        dat_src = os.path.join('templates', structural_model)
    if os.path.exists(dat_src):
        files_to_copy.append((dat_src, structural_model))
    else:
        log(f"ERROR: Structural model not found: {structural_model}")
        return None

    # Bush.blk
    bush_src = os.path.join(fem_dir, bush_file)
    if not os.path.exists(bush_src):
        bush_src = os.path.join('templates', bush_file)
    if os.path.exists(bush_src):
        files_to_copy.append((bush_src, bush_file))

    # RandomBeamX.dat (needed for full/sol111)
    if analysis_type in ('full', 'sol111'):
        rand_src = os.path.join(fem_dir, random_response)
        if not os.path.exists(rand_src):
            rand_src = os.path.join('templates', random_response)
        if os.path.exists(rand_src):
            files_to_copy.append((rand_src, random_response))
        else:
            log(f"ERROR: Random response deck not found: {random_response}")
            return None

    # Recoveries.blk (if referenced by DAT)
    recoveries_src = os.path.join(fem_dir, 'Recoveries.blk')
    if not os.path.exists(recoveries_src):
        recoveries_src = os.path.join('templates', 'Recoveries.blk')
    if os.path.exists(recoveries_src):
        files_to_copy.append((recoveries_src, 'Recoveries.blk'))

    # Copy all files
    for src, name in files_to_copy:
        dst = os.path.join(run_folder, name)
        shutil.copy2(src, dst)
        log(f"  Copied: {name}")

    # --- Run Nastran ---
    log(f"Analysis type: {analysis_type}")
    log(f"Nastran: {nastran_exe}")

    if analysis_type in ('sol103', 'full'):
        # SOL 103 — modal analysis with scratch=no to preserve DBALL
        log("Running SOL 103 (modal analysis)...")
        dat_path = os.path.join(run_folder, structural_model)
        model_stem = os.path.splitext(structural_model)[0].lower()
        f06_path = os.path.join(run_folder, f"{model_stem}.f06")
        cmd = [nastran_exe, dat_path, 'scratch=no']
        log(f"  Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=run_folder, capture_output=True, text=True, timeout=60)
        log(f"  Launcher exit code: {result.returncode}")

        # nastranw.exe is a launcher — wait for actual completion
        sol103_ok = _wait_for_nastran(f06_path, timeout=600)
        if not sol103_ok:
            log("ERROR: SOL 103 failed or timed out")
            _collect_outputs(run_folder)
            return run_folder

    if analysis_type == 'full':
        # Brief pause to ensure DBALL file handles are released
        log("Waiting 5 seconds for DBALL to flush...")
        time.sleep(5)

    if analysis_type in ('sol111', 'full'):
        # SOL 111 — random response (restart from SOL 103 DBALL)
        log("Running SOL 111 (random response)...")
        rand_path = os.path.join(run_folder, random_response)
        rand_stem = os.path.splitext(random_response)[0].lower()
        f06_sol111 = os.path.join(run_folder, f"{rand_stem}.f06")
        cmd = [nastran_exe, rand_path]
        log(f"  Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=run_folder, capture_output=True, text=True, timeout=60)
        log(f"  Launcher exit code: {result.returncode}")

        # Wait for actual completion
        sol111_ok = _wait_for_nastran(f06_sol111, timeout=600)
        if not sol111_ok:
            log("ERROR: SOL 111 failed or timed out")
            _collect_outputs(run_folder)
            # Check for specific known issues
            if os.path.exists(f06_sol111):
                with open(f06_sol111, 'r', errors='ignore') as f:
                    content = f.read()
                if 'PARAM,DDRMM' in content:
                    log("HINT: Add PARAM,DDRMM,-1 to bulk data for ESE support")
            return run_folder

        # Verify PCH file was produced (XYPUNCH output)
        pch_files = globmod.glob(os.path.join(run_folder, '*.pch'))
        if pch_files:
            for pf in pch_files:
                log(f"  PCH output: {os.path.basename(pf)} ({os.path.getsize(pf):,} bytes)")
        else:
            log("WARNING: No .pch file found — XYPUNCH may not have produced output")

    # --- Collect all Nastran outputs ---
    _collect_outputs(run_folder)

    # --- Publish to stable path for downstream pipeline consumption ---
    _publish_to_stable_path(run_folder, config)

    log(f"\nRun complete. All outputs in: {run_folder}")
    return run_folder


def _publish_to_stable_path(run_folder, config):
    """Copy report + images to a stable path so downstream scripts always find them.

    Publishes to D:\\thesis_database\\fem_utility\\ (or db_dir/fem_utility from config).
    This path never changes — every downstream script reads from here.
    The timestamped folder is the archive; this is the live copy.
    """
    db_dir = config.get('paths', {}).get('db_dir', r'D:\thesis_database')
    stable_dir = os.path.join(db_dir, 'fem_utility')
    os.makedirs(stable_dir, exist_ok=True)

    published = []
    # Copy all reports and images
    extensions = {'.md', '.pdf', '.docx', '.png', '.jpg', '.svg'}
    for fname in os.listdir(run_folder):
        ext = os.path.splitext(fname)[1].lower()
        if ext in extensions:
            src = os.path.join(run_folder, fname)
            dst = os.path.join(stable_dir, fname)
            shutil.copy2(src, dst)
            published.append(fname)

    # Write a manifest so downstream scripts know what's available
    manifest_path = os.path.join(stable_dir, 'manifest.txt')
    with open(manifest_path, 'w') as f:
        f.write(f"# FEM Utility — published {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Source: {run_folder}\n")
        for fname in sorted(published):
            f.write(f"{fname}\n")

    if published:
        log(f"Published {len(published)} files to {stable_dir}")
        for fname in published:
            log(f"  -> {fname}")
    else:
        log(f"WARNING: No reports or images found to publish from {run_folder}")


def _collect_outputs(run_folder):
    """List all files in the run folder (everything stays flat, no subdirectories)."""
    log("\n=== Output Files ===")
    for f in sorted(os.listdir(run_folder)):
        fpath = os.path.join(run_folder, f)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            log(f"  {f} ({size:,} bytes)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Nastran Utility Runner")
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--type', choices=['sol103', 'sol111', 'full'],
                        help='Analysis type override (default: from config)')
    args = parser.parse_args()

    run_folder = run_nastran_utility(args.config, args.type)
    if run_folder:
        # Write path to GITHUB_OUTPUT if available (for workflow chaining)
        github_output = os.environ.get('GITHUB_OUTPUT')
        if github_output:
            with open(github_output, 'a') as f:
                f.write(f"RUN_FOLDER={run_folder}\n")
        sys.exit(0)
    else:
        sys.exit(1)
