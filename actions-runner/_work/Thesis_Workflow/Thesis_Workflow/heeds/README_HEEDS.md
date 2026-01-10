# HEEDS Integration for Bolt Looseness Detection

Programmatic HEEDS MDO integration for automated parametric studies of CBUSH bolt stiffness effects on structural dynamics.

## Overview

This module provides:
- **Programmatic project generation** - Create HEEDS projects without GUI
- **Study automation** - Run sweep, DOE, and Monte Carlo studies
- **Result extraction** - Pull PSD data into SQLite database
- **Validation & testing** - Verify configurations before running
- **Workflow integration** - Full CI/CD pipeline with GitHub Actions

## Directory Structure

```
heeds/
├── scripts/                    # Executable scripts
│   ├── generate_heeds_study.py # Create HEEDS projects programmatically
│   ├── run_heeds_study.py      # Run study from command line
│   ├── extract_heeds_results.py# Extract results to database
│   └── validate_heeds_project.py
│
├── tests/                      # Test suite
│   ├── test_heeds_study.py
│   ├── test_bush_tagging.py
│   ├── run_heeds_tests.py
│   └── fixtures/
│
├── database/                   # SQLite storage
│   ├── psd_results.db
│   ├── schema.sql
│   ├── Pch_TO_Database.py
│   ├── setup_database.py
│   └── README_Database.md
│
├── projects/                   # HEEDS project files (.heeds)
│   └── *.heeds
│
└── results/                    # Study outputs
    └── {project}_{timestamp}/
```

## Quick Start

### Option 1: Use Workflow 4 (Recommended)

The easiest way to run HEEDS studies is via GitHub Actions Workflow 4:

```powershell
gh workflow run "HEEDS Programmatic Workflow4" `
  -f study_type=sweep `
  -f num_cases=72 `
  -f study_name=my_study `
  -f run_fresh_baseline=true `
  -f reset_database=true
```

This will:
1. Run pre-flight tests
2. Generate fresh baseline (calls Workflow 1)
3. Insert baseline as Case 0 in database
4. Generate HEEDS project programmatically
5. Run all 72 cases
6. Insert results into database
7. Commit to Git

### Option 2: Manual Generation

```bash
# Sweep study (72 cases - 9 bolts × 8 levels)
python heeds/scripts/generate_heeds_study.py --study sweep --output heeds/projects/sweep.heeds

# DOE study (200 cases - Latin Hypercube)
python heeds/scripts/generate_heeds_study.py --study doe --cases 200 --output heeds/projects/doe.heeds

# Monte Carlo (1000 random cases)
python heeds/scripts/generate_heeds_study.py --study monte_carlo --cases 1000 --output heeds/projects/mc.heeds
```

### Option 3: Run Tests Only

```bash
python heeds/tests/run_heeds_tests.py --verbose
```

## Study Types

| Type | Cases | Method | Use Case |
|------|-------|--------|----------|
| `sweep` | 72 | Full Factorial | Single bolt, systematic levels |
| `doe` | 50-500 | Latin Hypercube | Multi-bolt, space-filling |
| `monte_carlo` | 100-5000 | Random Sampling | Large-scale training data |
| `optimization` | Variable | SHERPA | Find worst-case configuration |

## Workflow Integration

### Complete Pipeline (Workflow 4)

```
┌─────────────────────────────────────────────────────────┐
│  Workflow 4: HEEDS Programmatic Pipeline                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐                                    │
│  │ Pre-flight Tests│ ─── Validate scripts & config     │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ Workflow 1      │ ─── Generate fresh baseline        │
│  │ (Reusable)      │     (optional, recommended)        │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ Insert Baseline │ ─── Case 0 in database            │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ generate_heeds_ │ ─── Create .heeds project         │
│  │ study.py        │     programmatically               │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ HEEDS Solver    │ ─── Run parametric study          │
│  │ (heeds.exe)     │     (72-5000 cases)               │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ Pch_TO_CSV2.py  │ ─── Extract PCH to CSV            │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ Pch_TO_Database │ ─── Insert cases 1-N              │
│  └────────┬────────┘                                    │
│           │                                             │
│           ▼                                             │
│  ┌─────────────────┐                                    │
│  │ ML Training     │ ─── Query database for training   │
│  │ Pipeline        │                                    │
│  └─────────────────┘                                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Workflow Dependencies

```
Workflow 1 (Baseline)          Workflow 4 (Full Pipeline)
     │                              │
     │  ◄───── calls ──────────────┤
     │                              │
     ▼                              ▼
baseline/randombeamx.pch    heeds/results/{study}/
baseline/Bush.blk           heeds/database/psd_results.db
```

## HEEDS Python API

### Key Functions

```python
import HEEDS

# Project management
project = HEEDS.currentProject()
(project, process, study, analysis) = HEEDS.createProject()
project.save("path/to/project.heeds")

# Variables
var = project.createVariable('K_bolt5', 
    type='Continuous', 
    min=1e4, 
    baseline=1e12, 
    max=1e14)

# Responses
resp = project.createResponse('PSD_peak_freq')

# File tagging
inputfile.addTag(row, col, variable)
outputfile.addTag(row, col, response)

# Study control
study.setName("my_study")
study.set('strAgentType', 'DOE')
study.set('numEvals', 100)
study.checkAndReport()
study.run()
study.wait()
```

### Running from Command Line

```bash
# HEEDS solver (command line)
"C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe" project.heeds

# HEEDS Python environment
"C:\HEEDS\MDO\Ver2410\Python3\python.exe" script.py
```

## Configuration

### GitHub Variables Required

| Variable | Value |
|----------|-------|
| `HEEDS_PATH` | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` |
| `PYTHON_PATH` | `C:\ProgramData\anaconda3\python.exe` |
| `NASTRAN_PATH` | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe` |
| `SCRATCH_DIR` | `D:\scratch` |

### Stiffness Level Encoding

| Level | Stiffness | Description |
|-------|-----------|-------------|
| 1 | 1e4 | Loosest |
| 2 | 1e5 | |
| 3 | 1e6 | |
| 4 | 1e7 | |
| 5 | 1e8 | Driving CBUSH K4 (Bolt 1 fixed here) |
| 6 | 1e9 | |
| 7 | 1e10 | |
| 8 | 1e11 | |
| 9 | 1e12 | Healthy/Baseline (Bolts 2-10) |

### Bolt Configuration

```
Bolt 1:  "Driving CBUSH" - Always fixed at K4=1e8, K5=K6=1e12
Bolts 2-10: Varied in studies (baseline = 1e12 for all K4/K5/K6)
```

## Database Schema

### Tables

```sql
studies     → Study metadata (name, type, num_cases, status)
cases       → Individual case info (case 0 = baseline)
parameters  → Bolt stiffness values (K4, K5, K6 per element)
psd_data    → Full PSD curves (266 points × nodes × DOFs)
peaks       → Top 3 peak frequencies per node/DOF
summary     → Aggregated metrics
delta       → Differences from baseline (case 0)
```

### Query Examples

```sql
-- Get baseline data
SELECT * FROM cases WHERE is_baseline = 1;

-- Get all cases with loosened bolt 5
SELECT c.case_name, p.K4, p.K5, p.K6
FROM cases c
JOIN parameters p ON c.case_id = p.case_id
WHERE p.element_id = 5 AND p.K4 < 1e12;

-- Compare case to baseline
SELECT node_id, dof, delta_peak_freq_1
FROM delta
WHERE case_id = 47;
```

## Troubleshooting

### HEEDS Module Not Found

```
ImportError: No module named 'HEEDS'
```

**Solution**: Run from HEEDS Python environment:
```bash
"C:\HEEDS\MDO\Ver2410\Python3\python.exe" script.py
```

### Bush.blk Tagging Errors

If variables aren't being written to correct positions, check:
1. Row numbers match bolt IDs (1-10)
2. Column positions for K4/K5/K6 (49, 57, 65 for 8-char fields)
3. File format matches expected Nastran fixed-width

### Study Validation Fails

Run `study.checkAndReport()` to see specific errors:
- Missing file references
- Invalid variable ranges
- Untagged variables

### Baseline Not Found

If Workflow 4 fails with "Baseline PCH not found":
- Set `run_fresh_baseline: true` to generate it
- Or run Workflow 1 manually first

### Database Errors

If database insert fails:
- Check `heeds/database/schema.sql` exists
- Try `reset_database: true` to recreate
- Verify `Pch_TO_Database.py` arguments

## Related Documentation

| Document | Description |
|----------|-------------|
| `docs/README_Workflow4.md` | Full Workflow 4 documentation |
| `docs/README_Baseline_Workflow.md` | Workflow 1 documentation |
| `heeds/database/README_Database.md` | Database schema details |
| `docs/README_HEEDS_API.md` | HEEDS Python API reference |
