# Workflow 4: Automated HEEDS Pipeline

Fully automated pipeline that generates fresh baseline, runs HEEDS parametric studies, and stores results in SQLite database.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        WORKFLOW 4                                │
├─────────────────────────────────────────────────────────────────┤
│  1. Pre-flight Tests     - Validate bush generator & HEEDS API  │
│  2. Run Fresh Baseline   - Call Workflow 1 (optional)           │
│  3. Generate HEEDS       - Create .heeds file programmatically  │
│  4. Run HEEDS Study      - Execute via heeds.exe                │
│  5. Extract CSV          - Process PCH files                    │
│  6. Insert to Database   - Store baseline + cases in SQLite     │
│  7. Commit Results       - Push to Git (optional)               │
└─────────────────────────────────────────────────────────────────┘
```

## Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `study_type` | choice | - | `sweep`, `doe`, or `monte_carlo` |
| `num_cases` | string | `72` | Number of cases (72 for sweep, 100-5000 for others) |
| `study_name` | string | `bolt_study` | Name for the study (used in filenames) |
| `skip_tests` | boolean | `false` | Skip pre-flight tests (not recommended) |
| `run_fresh_baseline` | boolean | `true` | **Run Workflow 1 first** to generate fresh baseline |
| `insert_to_database` | boolean | `true` | Insert results into SQLite database |
| `reset_database` | boolean | `false` | **DELETE** existing database and start fresh |
| `commit_results` | boolean | `true` | Commit result files to Git |

## Pipeline Stages

### Stage 1: Pre-flight Tests
Runs validation tests before starting:
- `tests/test_bush_generator.py` - Validates Bush.blk generation
- `heeds/tests/test_heeds_study.py` - Validates HEEDS project generation

Skip with `skip_tests: true` (not recommended).

### Stage 2: Run Fresh Baseline (Calls Workflow 1)
When `run_fresh_baseline: true`:
- Calls `baseline_workflow1.yml` as a reusable workflow
- Generates fresh `baseline/Bush.blk` with nominal stiffness values
- Runs Nastran SOL 103 + SOL 111
- Produces fresh `baseline/randombeamx.pch`
- **Baseline is inserted as Case 0** in the database

When `run_fresh_baseline: false`:
- Uses existing baseline files from repo
- Faster, but assumes baseline is already current

### Stage 3: HEEDS Study
- Generates `.heeds` project file programmatically
- Runs HEEDS solver with Nastran
- Extracts PCH results to CSV
- Inserts cases 1-N into database

## Study Types

### Sweep (72 cases)
- Single bolt loosened at a time
- 9 bolts × 8 stiffness levels = 72 cases
- Best for: Initial exploration, baseline comparisons

### DOE (100-500 cases)
- Latin Hypercube sampling
- Multiple bolts varied simultaneously
- Best for: Sensitivity analysis, surrogate modeling

### Monte Carlo (1000-5000 cases)
- Random sampling across parameter space
- Best for: ML training data, comprehensive coverage

## Database Management

### Database Contents
```
Case 0:     Baseline (from Workflow 1)
Cases 1-N:  HEEDS parametric study results
```

### Fresh Start
Set `reset_database: true` to:
1. Delete existing `heeds/database/psd_results.db`
2. Create new database from `schema.sql`
3. Insert baseline as case 0
4. Run HEEDS study and insert cases 1-N

### Append Mode (Default)
Set `reset_database: false` to:
1. Keep existing database
2. Add new study alongside existing studies
3. ⚠️ Will **FAIL** if `study_name` already exists (UNIQUE constraint)

### Check Existing Studies
Before running, the workflow shows existing studies in the database:
```
Existing studies:
  - sweep_test (sweep, 72 cases, completed)
  - doe_200 (doe, 200 cases, completed)
```

### Database Location
- Path: `heeds/database/psd_results.db`
- **NOT committed to Git** (in `.gitignore`)
- Stays local on runner machine
- Can grow to 2GB+ for large Monte Carlo studies

## Git Commit Behavior

### With `commit_results: true` (Default)
Commits to Git:
- `baseline/*` - Fresh baseline files (if `run_fresh_baseline: true`)
- `heeds/results/{study_name}_{timestamp}/` - All result files
- CSV files, logs, summary

Does NOT commit:
- `heeds/database/*.db` - SQLite database (gitignored)

### With `commit_results: false`
- Nothing committed to Git
- Results stay local on runner
- Use for large studies or testing

## Usage Examples

### First Test Run (Recommended)
```yaml
study_type: sweep
num_cases: 72
study_name: test_sweep_v1
skip_tests: false
run_fresh_baseline: true    # Generate fresh baseline first
insert_to_database: true
reset_database: true        # Start with clean database
commit_results: true
```

### Quick Re-run (Use Existing Baseline)
```yaml
study_type: sweep
num_cases: 72
study_name: sweep_v2
run_fresh_baseline: false   # Skip baseline, use existing
reset_database: false       # Keep existing data
commit_results: true
```

### Add DOE Study to Existing Database
```yaml
study_type: doe
num_cases: 200
study_name: doe_sensitivity
run_fresh_baseline: false   # Baseline already in database
reset_database: false       # Keep existing data
commit_results: true
```

### Large Monte Carlo (Don't Commit Files)
```yaml
study_type: monte_carlo
num_cases: 2000
study_name: mc_training_data
run_fresh_baseline: false
reset_database: false
commit_results: false       # Too many files for Git
```

### Full Fresh Start After Model Change
```yaml
study_type: sweep
num_cases: 72
study_name: model_v2_sweep
run_fresh_baseline: true    # New baseline for updated model
reset_database: true        # Wipe old results
commit_results: true
```

## Outputs

### Results Directory
```
heeds/results/{study_name}_{timestamp}/
├── {study_name}.heeds          # Generated HEEDS project
├── study_config.json           # Configuration record
├── Bush.blk                    # Input file
├── Fixed_base_beam.dat
├── RandomBeamX.dat
├── Recoveries.blk
├── Pch_TO_CSV2.py
├── SUMMARY.md                  # Run summary
├── *.pch                       # Nastran output
├── *.csv                       # Processed results
└── *.log                       # HEEDS logs
```

### Database Tables
```
studies     → Study metadata
cases       → Individual case info (case 0 = baseline)
parameters  → Bolt stiffness values
psd_data    → Full PSD curves (266 points × nodes × DOFs)
peaks       → Top 3 peak frequencies
summary     → Aggregated metrics
delta       → Differences from baseline
```

## Troubleshooting

### "Study name already exists"
- Use a different `study_name`, OR
- Set `reset_database: true` to wipe and start fresh

### Pre-flight tests fail
- Check `tests/test_bush_generator.py` passes locally
- Check `heeds/tests/test_heeds_study.py` passes locally
- Set `skip_tests: true` to bypass (not recommended)

### Baseline validation fails
- Set `run_fresh_baseline: true` to generate new baseline
- Or run Workflow 1 manually first

### HEEDS fails to run
- Check HEEDS_PATH variable is correct
- Check HEEDS license is available
- Review log files in results directory

### No PCH files generated
- HEEDS study may have failed
- Check for error files in results directory
- Review HEEDS log output

### Database insert fails
- Check `heeds/database/Pch_TO_Database.py` exists
- Check schema matches expected format
- Try `reset_database: true` to recreate

## Required GitHub Variables

| Variable | Example Value |
|----------|---------------|
| `PYTHON_PATH` | `C:\ProgramData\anaconda3\python.exe` |
| `NASTRAN_PATH` | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe` |
| `SCRATCH_DIR` | `D:\scratch` |
| `HEEDS_PATH` | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` |

## Related Workflows

| Workflow | Purpose | Called By |
|----------|---------|-----------|
| **Workflow 1** | Generate baseline Nastran results | Workflow 4 (optional) |
| Workflow 2 | Run single Nastran case manually | - |
| Workflow 3 | Run existing .heeds project file | - |
| **Workflow 4** | Full automated pipeline (this one) | - |

## Command Line Execution

```powershell
# Full run with fresh baseline
gh workflow run "HEEDS Programmatic Workflow4" `
  -f study_type=sweep `
  -f num_cases=72 `
  -f study_name=my_study `
  -f run_fresh_baseline=true `
  -f reset_database=true `
  -f commit_results=true; Start-Sleep -Seconds 5; gh run watch

# Quick run using existing baseline
gh workflow run "HEEDS Programmatic Workflow4" `
  -f study_type=sweep `
  -f num_cases=72 `
  -f study_name=my_study_v2 `
  -f run_fresh_baseline=false `
  -f reset_database=false; Start-Sleep -Seconds 5; gh run watch
```
