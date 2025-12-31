# Thesis Workflow Setup Script
# Root: C:\Users\waynelee\Documents
# Run this script to organize all files and create workflows

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Thesis Workflow Setup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Ensure we're in Documents folder
Set-Location C:\Users\waynelee\Documents

# Step 1: Create directory structure
Write-Host "Creating directory structure..." -ForegroundColor Yellow

$directories = @(
    ".github",
    ".github\workflows",
    "Scripts",
    "templates", 
    "baseline",
    "current_run",
    "heeds_projects",
    "heeds_results"
)

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -Path $dir -ItemType Directory | Out-Null
        Write-Host "  Created: $dir" -ForegroundColor Green
    } else {
        Write-Host "  Exists: $dir" -ForegroundColor Gray
    }
}

Write-Host ""

# Step 2: Move existing files to proper locations
Write-Host "Moving files to proper locations..." -ForegroundColor Yellow

# Move Pch_TO_CSV2.py to Scripts (if exists in root)
if (Test-Path "Pch_TO_CSV2.py") {
    Move-Item "Pch_TO_CSV2.py" "Scripts\" -Force
    Write-Host "  Moved: Pch_TO_CSV2.py -> Scripts\" -ForegroundColor Green
}

# Move templates
$templateFiles = @("Fixed_base_beam.dat", "Recoveries.blk")
foreach ($file in $templateFiles) {
    if (Test-Path $file) {
        Move-Item $file "templates\" -Force
        Write-Host "  Moved: $file -> templates\" -ForegroundColor Green
    }
}

# Move existing Scripts folder contents
if (Test-Path "Scripts\Scripts") {
    Get-ChildItem "Scripts\Scripts" | Move-Item -Destination "Scripts\" -Force
    Remove-Item "Scripts\Scripts" -Recurse -Force
    Write-Host "  Merged: Scripts\Scripts -> Scripts\" -ForegroundColor Green
}

# Copy HEEDS files to heeds_projects
$heedsFiles = @("Square_Beam_scenario_short_rev.heeds")
foreach ($file in $heedsFiles) {
    if (Test-Path $file) {
        Copy-Item $file "heeds_projects\" -Force
        Write-Host "  Copied: $file -> heeds_projects\" -ForegroundColor Green
    }
}

# Move baseline files
if (Test-Path "acceleration_results_baseline.csv") {
    Copy-Item "acceleration_results_baseline.csv" "baseline\acceleration_results.csv" -Force
    Write-Host "  Copied: baseline CSV -> baseline\" -ForegroundColor Green
}

$baselineFiles = @("fixed_base_beam.f06", "fixed_base_beam.MASTER")
foreach ($file in $baselineFiles) {
    if (Test-Path $file) {
        Copy-Item $file "baseline\" -Force
        Write-Host "  Copied: $file -> baseline\" -ForegroundColor Green
    }
}

if (Test-Path "Bush.blk") {
    Copy-Item "Bush.blk" "baseline\" -Force
    Write-Host "  Copied: Bush.blk -> baseline\" -ForegroundColor Green
}

Write-Host ""

# Step 3: Create .gitignore
Write-Host "Creating .gitignore..." -ForegroundColor Yellow

$gitignoreContent = @"
# Temporary working files
work/
*.tmp

# Nastran outputs in root (only commit in baseline/ and organized folders)
/*.MASTER
/*.op2
/*.pch
/*.f06
/*.log
/*.bdf

# Python cache
__pycache__/
*.pyc
*.pyo

# OS files
desktop.ini
.DS_Store
Thumbs.db

# Temporary CSV files in root
/acceleration_results.csv
/displacement_results.csv

# Old/test files
RandomBeamX.dat
randombeamx.*
FBM_TO_DBALL.bat

# Folders to exclude
Generate heeds file/
New folder/

# Keep these directories
!baseline/
!current_run/
!heeds_projects/
!heeds_results/
!Scripts/
!templates/
"@

Set-Content -Path ".gitignore" -Value $gitignoreContent
Write-Host "  Created: .gitignore" -ForegroundColor Green
Write-Host ""

# Step 4: Create Python scripts
Write-Host "Creating Python scripts..." -ForegroundColor Yellow

# generate_baseline_bush.py
$generateBaselineBush = @"
"""
Generate baseline Bush.blk configuration
Bolt 1: K4=1e8 (driving CBUSH), K5=1e12, K6=1e12
Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (all healthy)
All bolts: K1=1e6, K2=1e6, K3=1e6 (translational)
"""

def generate_baseline_bush():
    with open('Bush.blk', 'w') as f:
        # Bolt 1 - Driving CBUSH
        f.write("PBUSH   1       K       1.+6    1.+6    1.+6    1.+8    1.+12   1.+12\n")
        
        # Bolts 2-10 - All healthy
        for bolt_id in range(2, 11):
            f.write(f"PBUSH   {bolt_id}       K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12\n")
    
    print("Generated baseline Bush.blk")
    print("  Bolt 1:  K4=1e8 (driving), K5=1e12, K6=1e12")
    print("  Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (healthy)")

if __name__ == "__main__":
    generate_baseline_bush()
"@
Set-Content -Path "Scripts\generate_baseline_bush.py" -Value $generateBaselineBush
Write-Host "  Created: Scripts\generate_baseline_bush.py" -ForegroundColor Green

# compute_delta.py
$computeDelta = @"
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
"@
Set-Content -Path "Scripts\compute_delta.py" -Value $computeDelta
Write-Host "  Created: Scripts\compute_delta.py" -ForegroundColor Green

# verify_delta_zero.py
$verifyDeltaZero = @"
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
"@
Set-Content -Path "Scripts\verify_delta_zero.py" -Value $verifyDeltaZero
Write-Host "  Created: Scripts\verify_delta_zero.py" -ForegroundColor Green

# validate_heeds_project.py
$validateHeeds = @"
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
"@
Set-Content -Path "Scripts\validate_heeds_project.py" -Value $validateHeeds
Write-Host "  Created: Scripts\validate_heeds_project.py" -ForegroundColor Green

Write-Host ""

# Step 5: Create workflow YAML files
Write-Host "Creating GitHub Actions workflows..." -ForegroundColor Yellow

# Workflow 1: Baseline
$workflow1 = @"
name: Baseline Workflow1

on:
  workflow_dispatch:
  
jobs:
  generate-baseline:
    runs-on: self-hosted
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Generate baseline Bush.blk
        run: python Scripts/generate_baseline_bush.py
      
      - name: Clear baseline folder
        run: |
          if (Test-Path baseline) {
            Remove-Item baseline\* -Force
          } else {
            mkdir baseline
          }
      
      - name: Copy files for Nastran run
        run: |
          copy Bush.blk baseline\
          copy templates\Fixed_base_beam.dat .
      
      - name: Run NASTRAN
        run: nastran Fixed_base_beam.dat
      
      - name: Move Nastran outputs to baseline
        run: |
          move fixed_base_beam.pch baseline\
          move fixed_base_beam.f06 baseline\
          move fixed_base_beam.op2 baseline\
          move fixed_base_beam.MASTER baseline\
      
      - name: Extract PCH to CSV
        run: |
          copy baseline\fixed_base_beam.pch .
          python Scripts\Pch_TO_CSV2.py
      
      - name: Save CSV to baseline folder
        run: copy acceleration_results.csv baseline\
      
      - name: Commit baseline to Git
        run: |
          git add baseline\
          git add Bush.blk
          git commit -m "Update baseline - `$(Get-Date -Format 'yyyy-MM-dd HH:mm')"
          git push
"@
Set-Content -Path ".github\workflows\baseline_workflow1.yml" -Value $workflow1
Write-Host "  Created: .github\workflows\baseline_workflow1.yml" -ForegroundColor Green

# Workflow 2: FEM Analysis
$workflow2 = @"
name: FEM Analysis Workflow2

on:
  workflow_dispatch:
    inputs:
      case_number:
        description: 'Case number (0 for baseline verification, 1-73 for parametric cases)'
        required: true
        type: string
      verify_zero:
        description: 'Verify delta is zero (for baseline verification)'
        required: false
        type: boolean
        default: false
  
jobs:
  fem-analysis:
    runs-on: self-hosted
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Generate case-specific Bush.blk
        run: |
          # For now, just copy baseline (we'll create generate_case_bush.py later)
          # Case 0 = baseline verification
          if ("`${{ github.event.inputs.case_number }}" -eq "0") {
            python Scripts/generate_baseline_bush.py
          } else {
            Write-Host "TODO: Generate case `${{ github.event.inputs.case_number }}"
            python Scripts/generate_baseline_bush.py
          }
      
      - name: Setup current_run directory
        run: |
          if (Test-Path current_run) {
            Remove-Item current_run\* -Recurse -Force
          } else {
            mkdir current_run
          }
      
      - name: Copy files for Nastran run
        run: |
          copy Bush.blk current_run\
          copy templates\Fixed_base_beam.dat current_run\
      
      - name: Run NASTRAN
        run: |
          cd current_run
          nastran Fixed_base_beam.dat
          cd ..
      
      - name: Extract features from PCH
        run: |
          copy current_run\fixed_base_beam.pch .
          python Scripts\Pch_TO_CSV2.py
          copy acceleration_results.csv current_run\
      
      - name: Compute delta vs baseline
        run: |
          python Scripts/compute_delta.py ``
            --current current_run/acceleration_results.csv ``
            --baseline baseline/acceleration_results.csv ``
            --output current_run/acceleration_results_delta.csv
      
      - name: Verify delta is zero
        if: `${{ github.event.inputs.verify_zero == 'true' }}
        run: |
          python Scripts/verify_delta_zero.py current_run/acceleration_results_delta.csv
      
      - name: Commit results to Git
        run: |
          git add current_run\
          git commit -m "FEM analysis - Case `${{ github.event.inputs.case_number }} - `$(Get-Date -Format 'yyyy-MM-dd HH:mm')"
          git push
"@
Set-Content -Path ".github\workflows\fem_analysis_workflow2.yml" -Value $workflow2
Write-Host "  Created: .github\workflows\fem_analysis_workflow2.yml" -ForegroundColor Green

# Workflow 3: HEEDS Study
$workflow3 = @"
name: HEEDS Study Workflow3

on:
  workflow_dispatch:
    inputs:
      heeds_file:
        description: 'HEEDS project file (from heeds_projects/)'
        required: true
        type: choice
        options:
          - Square_Beam_scenario_short_rev.heeds
      skip_validation:
        description: 'Skip pre-flight validation checks'
        required: false
        type: boolean
        default: false
  
jobs:
  heeds-study:
    runs-on: self-hosted
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Validate HEEDS project
        if: `${{ github.event.inputs.skip_validation == 'false' }}
        run: |
          python Scripts/validate_heeds_project.py ``
            --heeds_file heeds_projects/`${{ github.event.inputs.heeds_file }} ``
            --templates_dir templates ``
            --baseline_dir baseline
      
      - name: Create timestamped results directory
        id: setup
        run: |
          `$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
          `$results_dir = "heeds_results/run_`$timestamp"
          mkdir `$results_dir
          echo "results_dir=`$results_dir" >> `$env:GITHUB_OUTPUT
          Write-Host "Results will be saved to: `$results_dir"
      
      - name: Copy HEEDS project to results directory
        run: |
          copy heeds_projects\`${{ github.event.inputs.heeds_file }} `${{ steps.setup.outputs.results_dir }}\
      
      - name: Run HEEDS study
        run: |
          cd `${{ steps.setup.outputs.results_dir }}
          heeds `${{ github.event.inputs.heeds_file }}
          cd ..\..
      
      - name: Commit results to Git
        run: |
          git add heeds_results\
          git commit -m "HEEDS study: `${{ github.event.inputs.heeds_file }} - `$(Get-Date -Format 'yyyy-MM-dd HH:mm')"
          git push
"@
Set-Content -Path ".github\workflows\heeds_study_workflow3.yml" -Value $workflow3
Write-Host "  Created: .github\workflows\heeds_study_workflow3.yml" -ForegroundColor Green

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Review the organized files" -ForegroundColor White
Write-Host "  2. git add ." -ForegroundColor White
Write-Host "  3. git commit -m 'Setup automated workflows'" -ForegroundColor White
Write-Host "  4. git push" -ForegroundColor White
Write-Host ""