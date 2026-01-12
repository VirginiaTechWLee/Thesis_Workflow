"""
Verify that delta file contains all zeros (within tolerance)
Used for baseline verification runs
"""
import pandas as pd
import sys
import argparse

def verify_zero(delta_file, tolerance=1e-6):
    print(f"Verifying delta is zero: {delta_file}")
    print(f"  Tolerance: {tolerance}")
    
    delta = pd.read_csv(delta_file)
    
    failed = False
    for col in delta.columns:
        if col != 'Measurement':
            max_delta = delta[col].abs().max()
            if max_delta > tolerance:
                print(f"  x Column {col}: max delta = {max_delta} (exceeds tolerance)")
                failed = True
            else:
                print(f"  v Column {col}: max delta = {max_delta}")
    
    if failed:
        print("\nERROR: Delta verification failed!")
        sys.exit(1)
    else:
        print("\nv SUCCESS: All deltas are zero (within tolerance)")
        sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('delta_file', help='Delta CSV file to verify')
    parser.add_argument('--tolerance', type=float, default=1e-6, help='Tolerance for zero check')
    args = parser.parse_args()
    
    verify_zero(args.delta_file, args.tolerance)
