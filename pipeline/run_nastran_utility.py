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
        cmd = [nastran_exe, dat_path, 'scratch=no']
        log(f"  Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=run_folder, capture_output=True, text=True, timeout=1800)
        log(f"  Exit code: {result.returncode}")
        if result.stdout:
            log(f"  stdout: {result.stdout.strip()}")
        if result.stderr:
            log(f"  stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            log("ERROR: SOL 103 failed")
            # Still collect outputs for diagnostics
            _collect_outputs(run_folder)
            return run_folder

    if analysis_type == 'full':
        # Wait for DBALL to be fully written
        log("Waiting 10 seconds for DBALL to flush...")
        time.sleep(10)

    if analysis_type in ('sol111', 'full'):
        # SOL 111 — random response
        log("Running SOL 111 (random response)...")
        rand_path = os.path.join(run_folder, random_response)
        cmd = [nastran_exe, rand_path]
        log(f"  Command: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=run_folder, capture_output=True, text=True, timeout=1800)
        log(f"  Exit code: {result.returncode}")
        if result.stdout:
            log(f"  stdout: {result.stdout.strip()}")
        if result.stderr:
            log(f"  stderr: {result.stderr.strip()}")

        if result.returncode != 0:
            log("WARNING: SOL 111 returned non-zero exit code")

    # --- Collect all Nastran outputs ---
    _collect_outputs(run_folder)

    log(f"\nRun complete. All outputs in: {run_folder}")
    return run_folder


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
