"""
Validate that fem_input/ contains required files and config.yaml is well-formed.

Usage:
    python pipeline/validate_fem_inputs.py
    python pipeline/validate_fem_inputs.py --config path/to/config.yaml
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config


def validate(config_path=None):
    """Validate FEM inputs. Returns True if all checks pass."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"[FAIL] Cannot load config: {e}")
        return False

    errors = []
    warnings = []

    # --- Check required config sections ---
    required_sections = ['study', 'files', 'bolts', 'output_nodes', 'dof_mapping', 'peaks', 'paths']
    for section in required_sections:
        if section not in config:
            errors.append(f"Missing config section: {section}")

    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        return False

    # --- Check study section ---
    study = config['study']
    for key in ['name', 'type']:
        if key not in study:
            errors.append(f"Missing study.{key}")
    if study.get('type') == 'sweep':
        if 'sweep_bolts' not in study:
            errors.append("sweep study requires study.sweep_bolts")
        if 'sweep_levels' not in study:
            errors.append("sweep study requires study.sweep_levels")
        if 'expected_designs' not in study:
            warnings.append("study.expected_designs not set, will infer from sweep_levels")

    # --- Check FEM files exist ---
    fem_dir = config['files'].get('fem_input_dir', 'fem_input')
    required_files = [
        config['files'].get('structural_model', 'Fixed_base_beam.dat'),
        config['files'].get('bush_template', 'Bush.blk'),
    ]
    for fname in required_files:
        fpath = os.path.join(fem_dir, fname)
        if not os.path.exists(fpath):
            errors.append(f"Missing FEM file: {fpath}")

    # --- Check bolt configuration ---
    bolts = config['bolts']
    if 'total' not in bolts:
        errors.append("Missing bolts.total")
    if 'driving_bolt' not in bolts:
        errors.append("Missing bolts.driving_bolt")
    if 'driving_stiffness' not in bolts:
        errors.append("Missing bolts.driving_stiffness")
    if 'baseline_stiffness' not in bolts:
        errors.append("Missing bolts.baseline_stiffness")

    # --- Check solver paths ---
    paths = config['paths']
    for key in ['nastran_exe', 'python_exe', 'heeds_python']:
        if key not in paths:
            warnings.append(f"Missing paths.{key}")

    # --- Report ---
    for w in warnings:
        print(f"[WARN] {w}")
    if errors:
        for e in errors:
            print(f"[FAIL] {e}")
        return False

    print(f"[PASS] Config validated: {config['study']['name']}")
    print(f"  Bolts: {bolts.get('total', '?')}, Driving: {bolts.get('driving_bolt', '?')}")
    print(f"  Nodes: {len(config.get('output_nodes', []))}")
    print(f"  FEM dir: {fem_dir}")
    return True


def validate_dball_readiness(config_path=None):
    """Validate that FEM inputs are ready for the DBALL chain (Nastran Utility Workflow).
    Returns True if all checks pass."""
    try:
        config = load_config(config_path)
    except Exception as e:
        print(f"[FAIL] Cannot load config: {e}")
        return False

    errors = []
    fem_dir = config.get('files', {}).get('fem_input_dir', 'fem_input')
    structural_model = config.get('files', {}).get('structural_model', 'Fixed_base_beam.dat')
    random_response = config.get('files', {}).get('random_response', 'RandomBeamX.dat')
    analysis_type = config.get('analysis', {}).get('type', 'full')

    dat_path = os.path.join(fem_dir, structural_model)

    # --- Check 1: DAT file uses SOL SEMODES or SOL 103 ---
    if os.path.exists(dat_path):
        with open(dat_path, 'r', errors='ignore') as f:
            dat_content = f.read()
        import re
        sol_match = re.search(r'^\s*SOL\s+(SEMODES|103)\b', dat_content, re.MULTILINE | re.IGNORECASE)
        if not sol_match:
            errors.append(f"DAT file does not use SOL SEMODES or SOL 103: {dat_path}")
        else:
            print(f"[PASS] SOL type: {sol_match.group(1)}")

        # --- Check 2: scratch=no present (preserves DBALL between runs) ---
        # Check for scratch=no in DAT or in Nastran command line args
        # In practice this is set in the BAT file, so we check DAT for INIT MASTER
        init_match = re.search(r'INIT\s+MASTER', dat_content, re.IGNORECASE)
        if init_match:
            print("[PASS] INIT MASTER(S) found — DBALL will be preserved")
        else:
            # Not fatal — scratch=no can be passed on the command line
            print("[WARN] No INIT MASTER in DAT — ensure scratch=no is passed on Nastran command line")

        # --- Check 3: At least one SPC boundary condition (no free-free) ---
        spc_match = re.search(r'^\s*SPC1?\s+', dat_content, re.MULTILINE)
        if not spc_match:
            errors.append("No SPC boundary condition found — free-free models not supported for DBALL chain")
        else:
            print("[PASS] SPC boundary condition found")
    else:
        errors.append(f"Structural model not found: {dat_path}")

    # --- Check 4: RandomBeamX.dat exists (required for full/sol111 runs) ---
    if analysis_type in ('full', 'sol111'):
        rand_path = os.path.join(fem_dir, random_response)
        # Also check templates/ directory
        rand_template = os.path.join('templates', random_response)
        if os.path.exists(rand_path):
            print(f"[PASS] Random response deck found: {rand_path}")
            rand_file_path = rand_path
        elif os.path.exists(rand_template):
            print(f"[PASS] Random response deck found: {rand_template}")
            rand_file_path = rand_template
        else:
            errors.append(f"Random response deck not found for {analysis_type} run: {random_response} (checked {fem_dir}/ and templates/)")
            rand_file_path = None

        # --- Check 5: DLOAD or RANDPS cards in random response deck ---
        if rand_file_path and os.path.exists(rand_file_path):
            with open(rand_file_path, 'r', errors='ignore') as f:
                rand_content = f.read()
            has_dload = re.search(r'^\s*DLOAD\b', rand_content, re.MULTILINE | re.IGNORECASE)
            has_randps = re.search(r'^\s*RANDPS\b', rand_content, re.MULTILINE | re.IGNORECASE)
            if has_dload or has_randps:
                found = []
                if has_dload: found.append('DLOAD')
                if has_randps: found.append('RANDPS')
                print(f"[PASS] Random response cards found: {', '.join(found)}")
            else:
                errors.append(f"No DLOAD or RANDPS cards found in {rand_file_path} — required for random response analysis")

    if errors:
        print("\n=== DBALL READINESS CHECK FAILED ===")
        for e in errors:
            print(f"[FAIL] {e}")
        return False

    print(f"\n[PASS] DBALL readiness validated for analysis type: {analysis_type}")
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Validate FEM pipeline inputs")
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--dball', action='store_true', help='Run DBALL readiness checks for Nastran Utility')
    args = parser.parse_args()

    ok = validate(args.config)
    if args.dball:
        ok = ok and validate_dball_readiness(args.config)
    sys.exit(0 if ok else 1)
