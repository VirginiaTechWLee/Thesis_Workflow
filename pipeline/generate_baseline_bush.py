"""
Generate baseline Bush.blk in Femap format from config.yaml.

Femap format = alternating comment lines and PBUSH cards, with 8-char
fixed-width Nastran fields. This is the format HEEDS expects when using
charCol-based tags to modify K4/K5/K6 stiffness values.

Row mapping (0-based, for HEEDS tags):
    Bolt 1 PBUSH = row 1
    Bolt 2 PBUSH = row 3
    Bolt N PBUSH = row 2*N - 1

Usage:
    python pipeline/generate_baseline_bush.py
    python pipeline/generate_baseline_bush.py --output Misc/Bush.blk
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config, nastran_field


def generate_baseline_bush(config_path=None, output_path='Bush.blk'):
    """Generate baseline Bush.blk in Femap format."""
    config = load_config(config_path)

    total_bolts = config['bolts']['total']
    trans_k = config['bolts']['translational_stiffness']
    driving = config['bolts']['driving_stiffness']
    baseline = config['bolts']['baseline_stiffness']
    driving_bolt = config['bolts']['driving_bolt']

    k_trans = nastran_field(trans_k)

    with open(output_path, 'w') as f:
        for bolt_id in range(1, total_bolts + 1):
            if bolt_id == driving_bolt:
                name = f"Driving Cbush_{bolt_id}"
                k4 = nastran_field(driving['K4'])
                k5 = nastran_field(driving['K5'])
                k6 = nastran_field(driving['K6'])
            else:
                name = f"Cbush_{bolt_id}"
                k4 = nastran_field(baseline)
                k5 = nastran_field(baseline)
                k6 = nastran_field(baseline)

            # Femap comment line
            f.write(f"$ Femap Property {bolt_id} : {name}\n")
            # PBUSH card: standard 8-char fixed-width Nastran format
            # Field positions: 0-7=PBUSH, 8-15=PID, 16-23=K, 24-31=K1,
            #                  32-39=K2, 40-47=K3, 48-55=K4, 56-63=K5, 64-71=K6
            f.write(f"{'PBUSH':<8s}{bolt_id:>8d}{'K':>8s}"
                    f"{k_trans}{k_trans}{k_trans}{k4}{k5}{k6}\n")

    print(f"Generated baseline Bush.blk: {output_path}")
    print(f"  {total_bolts} bolts, driving bolt {driving_bolt}")
    print(f"  Driving: K4={driving['K4']:.0e}, K5={driving['K5']:.0e}, K6={driving['K6']:.0e}")
    print(f"  Healthy: K4=K5=K6={baseline:.0e}")
    return output_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate baseline Bush.blk from config")
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--output', '-o', default='Bush.blk')
    args = parser.parse_args()
    generate_baseline_bush(args.config, args.output)
