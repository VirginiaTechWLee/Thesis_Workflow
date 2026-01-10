# WORKFLOW 1: NASTRAN BASELINE

## Overview

**Workflow 1** establishes the reference configuration for bolt looseness detection using MSC Nastran random vibration analysis. This workflow automates running a fixed-base modal analysis followed by random vibration analysis, extracting Power Spectral Density (PSD) response data, and storing results as a baseline for comparison.

---

## Purpose

The baseline represents a **fully healthy bolted beam structure** with nominal CBUSH element stiffness values. All subsequent parametric studies compare their dynamic responses against this baseline to identify how bolt looseness (reduced stiffness) affects structural response.

**Key Concept - The Driving CBUSH:**
- Bolt 1 has K4=1e8 (not "loose" - it provides excitation input)
- Bolts 2-10 have K4=K5=K6=1e12 (healthy/tight)

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WORKFLOW 1: BASELINE                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   Checkout   │───▶│   Validate   │───▶│   Generate   │               │
│  │     Code     │    │  Environment │    │   Bush.blk   │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                 │                        │
│                                                 ▼                        │
│  ┌──────────────────────────────────────────────────────┐               │
│  │              NASTRAN STEP 1                          │               │
│  │         Fixed_base_beam.dat (SOL SEMODES)            │               │
│  │    Creates: .MASTER, .DBALL (modal database)         │               │
│  └──────────────────────────────────────────────────────┘               │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────┐               │
│  │              NASTRAN STEP 2                          │               │
│  │         RandomBeamX.dat (SOL 111 RESTART)            │               │
│  │    Creates: .pch (PSD results), .f06, .op2           │               │
│  └──────────────────────────────────────────────────────┘               │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │   Validate   │───▶│  Extract to  │───▶│   Commit     │               │
│  │   F06 Files  │    │     CSV      │    │   to Git     │               │
│  └──────────────┘    └──────────────┘    └──────────────┘               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Inputs

| Input | Description | Default |
|-------|-------------|---------|
| None | Workflow runs with fixed baseline configuration | - |

---

## Outputs

| File | Location | Description |
|------|----------|-------------|
| `Bush.blk` | `baseline/` | CBUSH stiffness definitions |
| `acceleration_results.csv` | `baseline/` | PSD features (area, peaks) |
| `displacement_results.csv` | `baseline/` | Displacement PSD features |
| `randombeamx.pch` | `baseline/` | Raw PSD punch file |
| `fixed_base_beam.MASTER` | `baseline/` | Modal database |
| `*.png` | `baseline/` | PSD plots |

---

## How to Run

1. Go to **Actions** tab in GitHub
2. Select **Baseline Workflow1**
3. Click **Run workflow**
4. Select branch (main) and click **Run workflow**

---

## Prerequisites

- GitHub Variables configured:
  - `PYTHON_PATH`
  - `NASTRAN_PATH`
  - `SCRATCH_DIR`
- Self-hosted runner online
- MSC Nastran license available

---

## Expected Runtime

~3-5 minutes total

---

## Validation Checks

1. ✅ Scratch directory writable
2. ✅ F06 files contain no FATAL errors
3. ✅ MASTER file created
4. ✅ PCH file generated
5. ✅ CSV extraction successful

---

## When to Re-Run

- After changing beam model geometry
- After modifying material properties
- After changing excitation profile
- To reset baseline after experimental validation

---

## Related Workflows

| Workflow | Purpose |
|----------|---------|
| **Workflow 2** | Run single parametric case |
| **Workflow 3** | Run existing HEEDS project |
| **Workflow 4** | Full automated HEEDS + database |

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-02 | Initial workflow | Wayne Lee |
| 2026-01-03 | Added D:\scratch, FATAL validation | Wayne Lee |
| 2026-01-05 | Documentation update | Wayne Lee |

---

## Contact

**Author**: Wayne Lee (waynelee@vt.edu)
**Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
