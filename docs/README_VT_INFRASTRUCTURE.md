# VT INFRASTRUCTURE, TOOLS, AND GIT SETUP GUIDE

## Overview

This document explains the infrastructure required to run automated Nastran workflows at Virginia Tech, including the server environment, software tools, GitHub integration, and permissions configuration.

---

## Table of Contents

1. [Software Stack](#software-stack)
2. [Server Environment](#server-environment)
3. [GitHub Self-Hosted Runner](#github-self-hosted-runner)
4. [Git Configuration](#git-configuration)
5. [GitHub Variables](#github-variables)
6. [GitHub Permissions](#github-permissions)
7. [Repository Structure](#repository-structure)
8. [HEEDS Integration](#heeds-integration)
9. [Troubleshooting](#troubleshooting)

---

## Software Stack

### MSC Nastran

| Property | Value |
|----------|-------|
| Version | MSC Nastran 2025.1 |
| Path | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe` |
| License Server | `27500@msc.software.vt.edu` |

### HEEDS MDO

| Property | Value |
|----------|-------|
| Version | Siemens HEEDS MDO 2024.1 |
| Solver Path | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` |
| GUI Path | `C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe` |
| Python API | `C:\HEEDS\MDO\Ver2410\Python3\python.exe` |

**Note**: Use `solver\heeds.exe` for automated workflows, not the GUI.

### Python Environment

| Property | Value |
|----------|-------|
| Distribution | Anaconda |
| Path | `C:\ProgramData\anaconda3\python.exe` |
| Key Packages | pandas, numpy, matplotlib, sqlite3 |

### Git

| Property | Value |
|----------|-------|
| Version | PortableGit 2.52.0 |
| Path | `C:\Users\waynelee\Desktop\PortableGit\bin` |

---

## Server Environment

### VT Virtual Machine

| Property | Value |
|----------|-------|
| Hostname | gl-mercury.cntrlsrvs.w2k.vt.edu |
| OS | Windows Server 2022 (Build 20348) |
| CPU | Intel Core i9-14900K (32 threads) |
| RAM | 128 GB |
| Scratch | D:\scratch |

---

## GitHub Self-Hosted Runner

### What is a Runner?

A self-hosted runner executes GitHub Actions workflows on your own infrastructure. We use self-hosted because:
- VT firewall restricts cloud access
- Nastran and HEEDS are installed locally
- Large file transfers are faster locally

### Runner Location

```
C:\Users\waynelee\Desktop\actions-runner\
├── _work\
│   └── Thesis_Workflow\
│       └── Thesis_Workflow\    # Repository working directory
├── config.cmd                   # Configuration script
├── run.cmd                      # Run script (interactive)
└── svc.cmd                      # Service management
```

### Starting the Runner

**Interactive mode** (for testing):
```powershell
cd C:\Users\waynelee\Desktop\actions-runner
.\run.cmd
```

**As a Windows service** (recommended):
```powershell
.\svc.cmd start
```

---

## Git Configuration

```powershell
# Set user identity
git config --global user.name "Wayne Lee"
git config --global user.email "waynelee@vt.edu"

# Store credentials
git config --global credential.helper store

# Add safe directory
git config --global --add safe.directory C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow
```

---

## GitHub Variables

### Required Variables

Navigate to: `Settings → Secrets and variables → Actions → Variables`

| Variable | Value | Description |
|----------|-------|-------------|
| `PYTHON_PATH` | `C:\ProgramData\anaconda3\python.exe` | Python executable |
| `NASTRAN_PATH` | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe` | Nastran executable |
| `SCRATCH_DIR` | `D:\scratch` | Nastran temp directory |
| `HEEDS_PATH` | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` | HEEDS solver |

### Usage in Workflows

```yaml
- name: Run Python script
  run: |
    & "${{ vars.PYTHON_PATH }}" Scripts/generate_baseline_bush.py

- name: Run Nastran
  run: |
    & "${{ vars.NASTRAN_PATH }}" Fixed_base_beam.dat scr=no sdir="${{ vars.SCRATCH_DIR }}"

- name: Run HEEDS
  run: |
    & "${{ vars.HEEDS_PATH }}" project.heeds
```

---

## GitHub Permissions

### Repository Permissions

Navigate to: `Settings → Actions → General → Workflow permissions`

Select: **Read and write permissions**

This allows workflows to commit results back to the repository.

---

## Repository Structure

```
Thesis_Workflow/
├── .github/
│   └── workflows/
│       ├── baseline_workflow1.yml           # Workflow 1: Baseline
│       ├── fem_analysis_workflow2.yml       # Workflow 2: Single case
│       ├── heeds_workflow3.yml              # Workflow 3: Run HEEDS project
│       └── heeds_workflow4.yml              # Workflow 4: Full automation
│
├── Scripts/                                  # Nastran/workflow scripts
│   ├── generate_baseline_bush.py
│   ├── generate_case_bush.py
│   ├── Pch_TO_CSV2.py
│   ├── compute_delta.py
│   └── verify_delta_zero.py
│
├── heeds/                                    # HEEDS ecosystem
│   ├── scripts/
│   │   ├── generate_heeds_study.py          # SDK project generator
│   │   └── validate_heeds_project.py
│   ├── tests/
│   │   ├── test_heeds_study.py
│   │   ├── run_heeds_tests.py
│   │   └── fixtures/
│   ├── database/
│   │   ├── psd_results.db                   # SQLite database
│   │   ├── schema.sql
│   │   ├── setup_database.py
│   │   └── Pch_TO_Database.py
│   ├── projects/                            # .heeds project files
│   └── results/                             # Study outputs
│
├── tests/                                    # General tests
│   ├── test_bush_generator.py
│   └── run_all_tests.py
│
├── docs/                                     # Documentation
│   ├── README_WORKFLOW_1_NASTRAN_BASELINE.md
│   ├── README_WORKFLOW_2_NASTRAN_SINGLE_CASE.md
│   ├── README_WORKFLOW_3_RUN_HEEDS_PROJECT.md
│   ├── README_WORKFLOW_4_AUTOMATED_HEEDS_PIPELINE.md
│   ├── README_VT_INFRASTRUCTURE.md
│   └── README_MECHANICAL_ANALYSIS.md
│
├── templates/                                # Nastran input templates
│   ├── Fixed_base_beam.dat
│   ├── RandomBeamX.dat
│   └── Recoveries.blk
│
├── baseline/                                 # Baseline results
│   ├── Bush.blk
│   ├── acceleration_results.csv
│   └── randombeamx.pch
│
├── current_run/                              # Workflow 2 outputs
│   └── {case_label}/
│
├── Bush.blk                                  # Working copy
└── README.md
```

---

## HEEDS Integration

### HEEDS Python API

HEEDS provides a full Python SDK for programmatic control:

```python
import HEEDS

# Create project
(project, process, study, analysis) = HEEDS.createProject()
project.save("my_study.heeds")

# Define variables
var = project.createVariable('K_bolt5', min=1e4, baseline=1e12, max=1e14)

# Define responses
resp = project.createResponse('peak_frequency')

# Configure study
study.set('strAgentType', 'DOE')
study.set('numEvals', 100)

# Run
study.run()
study.wait()
```

### API Documentation

```
C:\HEEDS\MDO\Ver2410\docs\API\           # HTML documentation
C:\HEEDS\MDO\Ver2410\docs\API_samples\   # Example scripts
```

---

## Troubleshooting

### Runner Issues

| Problem | Solution |
|---------|----------|
| Runner offline | Check if `run.cmd` is running |
| Permission denied | Verify PAT has `repo` scope |
| Git not found | Add PortableGit to PATH |

### Nastran Issues

| Problem | Solution |
|---------|----------|
| Scratch not writable | Use `D:\scratch` |
| License failed | Check license server status |
| FATAL MESSAGE 398 | Ensure MASTER file exists |

### HEEDS Issues

| Problem | Solution |
|---------|----------|
| HEEDS not found | Add `HEEDS_PATH` variable |
| License error | Check HEEDS license server |
| Cases failing | Check design_N/ folders for F06 errors |

---

## Quick Reference

### Key Paths

```
MSC Nastran:     C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe
HEEDS Solver:    C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe
Python:          C:\ProgramData\anaconda3\python.exe
Git:             C:\Users\waynelee\Desktop\PortableGit\bin\git.exe
Repository:      C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow\
Scratch:         D:\scratch\
```

### Key URLs

```
Repository:      https://github.com/VirginiaTechWLee/Thesis_Workflow
Actions:         https://github.com/VirginiaTechWLee/Thesis_Workflow/actions
Variables:       https://github.com/VirginiaTechWLee/Thesis_Workflow/settings/variables/actions
```

### Common Commands

```powershell
# Check runner status
cd C:\Users\waynelee\Desktop\actions-runner
.\run.cmd

# Pull latest code
cd C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow
git pull

# Run tests
& "C:\ProgramData\anaconda3\python.exe" tests\run_all_tests.py

# Initialize database
& "C:\ProgramData\anaconda3\python.exe" heeds\database\setup_database.py
```

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-02 | Initial documentation | Wayne Lee |
| 2026-01-05 | Added HEEDS integration, new folder structure | Wayne Lee |

---

## Contact

**Author**: Wayne Lee (waynelee@vt.edu)
**Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
