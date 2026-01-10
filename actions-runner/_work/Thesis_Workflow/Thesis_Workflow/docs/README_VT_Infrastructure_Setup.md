# VT Infrastructure, Tools, and Git Setup Guide

## Overview

This document explains the infrastructure required to run automated Nastran workflows at Virginia Tech, including the server environment, software tools, GitHub integration, and permissions configuration.

---

## Table of Contents

1. [Software Stack](#software-stack)
2. [Server Environment](#server-environment)
3. [GitHub Self-Hosted Runner](#github-self-hosted-runner)
4. [Git Configuration](#git-configuration)
5. [GitHub Permissions](#github-permissions)
6. [HEEDS Integration](#heeds-integration)
7. [Troubleshooting](#troubleshooting)

---

## Software Stack

### MSC Nastran vs Siemens Nastran

This project uses **MSC Nastran 2025.1**, which is the version licensed by Virginia Tech. However, the workflows can be adapted for **Siemens Simcenter Nastran** (formerly NX Nastran) with minor modifications.

| Feature | MSC Nastran | Siemens Nastran |
|---------|-------------|-----------------|
| Installation Path (VT) | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\` | `D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\` |
| Executable | `nastran.exe` | `nastranw.exe` |
| Scratch Parameter | `scr=no` | `scratch=no` |
| License Server | `27500@msc.software.vt.edu` | Siemens license server |

**Key Differences for Workflow Adaptation:**

```yaml
# MSC Nastran command
& "C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe" input.dat scr=no sdir=D:\scratch

# Siemens Nastran command
& "D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe" input.dat scratch=no
```

### HEEDS MDO

**HEEDS** (Hierarchical Evolutionary Engineering Design System) is used for design optimization and parametric studies.

- **VT Installation**: Siemens HEEDS MDO 2024.1
- **Purpose**: Automates running multiple Nastran cases with varied parameters
- **Integration**: HEEDS reads/writes Nastran input files and post-processes results

### Python Environment

- **Distribution**: Anaconda
- **Path**: `C:\ProgramData\anaconda3\python.exe`
- **Key Packages**: pandas, numpy, matplotlib

### Git

- **Version**: PortableGit 2.52.0
- **Path**: `C:\Users\waynelee\Desktop\PortableGit\bin`
- **Note**: Portable Git was used due to permission restrictions on VT managed systems

---

## Server Environment

### VT Virtual Machine

The workflows run on a VT-managed Windows Server virtual machine:

| Property | Value |
|----------|-------|
| Hostname | gl-mercury.cntrlsrvs.w2k.vt.edu |
| OS | Windows Server 2022 (Build 20348) |
| CPU | Intel Core i9-14900K (32 threads) |
| RAM | 128 GB |
| Architecture | 64-bit |

### Directory Structure

```
C:\Users\waynelee\
├── Desktop\
│   ├── actions-runner\              # GitHub Actions runner
│   │   └── _work\
│   │       └── Thesis_Workflow\
│   │           └── Thesis_Workflow\  # Repository working directory
│   └── PortableGit\                  # Git installation
├── Documents\                        # Local working files (not synced)
└── Downloads\                        # Temporary files

D:\
└── scratch\                          # Nastran scratch directory
```

### Scratch Directory

Nastran requires a scratch directory for temporary files during analysis. Due to permission issues with `C:\scratch`, we use `D:\scratch`:

```powershell
# Create scratch directory (if needed)
mkdir D:\scratch

# Verify write permissions
"test" | Out-File D:\scratch\test.txt
Remove-Item D:\scratch\test.txt
```

The workflow validates this directory is writable before running Nastran.

---

## GitHub Self-Hosted Runner

### What is a Runner?

A **GitHub Actions runner** is an application that executes workflow jobs. There are two types:

1. **GitHub-hosted runners**: Managed by GitHub, run in the cloud
2. **Self-hosted runners**: Run on your own infrastructure

We use a **self-hosted runner** because:
- VT firewall restricts cloud access to internal resources
- Nastran and HEEDS are installed locally on the VM
- Large file transfers (MASTER/DBALL files) are faster locally

### How the Runner Works

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│                 │         │                 │         │                 │
│  GitHub.com     │◀───────▶│  VT Firewall    │◀───────▶│  gl-mercury VM  │
│  (Repository)   │  HTTPS  │                 │         │  (Runner)       │
│                 │         │                 │         │                 │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                                               │
                                                               ▼
                                                        ┌─────────────────┐
                                                        │  MSC Nastran    │
                                                        │  HEEDS          │
                                                        │  Python         │
                                                        └─────────────────┘
```

1. User triggers workflow on GitHub
2. Runner (on VM) polls GitHub for jobs
3. Runner downloads code and executes workflow steps
4. Runner uploads results back to GitHub

### Setting Up a Self-Hosted Runner

#### Step 1: Download the Runner

Go to your repository on GitHub:
```
Settings → Actions → Runners → New self-hosted runner
```

Select **Windows** and follow the download instructions.

#### Step 2: Configure the Runner

```powershell
# Navigate to runner directory
cd C:\Users\waynelee\Desktop\actions-runner

# Configure the runner (one-time setup)
.\config.cmd --url https://github.com/VirginiaTechWLee/Thesis_Workflow --token <YOUR_TOKEN>
```

You'll be prompted for:
- Runner group (press Enter for default)
- Runner name (e.g., `gl-mercury`)
- Work folder (press Enter for default `_work`)
- Labels (e.g., `self-hosted,Windows,X64`)

#### Step 3: Run the Runner

**Interactive mode** (for testing):
```powershell
.\run.cmd
```

**As a Windows service** (recommended for production):
```powershell
.\svc.cmd install
.\svc.cmd start
```

#### Step 4: Verify Runner Status

Check runner status on GitHub:
```
Settings → Actions → Runners
```

The runner should show as **Idle** (green dot) when ready.

### Runner Directory Structure

```
actions-runner\
├── _work\
│   ├── Thesis_Workflow\
│   │   └── Thesis_Workflow\    # Cloned repository
│   └── _temp\                   # Temporary workflow files
├── _diag\                       # Diagnostic logs
├── config.cmd                   # Configuration script
├── run.cmd                      # Run script (interactive)
└── svc.cmd                      # Service management script
```

---

## Git Configuration

### Why PortableGit?

VT-managed systems have restrictions on software installation. **PortableGit** allows Git usage without admin privileges:

1. Download from: https://git-scm.com/download/win (Portable/"thumbdrive" edition)
2. Extract to: `C:\Users\waynelee\Desktop\PortableGit`
3. Add to PATH or use full path in commands

### Git Configuration Commands

```powershell
# Set user identity
git config --global user.name "Wayne Lee"
git config --global user.email "waynelee@vt.edu"

# Store credentials (so you don't re-enter password)
git config --global credential.helper store

# Add safe directory (required for runner)
git config --global --add safe.directory C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow
```

### Authentication

GitHub no longer accepts password authentication. Use a **Personal Access Token (PAT)**:

1. Go to GitHub → Settings → Developer Settings → Personal Access Tokens
2. Generate new token (classic)
3. Select scopes: `repo`, `workflow`
4. Copy token and use as password when prompted

---

## GitHub Variables (Required Setup)

### Overview

This repository uses **GitHub Actions Variables** to store environment-specific paths. This allows different users to use the same workflow without modifying the YAML files.

> ⚠️ **IMPORTANT**: Before running any workflows, you MUST configure these variables for your environment.

### Setting Up Variables

1. Go to your repository on GitHub
2. Navigate to: `Settings → Secrets and variables → Actions → Variables`
3. Click **"New repository variable"** for each variable below

**Direct link:**
```
https://github.com/YOUR_USERNAME/YOUR_REPO/settings/variables/actions
```

### Required Variables

| Variable Name | Description | Example Value |
|--------------|-------------|---------------|
| `PYTHON_PATH` | Full path to Python executable | `C:\ProgramData\anaconda3\python.exe` |
| `NASTRAN_PATH` | Full path to Nastran executable | `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe` |
| `SCRATCH_DIR` | Writable directory for Nastran temp files | `D:\scratch` |
| `HEEDS_PATH` | Full path to HEEDS solver executable | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` |

### Finding Your Paths

**Python:**
```powershell
# If Python is in PATH
(Get-Command python).Source

# Common locations
C:\ProgramData\anaconda3\python.exe
C:\Users\<username>\anaconda3\python.exe
C:\Python311\python.exe
```

**MSC Nastran:**
```powershell
# Search for Nastran
Get-ChildItem -Path "C:\Program Files\MSC.Software" -Recurse -Name "nastran.exe" -ErrorAction SilentlyContinue

# Common locations
C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe
C:\Program Files\MSC.Software\MSC_Nastran\2024.1\bin\nastran.exe
```

**Siemens Nastran (alternative):**
```powershell
# Search for Siemens Nastran
Get-ChildItem -Path "C:\Program Files\Siemens","D:\Program Files\Siemens" -Recurse -Name "nastranw.exe" -ErrorAction SilentlyContinue

# Common locations
D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe
```

**HEEDS:**
```powershell
# Search for HEEDS
Get-ChildItem -Path "C:\HEEDS" -Recurse -Name "heeds.exe" -ErrorAction SilentlyContinue

# Command-line solver (use this one for workflows)
C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe

# GUI application (not for automated workflows)
C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe
```

**Scratch Directory:**
```powershell
# Check if D:\scratch exists and is writable
if (-not (Test-Path D:\scratch)) { mkdir D:\scratch }
"test" | Out-File D:\scratch\test.txt
Remove-Item D:\scratch\test.txt
Write-Host "D:\scratch is writable"

# Alternative locations if D: doesn't exist
C:\scratch
C:\temp\nastran_scratch
$env:TEMP\nastran_scratch
```

### How Variables Are Used in Workflows

The workflow YAML files reference these variables using the `${{ vars.VARIABLE_NAME }}` syntax:

```yaml
# Example usage in workflow
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

### Verifying Your Setup

After adding variables, verify them:

1. Go to `Settings → Secrets and variables → Actions → Variables`
2. Confirm all 4 variables are listed with correct values
3. Run a test workflow to confirm paths work

### Updating Variables

If you upgrade software (e.g., Nastran 2025.1 → 2026.1):

1. Go to `Settings → Secrets and variables → Actions → Variables`
2. Click on the variable name
3. Update the value
4. Click **"Update variable"**

No workflow file changes needed!

---

## GitHub Permissions

### Repository Permissions

For the workflow to commit and push results, you must enable write permissions:

1. Go to repository on GitHub
2. Navigate to: `Settings → Actions → General`
3. Scroll to **Workflow permissions**
4. Select: **Read and write permissions**
5. Click **Save**

```
┌─────────────────────────────────────────────────────────────────────┐
│ Workflow permissions                                                 │
├─────────────────────────────────────────────────────────────────────┤
│ Choose the default permissions granted to the GITHUB_TOKEN          │
│                                                                      │
│ ◉ Read and write permissions                                        │
│   Workflows have read and write permissions in the repository       │
│   for all scopes.                                                   │
│                                                                      │
│ ○ Read repository contents and packages permissions                 │
│   Workflows have read permissions in the repository for the         │
│   contents and packages scopes only.                                │
│                                                                      │
│ ☐ Allow GitHub Actions to create and approve pull requests          │
│   (Not required for this project)                                   │
└─────────────────────────────────────────────────────────────────────┘
```

### Workflow YAML Configuration

The checkout action must be configured to persist credentials:

```yaml
- name: Checkout code
  uses: actions/checkout@v4
  with:
    clean: true
    persist-credentials: true
```

### Branch Protection (Optional)

If you have branch protection rules, you may need to:
- Allow the runner to bypass protection
- Or use a bot account with appropriate permissions

---

## HEEDS Integration

### How HEEDS Works with Nastran

HEEDS automates parametric studies by:

1. **Reading** a template Nastran input file with tagged variables
2. **Modifying** variable values according to the design of experiments
3. **Executing** Nastran for each design point
4. **Extracting** response values from output files
5. **Optimizing** based on objectives and constraints

### HEEDS Project Structure

```
heeds_projects/
└── Square_Beam_scenario.heeds     # HEEDS project file (XML)
    ├── Variables                   # K4, K5, K6 stiffness values
    ├── Responses                   # Modal frequencies, PSD values
    ├── Objectives                  # Minimize/maximize targets
    └── Workflow                    # Nastran execution sequence
```

### Variable Tagging in Nastran Files

HEEDS uses tags in input files to identify variable locations:

```nastran
$ Bush.blk - Tagged for HEEDS
PBUSH   1       K       1.0+6   1.0+6   1.0+6   <K4_1>  <K5_1>  <K6_1>
PBUSH   2       K       1.0+6   1.0+6   1.0+6   <K4_2>  <K5_2>  <K6_2>
...
```

HEEDS replaces `<K4_1>`, `<K5_1>`, etc. with actual values for each design point.

### Response Extraction

HEEDS extracts responses from Nastran output files:

| Response | Source File | Extraction Method |
|----------|-------------|-------------------|
| Modal frequencies | `fixed_base_beam.f06` | Search for "EIGENVALUE" |
| PSD acceleration | `randombeamx.pch` | Parse punch file data |
| Peak frequencies | `acceleration_results.csv` | Read CSV columns |

### Running HEEDS from Workflow

```yaml
- name: Run HEEDS study
  run: |
    cd ${{ steps.setup.outputs.results_dir }}
    heeds ${{ github.event.inputs.heeds_file }}
```

---

## Troubleshooting

### Runner Issues

| Problem | Solution |
|---------|----------|
| Runner shows offline | Check if `run.cmd` is running or restart the service |
| "Permission denied" on checkout | Verify PAT has `repo` scope |
| Runner can't find Git | Add PortableGit to system PATH |

### Nastran Issues

| Problem | Solution |
|---------|----------|
| "scratch directory not writable" | Use `D:\scratch` instead of `C:\scratch` |
| MASTER file not created | Ensure `scr=no` is in the command |
| License checkout failed | Check VT license server status |

### Git Push Issues

| Problem | Solution |
|---------|----------|
| "Permission denied to github-actions[bot]" | Enable "Read and write permissions" in repository settings |
| "non-fast-forward" | Run `git pull --rebase` before pushing |
| Credential prompt every time | Run `git config --global credential.helper store` |

### HEEDS Issues

| Problem | Solution |
|---------|----------|
| HEEDS can't find Nastran | Verify Nastran path in HEEDS preferences |
| Variables not substituted | Check tag format matches HEEDS expectations |
| Results not extracted | Verify search patterns in response definitions |

---

## Quick Reference

### Key Paths (VT gl-mercury)

```
MSC Nastran:     C:\Program Files\MSC.Software\MSC_Nastran\2025.1\bin\nastran.exe
Python:          C:\ProgramData\anaconda3\python.exe
Git:             C:\Users\waynelee\Desktop\PortableGit\bin\git.exe
Runner:          C:\Users\waynelee\Desktop\actions-runner\
Repository:      C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow\
Scratch:         D:\scratch\
```

### Key URLs

```
Repository:      https://github.com/VirginiaTechWLee/Thesis_Workflow
Actions:         https://github.com/VirginiaTechWLee/Thesis_Workflow/actions
Runner Settings: https://github.com/VirginiaTechWLee/Thesis_Workflow/settings/actions/runners
Permissions:     https://github.com/VirginiaTechWLee/Thesis_Workflow/settings/actions
```

### Common Commands

```powershell
# Check runner status
cd C:\Users\waynelee\Desktop\actions-runner
.\run.cmd

# Pull latest code
cd C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow
git pull

# Check for Nastran errors
Select-String -Path "*.f06" -Pattern "FATAL","ERROR"

# Clean scratch directory
Remove-Item D:\scratch\* -Force
```

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-02 | Initial documentation | Wayne Lee |

---

## Contact

- **Author**: Wayne Lee (waynelee@vt.edu)
- **VT IT Support**: For VM or network issues
- **MSC Support**: For Nastran licensing issues
