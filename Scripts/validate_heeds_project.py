"""
Pre-flight validation checks for HEEDS project
"""
import xml.etree.ElementTree as ET
import os
import sys
import argparse

def validate_heeds_project(heeds_file, templates_dir, baseline_dir):
    print(f"="*60)
    print(f"HEEDS Project Validation")
    print(f"="*60)
    print(f"Project file: {heeds_file}\n")
    
    # Check file exists
    if not os.path.exists(heeds_file):
        print(f"x ERROR: HEEDS file not found: {heeds_file}")
        sys.exit(1)
    print(f"v HEEDS file exists")
    
    # Parse XML
    try:
        tree = ET.parse(heeds_file)
        root = tree.getroot()
        print(f"v XML parsing successful")
    except Exception as e:
        print(f"x ERROR: Failed to parse XML: {e}")
        sys.exit(1)
    
    # Check template files exist
    required_templates = [
        os.path.join(templates_dir, 'Fixed_base_beam.dat'),
    ]
    
    for template in required_templates:
        if not os.path.exists(template):
            print(f"x ERROR: Template file missing: {template}")
            sys.exit(1)
        print(f"v Template found: {os.path.basename(template)}")
    
    # Check baseline files exist
    baseline_csv = os.path.join(baseline_dir, 'acceleration_results.csv')
    if not os.path.exists(baseline_csv):
        print(f"x ERROR: Baseline file missing: {baseline_csv}")
        sys.exit(1)
    print(f"v Baseline found: {os.path.basename(baseline_csv)}")
    
    print(f"\n{'='*60}")
    print(f"v All validation checks passed!")
    print(f"{'='*60}\n")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--heeds_file', required=True)
    parser.add_argument('--templates_dir', required=True)
    parser.add_argument('--baseline_dir', required=True)
    args = parser.parse_args()
    
    validate_heeds_project(args.heeds_file, args.templates_dir, args.baseline_dir)
