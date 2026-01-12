# Baseline Workflow 1 - Documentation

## Overview

**Baseline Workflow 1** establishes the reference configuration for a bolt looseness detection study using MSC Nastran random vibration analysis. This workflow automates the process of running a fixed-base modal analysis followed by a random vibration analysis, extracting Power Spectral Density (PSD) response data, and storing the results as a baseline for comparison with parametric cases.

---

## Purpose

The baseline represents a **fully tight bolted beam structure** with nominal CBUSH element stiffness values. All subsequent parametric studies will compare their dynamic responses against this baseline to identify how bolt looseness (reduced stiffness) affects the structural response.

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BASELINE WORKFLOW 1                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   Checkout   │───▶│  Validate    │───▶│   Clean      │               │
│  │     Code     │    │  D:\scratch  │    │   Outputs    │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                 │                        │
│                                                 ▼                        │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │  Copy Input  │◀───│Clear Baseline│◀───│Generate Bush │               │
│  │    Files     │    │    Folder    │    │    .blk      │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │              NASTRAN STEP 1                          │               │
│  │         Fixed_base_beam.dat (SOL SEMODES)            │               │
│  │    Creates: .MASTER, .DBALL (modal database)         │               │
│  └──────────────────────────────────────────────────────┘               │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────┐               │
│  │              NASTRAN STEP 2                          │               │
│  │         RandomBeamX.dat (SOL 111 RESTART)            │               │
│  │    Creates: .pch (PSD results), .f06, .op2           │               │
│  └──────────────────────────────────────────────────────┘               │
│         │                                                                │
│         ▼                                                                │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   Validate   │───▶│ Move Outputs │───▶│  PCH to CSV  │               │
│  │   F06 Files  │    │  to baseline │    │  Extraction  │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                 │                        │
│                                                 ▼                        │
│                      ┌──────────────────────────────────┐               │
│                      │     Commit Results to Git        │               │
│                      │   baseline/ folder + Bush.blk    │               │
│                      └──────────────────────────────────┘               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Directory Structure

```
Thesis_Workflow/
├── .github/
│   └── workflows/
│       ├── baseline_workflow1.yml      # This workflow
│       ├── fem_analysis_workflow2.yml  # Parametric case runner
│       └── heeds_study_workflow3.yml   # HEEDS optimization
├── Scripts/
│   ├── generate_baseline_bush.py       # Generates Bush.blk with nominal stiffness
│   ├── Pch_TO_CSV_git.py              # Converts PCH to CSV (flexible paths)
│   └── Pch_TO_CSV2.py                 # Original PCH converter (legacy)
├── templates/
│   ├── Fixed_base_beam.dat            # Modal analysis input deck
│   ├── RandomBeamX.dat                # Random vibration input deck
│   └── Recoveries.blk                 # Output request definitions
├── baseline/
│   ├── Bush.blk                       # CBUSH stiffness definitions
│   ├── randombeamx.pch                # PSD punch file results
│   ├── randombeamx.f06                # Nastran output file
│   ├── fixed_base_beam.MASTER         # Modal database
│   └── acceleration_results.csv       # Extracted PSD features
├── heeds_projects/
│   └── *.heeds                        # HEEDS optimization project files
└── Bush.blk                           # Working copy of CBUSH definitions
```

---

## Key Files Explained

### Input Files

| File | Description |
|------|-------------|
| `Fixed_base_beam.dat` | SOL SEMODES deck - computes natural frequencies and mode shapes. Creates MASTER/DBALL database for restart. |
| `RandomBeamX.dat` | SOL 111 deck - random vibration analysis using modal superposition. Restarts from Fixed_base_beam database. |
| `Bush.blk` | INCLUDE file containing CBUSH/PBUSH definitions for 10 bolt elements with K4, K5, K6 stiffness values. |
| `Recoveries.blk` | XY plot output requests for acceleration and displacement PSD at monitored nodes. |

### Output Files

| File | Description |
|------|-------------|
| `randombeamx.pch` | Punch file containing PSD response data at all requested nodes/DOFs |
| `acceleration_results.csv` | Extracted features: Area under PSD curve, top 3 peak frequencies and amplitudes per DOF |
| `displacement_results.csv` | Same format as acceleration but for displacement PSD |
| `fixed_base_beam.MASTER` | Modal database containing eigenvalues and eigenvectors |

---

## The Beam Model

### Physical Description

The model represents a **cantilever beam with distributed bolted joints**:

- **11 nodes** along the beam length (Nodes 1-10 on one side, 111-1111 on the other)
- **10 CBUSH elements** connecting node pairs, simulating bolted connections
- **10 CBEAM elements** representing the beam structure (aluminum 6061)
- **Fixed boundary condition** at Node 1 (base)

### Node Layout

```
Fixed End                                                    Free End
    │
    ▼
  [1]═══[2]═══[3]═══[4]═══[5]═══[6]═══[7]═══[8]═══[9]═══[10]
   │     │     │     │     │     │     │     │     │      │
   ║     ║     ║     ║     ║     ║     ║     ║     ║      ║   ← CBUSH Elements
   │     │     │     │     │     │     │     │     │      │
[111]══[222]══[333]══[444]══[555]══[666]══[777]══[888]══[999]══[1010]══[1111]
                                                                          │
                                                               Monitored  ▼
                                                               Outputs
```

### CBUSH Stiffness Parameters

Each CBUSH element has 6 stiffness DOFs. For this study, we focus on **rotational stiffness**:

| Parameter | DOF | Description | Baseline Value |
|-----------|-----|-------------|----------------|
| K1 | Translation X | Axial stiffness | Not varied |
| K2 | Translation Y | Lateral stiffness | Not varied |
| K3 | Translation Z | Vertical stiffness | Not varied |
| **K4** | Rotation X | Roll stiffness | **1.0E+8** |
| **K5** | Rotation Y | Pitch stiffness | **1.0E+8** |
| **K6** | Rotation Z | Yaw stiffness | **1.0E+8** |

---

## Nastran Analysis Details

### Step 1: Modal Analysis (SOL SEMODES)

```nastran
$INIT MASTER(S)
NASTRAN SYSTEM(442)=-1,SYSTEM(319)=1
SOL SEMODES
CEND
MEFFMASS(ALL) = YES
  METHOD = 1
  SPC = 1
BEGIN BULK
EIGRL  1              10  0              MASS
...
ENDDATA
```

**Purpose**: Extract the first 10 natural frequencies and mode shapes of the constrained beam structure.

**Key Outputs**:
- `fixed_base_beam.MASTER` - Database containing modal data
- `fixed_base_beam.DBALL` - Associated data blocks

### Step 2: Random Vibration (SOL 111)

```nastran
ASSIGN MASTERCP='fixed_base_beam.master'
RESTART,LOGI=MODES NOKEEP
SOL 111
CEND
  DISPLACEMENT(PHASE,PSDF) = 1
  ACCELERATION(PHASE,PSDF) = 1
  SDAMPING = 2001
  RANDOM = 200
  DLOAD = 1001
BEGIN BULK
RANDPS  200  1  1  1.  0.  201
TABRND1 201  LOG  LOG
        20.  1.0  100.  1.0  1000.  1.0  2000.  1.0
        ENDT
...
ENDDATA
```

**Purpose**: Apply random base excitation and compute PSD response.

**Loading**:
- Flat PSD input from 20-2000 Hz at 1.0 g²/Hz
- Applied as base acceleration in X, Y, Z directions
- 2% critical damping for all modes

---

## CSV Output Format

The `acceleration_results.csv` contains extracted features organized as:

| Measurement | Node_1 | Node_111 | Node_222 | ... | Node_1111 |
|-------------|--------|----------|----------|-----|-----------|
| ACCE_T1_Area | 1234.5 | 2345.6 | 3456.7 | ... | 4567.8 |
| ACCE_T1_Frequency_1 | 45.2 | 46.1 | 47.0 | ... | 48.5 |
| ACCE_T1_PSD_1 | 0.0234 | 0.0345 | 0.0456 | ... | 0.0567 |
| ACCE_T1_Frequency_2 | 123.4 | 124.5 | 125.6 | ... | 126.7 |
| ACCE_T1_PSD_2 | 0.0123 | 0.0234 | 0.0345 | ... | 0.0456 |
| ... | ... | ... | ... | ... | ... |

**Feature Definitions**:
- **Area**: Total energy (integral of PSD over frequency range using trapezoidal rule)
- **Frequency_N**: Frequency of Nth highest peak in PSD
- **PSD_N**: Amplitude of Nth highest peak

---

## Running the Workflow

### Trigger

The workflow is triggered manually via `workflow_dispatch`:

1. Go to **Actions** tab in GitHub
2. Select **Baseline Workflow1**
3. Click **Run workflow**
4. Select branch (main) and click **Run workflow**

### Prerequisites

- Self-hosted runner configured on Windows VM
- MSC Nastran 2025.1 installed at `C:\Program Files\MSC.Software\MSC_Nastran\2025.1\`
- Python (Anaconda) at `C:\ProgramData\anaconda3\python.exe`
- D:\scratch directory exists and is writable

### Expected Runtime

- Modal analysis: ~30 seconds
- Random vibration: ~60 seconds
- Total workflow: ~3-5 minutes

---

## Validation Checks

The workflow includes built-in validation:

1. **Scratch directory check**: Verifies D:\scratch is writable
2. **F06 FATAL check**: Scans output files for FATAL errors
3. **MASTER file check**: Confirms modal database was created
4. **PCH file check**: Confirms PSD results were generated

If any check fails, the workflow stops with a descriptive error message.

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `FATAL MESSAGE 398` | MASTER file not found | Check Fixed_base_beam completed successfully |
| `scratch directory not writable` | Permission issue | Verify D:\scratch exists and has write access |
| `python not recognized` | Path issue | Use full path: `C:\ProgramData\anaconda3\python.exe` |
| `RandomBeamX.dat not found` | Case sensitivity | Ensure filename matches exactly in templates/ |
| No PCH file created | Missing PUNCH keyword | Add PUNCH to DISPLACEMENT/ACCELERATION requests |

### Debug Steps

1. Check the workflow run logs in GitHub Actions
2. Look at the "Debug - List files" step output
3. Examine F06 files for Nastran errors:
   ```powershell
   Select-String -Path "*.f06" -Pattern "FATAL","ERROR"
   ```

---

## Best Practices

1. **Always run Baseline Workflow first** before any parametric studies
2. **Don't modify templates/** directly - changes should go through git
3. **Check F06 files** if results seem unexpected
4. **Monitor disk space** - Nastran MASTER/DBALL files can be large
5. **Clean scratch directory** periodically if running many analyses

---

## Next Steps

After establishing the baseline:

1. **Workflow 2 (FEM Analysis)**: Run individual parametric cases with varied CBUSH stiffness
2. **Workflow 3 (HEEDS Study)**: Run full optimization study across 73 parametric cases
3. **Delta Analysis**: Compare parametric results against baseline to quantify looseness effects

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-02 | Initial baseline workflow complete | Wayne Lee |
| 2026-01-02 | Added D:\scratch, FATAL validation, scr=no | Wayne Lee |
| 2026-01-02 | Fixed Recoveries.blk copy step | Wayne Lee |

---

## Contact

For questions about this workflow:
- **Author**: Wayne Lee (waynelee@vt.edu)
- **Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
