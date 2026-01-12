"""
Compute delta between current and baseline acceleration results
Delta = baseline - current
"""
import pandas as pd
import argparse

def compute_delta(current_file, baseline_file, output_file):
    print(f"Computing delta...")
    print(f"  Current: {current_file}")
    print(f"  Baseline: {baseline_file}")
    
    # Read files
    current = pd.read_csv(current_file)
    baseline = pd.read_csv(baseline_file)
    
    # Verify measurement columns match
    if not current['Measurement'].equals(baseline['Measurement']):
        print("WARNING: Measurement columns don't match!")
    
    # Create delta dataframe
    delta = baseline.copy()
    
    # Compute: baseline - current
    for col in current.columns:
        if col != 'Measurement':
            delta[col] = baseline[col] - current[col]
            # Set values < 1e-6 to zero
            delta[col] = delta[col].apply(lambda x: 0 if abs(x) < 1e-6 else x)
    
    # Save
    delta.to_csv(output_file, index=False, float_format='%.10g')
    print(f"  Output: {output_file}")
    print("Delta computation complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--current', required=True, help='Current acceleration results CSV')
    parser.add_argument('--baseline', required=True, help='Baseline acceleration results CSV')
    parser.add_argument('--output', required=True, help='Output delta CSV file')
    args = parser.parse_args()
    
    compute_delta(args.current, args.baseline, args.output)
