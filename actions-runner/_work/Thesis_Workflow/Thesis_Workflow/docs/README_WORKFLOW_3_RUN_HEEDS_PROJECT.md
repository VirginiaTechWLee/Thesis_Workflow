# WORKFLOW 3: RUN HEEDS PROJECT

## Overview

**Workflow 3** runs an existing HEEDS MDO project file (`.heeds`) that was created manually through the HEEDS GUI. This workflow is for legacy/manual projects where you've already configured variables, responses, and study settings in the HEEDS interface.

---

## Purpose

HEEDS (Hierarchical Evolutionary Engineering Design System) automates parametric studies by:
1. Reading template Nastran input files with tagged variables
2. Modifying variable values per the design of experiments
3. Executing Nastran for each design point
4. Extracting response values from output files

Workflow 3 takes an existing `.heeds` project and runs it through the HEEDS solver.

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW 3: RUN HEEDS PROJECT                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT:                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  heeds_file: "Square_Beam_scenario_short_rev.heeds"             │    │
│  │  skip_validation: false                                          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Validate Environment                                            │   │
│  │  - Check HEEDS_PATH, NASTRAN_PATH, PYTHON_PATH                  │   │
│  │  - Verify executables exist                                      │   │
│  │  - Test scratch directory                                        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Pre-flight Validation (optional)                                │   │
│  │  validate_heeds_project.py                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Create Results Directory                                        │   │
│  │  heeds/results/{project}_{timestamp}/                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Copy Required Files                                             │   │
│  │  - .heeds project file                                           │   │
│  │  - Templates (Fixed_base_beam.dat, RandomBeamX.dat, etc.)       │   │
│  │  - Baseline Bush.blk                                             │   │
│  │  - Post-processing scripts                                       │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  RUN HEEDS SOLVER                                                │   │
│  │  heeds.exe {project}.heeds                                       │   │
│  │  (May take hours for large studies)                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  Post-Processing                                                 │   │
│  │  - Check for error logs                                          │   │
│  │  - List output files                                             │   │
│  │  - Commit results to Git                                         │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Inputs

| Input | Type | Description | Default |
|-------|------|-------------|---------|
| `heeds_file` | string | HEEDS project filename (from `heeds/projects/`) | `Square_Beam_scenario_short_rev.heeds` |
| `skip_validation` | boolean | Skip pre-flight validation checks | `false` |

---

## HEEDS Project Requirements

Your `.heeds` project file must be:
1. Located in `heeds/projects/`
2. Configured with correct paths to Nastran
3. Have variables tagged in input files
4. Have responses configured for output extraction

### Variable Tagging Example

In Bush.blk, HEEDS looks for tagged values:
```nastran
PBUSH   2       K       1.+6    1.+6    1.+6    <K4_2>  <K5_2>  <K6_2>
```

HEEDS replaces `<K4_2>` with actual stiffness values during each run.

---

## Outputs

Results saved to `heeds/results/{project}_{timestamp}/`:

| Output | Description |
|--------|-------------|
| `*.heeds` | Copy of project file |
| `design_*/` | Individual case directories |
| `*.log` | HEEDS execution logs |
| `report.txt` | Study summary |
| `results.csv` | Tabulated results |

---

## How to Run

1. Ensure your `.heeds` file is in `heeds/projects/`
2. Go to **Actions** → **HEEDS Study Workflow3**
3. Click **Run workflow**
4. Enter the HEEDS filename
5. Click **Run workflow**

---

## HEEDS vs Workflow 4

| Aspect | Workflow 3 | Workflow 4 |
|--------|-----------|------------|
| Project Creation | Manual (HEEDS GUI) | Automatic (Python SDK) |
| Flexibility | Full HEEDS features | Predefined study types |
| Use Case | Complex custom studies | Standard parametric sweeps |
| Database | Manual extraction | Automatic insertion |

**Use Workflow 3 when:**
- You have an existing HEEDS project
- You need custom optimization objectives
- You want full HEEDS GUI features

**Use Workflow 4 when:**
- You want fully automated pipeline
- You need results in database
- You're running standard sweep/DOE studies

---

## Creating a HEEDS Project (GUI)

1. Open HEEDS MDO GUI:
   ```
   C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe
   ```

2. Create new project → Select analysis type

3. Add Nastran analysis:
   - Set command: path to Nastran batch file
   - Add input files (Bush.blk, etc.)
   - Add output files (randombeamx.pch)

4. Define variables:
   - K4_bolt2, K4_bolt3, ... K4_bolt10
   - Set min/max/baseline values

5. Define responses:
   - Tag output file for PSD extraction

6. Configure study:
   - DOE, Optimization, or Exploration
   - Number of evaluations

7. Save project to `heeds/projects/`

---

## Prerequisites

- GitHub Variables configured:
  - `PYTHON_PATH`
  - `NASTRAN_PATH`
  - `SCRATCH_DIR`
  - `HEEDS_PATH` ← **Required for this workflow**
- Self-hosted runner online
- HEEDS license available
- Nastran license available

### HEEDS Path

```
HEEDS_PATH = C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe
```

Note: Use the **solver** executable, not the GUI (`HEEDSMDO.exe`).

---

## Expected Runtime

Depends on study size:

| Study Type | Cases | Estimated Time |
|------------|-------|----------------|
| Small sweep | 10 | ~30 minutes |
| Full sweep | 72 | ~4-6 hours |
| DOE | 200 | ~12-20 hours |
| Monte Carlo | 1000 | ~3-5 days |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "HEEDS not found" | Add `HEEDS_PATH` to GitHub Variables |
| License error | Check HEEDS license server |
| "File not found" in HEEDS | Verify paths inside .heeds file |
| Cases failing | Check individual design_N/ folders for F06 errors |

### Checking HEEDS Logs

After a run, check:
```
heeds/results/{project}_{timestamp}/
├── heeds.log          # Main log
├── design_1/          # First case
│   ├── fixed_base_beam.f06
│   └── randombeamx.f06
└── design_N/          # Nth case
```

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-05 | Initial workflow | Wayne Lee |
| 2026-01-05 | Updated paths to heeds/ folder | Wayne Lee |

---

## Contact

**Author**: Wayne Lee (waynelee@vt.edu)
**Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
