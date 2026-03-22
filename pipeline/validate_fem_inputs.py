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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Validate FEM pipeline inputs")
    parser.add_argument('--config', help='Path to config.yaml')
    args = parser.parse_args()
    sys.exit(0 if validate(args.config) else 1)
