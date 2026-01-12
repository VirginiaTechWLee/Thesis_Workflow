# HEEDS API Lessons Learned

Documentation of findings, errors, and solutions when integrating HEEDS MDO with automated GitHub Actions workflows.

**Author:** Wayne Lee (Virginia Tech)  
**Date:** January 8, 2026  
**Context:** Thesis workflow automation for ML-based bolt looseness detection

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [What Works](#what-works)
3. [What Doesn't Work](#what-doesnt-work)
4. [Errors Encountered](#errors-encountered)
5. [Solutions Applied](#solutions-applied)
6. [HEEDS API Usage](#heeds-api-usage)
7. [Recommendations](#recommendations)

---

## Executive Summary

The HEEDS Python API (`import HEEDS`) is **only available when scripts are executed through the HEEDS application itself**, not when running Python directly. This has significant implications for CI/CD automation.

**Key Finding:** You cannot simply call `python my_script.py` and expect `import HEEDS` to work, even when using HEEDS's bundled Python interpreter.

---

## What Works

### 1. Running Scripts Through HEEDSMDO.exe

The HEEDS module loads successfully when using:

```powershell
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" -b -script "my_script.py"
```

**Evidence from log:**
```
Running script test_heeds_api.py...
HEEDS module loaded successfully!
```

### 2. Command Line Options for HEEDSMDO.exe

| Flag | Description |
|------|-------------|
| `-b` | Run in batch mode (execute and quit) |
| `-script path` | Execute the script file at path |
| `-cwd dir` | Set working directory |
| `-verbose` | Enable verbose logging |
| `-open path` | Open a .heeds project file |
| `-save path` | Save project to path |

### 3. Passing Arguments via HEEDS.app().data()

HEEDS uses its own argument system, not standard `argparse`:

```python
# This works inside HEEDS-executed scripts:
study_name = HEEDS.app().data("-study")
```

**NOT** this (standard Python):
```python
# This does NOT work for HEEDS-specific args:
parser = argparse.ArgumentParser()
args = parser.parse_args()
```

### 4. License Checkout

The VT license server works (with warnings):
```
RCT license for Modeler has been checked out. Server: siemensaoe.software.vt.edu Expires: 02-feb-2026
```

Note: `heeds_runtime` feature shows errors but execution continues with RCT license.

### 5. Config-Only Mode

When HEEDS API isn't available, generating JSON config works:

```python
if not HEEDS_AVAILABLE:
    generate_study_config(args.study, args.cases, args.output)  # Creates JSON
```

---

## What Doesn't Work

### 1. Direct Python Execution

```powershell
# FAILS - No HEEDS module available
& "C:\HEEDS\MDO\Ver2410\Python3\python.exe" my_script.py

# FAILS - No HEEDS module available  
& "C:\ProgramData\anaconda3\python.exe" my_script.py
```

**Error:**
```
ModuleNotFoundError: No module named 'HEEDS'
```

### 2. Standard Argument Passing

Command line arguments after `-script` are NOT passed to the Python script in the normal way:

```powershell
# Arguments after script path may not be accessible via argparse
& "HEEDSMDO.exe" -b -script "my_script.py" --study sweep --cases 72
```

### 3. Consistent Logging

Log file location is inconsistent:
- Sometimes creates `HEEDSMDO.log` in current directory
- Sometimes creates it in user home directory
- Sometimes creates empty (0 byte) log files
- `-verbose` flag doesn't always produce output

### 4. Unicode Characters in PowerShell

PowerShell on Windows Server doesn't handle Unicode emojis in YAML:

```yaml
# FAILS - causes parser error
Write-Host "Tests PASSED ✓"

# WORKS
Write-Host "Tests PASSED [PASS]"
```

**Error:**
```
The string is missing the terminator: ".
```

### 5. Bash-Style Operators in PowerShell

```powershell
# FAILS
git pull || Write-Host "No changes"

# WORKS
try { git pull } catch { Write-Host "No changes" }
```

---

## Errors Encountered

### Database Schema Mismatches

| Error | Cause | Fix |
|-------|-------|-----|
| `NOT NULL constraint failed: studies.study_type` | Missing `--study_type` argument | Added argument to script and workflow |
| `table cases has no column named case_name` | Schema used `case_label`, Python used `case_name` | Updated schema to match Python |
| `table psd_data has no column named data_type` | Schema used `response_type`, Python used `data_type` | Renamed column in schema |
| `table peaks has no column named area` | Different table structure | Rewrote peaks table definition |
| `table parameters has no column named element_id` | Schema used `bolt_id` | Renamed to `element_id` |

### Python/Test Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `FileNotFoundError: '/dev/null'` | Linux path on Windows | Changed to `'NUL'` |
| `HEEDS module not available` | Running Python directly | Need to run through HEEDSMDO.exe |

### Workflow Syntax Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `token '||' is not valid` | Bash syntax in PowerShell | Used try/catch instead |
| `string is missing terminator` | Unicode emoji (✓) | Replaced with ASCII `[PASS]` |

---

## Solutions Applied

### 1. Schema Alignment

Created consistent naming between `schema.sql` and `Pch_TO_Database.py`:

```sql
-- Final aligned schema
CREATE TABLE cases (
    case_name TEXT NOT NULL,      -- not case_label
    is_baseline INTEGER DEFAULT 0,
    pch_file TEXT,
    ...
);

CREATE TABLE psd_data (
    data_type TEXT NOT NULL,      -- not response_type
    ...
);

CREATE TABLE parameters (
    element_id INTEGER NOT NULL,  -- not bolt_id
    K4 REAL NOT NULL,             -- uppercase
    K5 REAL NOT NULL,
    K6 REAL NOT NULL,
    ...
);
```

### 2. Workflow PowerShell Compatibility

```yaml
# Before (fails)
run: git pull || echo "skip"

# After (works)
run: try { git pull origin main --rebase } catch { Write-Host "No changes to pull" }
```

### 3. ASCII-Only Output

```yaml
# Before (fails on Windows Server)
Write-Host "All tests PASSED ✓"

# After (works)
Write-Host "All tests PASSED [PASS]"
```

### 4. Added Missing Arguments

```yaml
# Before (fails - missing study_type)
& python Pch_TO_Database.py --study "name" ...

# After (works)
& python Pch_TO_Database.py --study "name" --study_type "sweep" ...
```

---

## HEEDS API Usage

### Correct Way to Run HEEDS Scripts

```powershell
# Batch mode with script
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" -b -script "my_script.py"

# With working directory
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" -b -cwd "C:\project" -script "script.py"
```

### Getting Arguments Inside HEEDS Scripts

```python
import HEEDS

# Get custom command line argument
study_type = HEEDS.app().data("-study")
num_cases = HEEDS.app().data("-cases")

# Get built-in paths
examples_dir = HEEDS.app().data("EXAMPLES_DIR")
project_folder = HEEDS.projectFolder()
```

### Creating Projects Programmatically

```python
import HEEDS

# Create new project
(project, process, study, analysis) = HEEDS.createProject()
project.save("my_study.heeds")

# Create variables
var = project.createVariable('K_bolt5', 
    type='Continuous',
    min=1e4,
    baseline=1e12,
    max=1e14)

# Create responses
resp = project.createResponse('peak_frequency')

# Configure study
study.setName("sweep_study")
study.set('strAgentType', 'DOE')
study.set('numEvals', 100)

# Run
study.checkAndReport()
study.run()
study.wait()
```

### Sample Scripts Location

```
C:\HEEDS\MDO\Ver2410\docs\API_samples\
├── cbeam.py           # Basic example
├── runstudy.py        # Running studies
├── nastran.py         # Nastran integration
├── surrogate_export.py
└── ...
```

---

## Recommendations

### For Automated Workflows

1. **Use config-only mode for CI/CD**: Generate JSON config with standard Python, then run HEEDS separately if needed.

2. **Pre-create .heeds templates**: Create .heeds files manually in HEEDS GUI, then run them via command line:
   ```powershell
   & "C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe" project.heeds
   ```

3. **Avoid HEEDS Python API in GitHub Actions**: The module dependency on HEEDSMDO.exe makes it difficult for automated pipelines.

### For Database Design

1. **Always align schema with Python code FIRST** before running workflows
2. **Use consistent naming**: Pick `case_name` or `case_label`, not both
3. **Test database inserts locally** before running in CI/CD

### For PowerShell Workflows

1. **No Unicode emojis** - use ASCII alternatives
2. **No `||` or `&&`** - use try/catch or if/else
3. **Test workflow YAML locally** if possible
4. **Use full paths** for .NET methods like `[System.IO.File]::ReadAllText()`

### For Future Development

1. **Consider generating .heeds XML directly**: The .heeds format is XML-based; could generate without HEEDS module
2. **Document HEEDS API quirks**: The `HEEDS.app().data()` argument system is non-standard
3. **Monitor license expiration**: RCT license expires 02-feb-2026

---

## File Locations Reference

| Item | Path |
|------|------|
| HEEDS GUI | `C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe` |
| HEEDS Solver | `C:\HEEDS\MDO\Ver2410\Win64\solver\heeds.exe` |
| HEEDS Python | `C:\HEEDS\MDO\Ver2410\Python3\python.exe` |
| API Docs | `C:\HEEDS\MDO\Ver2410\docs\API\` |
| API Samples | `C:\HEEDS\MDO\Ver2410\docs\API_samples\` |
| Log File | `HEEDSMDO.log` (location varies) |

---

## Version Information

- **HEEDS MDO**: 2410.0 build 241030
- **License Server**: siemensaoe.software.vt.edu
- **MSC Nastran**: 2025.1
- **Python (Anaconda)**: 3.x
- **Windows Server**: 2022 (Build 20348)

---

## Running Studies Programmatically (Added 2026-01-08)

### Verified Working Command
```powershell
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" `
    -b `
    -script "run_study_v2.py" `
    -project "C:\Users\waynelee\Documents\project.heeds"
```

### Key Discoveries

1. **sys.argv works** - Use `sys.argv` to parse `-project` argument, not `HEEDS.app().data()`
2. **HEEDS.openProject()** - Opens .heeds file and returns project object
3. **project.study()** - Gets the study object
4. **study.run() + study.wait()** - Executes the study and waits for completion
5. **576 design folders created** - Confirmed batch mode creates all UserDesignSet evaluations

### Required Input Files (must be in Documents or referenced path)

| File | Purpose |
|------|---------|
| Fixed_base_beam.dat | Main Nastran model |
| FBM_TO_DBALL.bat | Nastran runner (check path!) |
| Bush.blk | CBUSH stiffness template |
| Pch_TO_CSV2.py | Post-processor |
| RandomBeamX.dat | Random vibe load case |
| Recoveries.blk | Output requests |
| acceleration_results_baseline.csv | Baseline data |
| displacement_results_baseline.csv | Baseline data |

### Common Failure: Wrong Nastran Path
```batch
REM WRONG (old path)
"D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe"

REM CORRECT (current system)
"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe"
```

---

## Running Studies Programmatically (Added 2026-01-08)

### Verified Working Command
```powershell
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" `
    -b `
    -script "run_study_v2.py" `
    -project "C:\Users\waynelee\Documents\project.heeds"
```

### Key Discoveries

1. **sys.argv works** - Use `sys.argv` to parse `-project` argument, not `HEEDS.app().data()`
2. **HEEDS.openProject()** - Opens .heeds file and returns project object
3. **project.study()** - Gets the study object
4. **study.run() + study.wait()** - Executes the study and waits for completion
5. **576 design folders created** - Confirmed batch mode creates all UserDesignSet evaluations

### Required Input Files (must be in Documents or referenced path)

| File | Purpose |
|------|---------|
| Fixed_base_beam.dat | Main Nastran model |
| FBM_TO_DBALL.bat | Nastran runner (check path!) |
| Bush.blk | CBUSH stiffness template |
| Pch_TO_CSV2.py | Post-processor |
| RandomBeamX.dat | Random vibe load case |
| Recoveries.blk | Output requests |
| acceleration_results_baseline.csv | Baseline data |
| displacement_results_baseline.csv | Baseline data |

### Common Failure: Wrong Nastran Path
```batch
REM WRONG (old path)
"D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe"

REM CORRECT (current system)
"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe"
```
