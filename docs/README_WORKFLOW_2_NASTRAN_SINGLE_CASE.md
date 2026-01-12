# WORKFLOW 2: NASTRAN SINGLE CASE ANALYSIS

## Overview

**Workflow 2** runs a single Nastran analysis with user-specified bolt stiffness configuration. This workflow is the workhorse for:
- Manual testing of specific configurations
- Recovery runs when HEEDS cases fail
- Debugging and validation
- Quick "what-if" analyses

---

## Purpose

While Workflow 4 (HEEDS automation) handles bulk parametric studies, Workflow 2 provides fine-grained control over individual cases. It generates a custom `Bush.blk` file based on inputs, runs the full Nastran analysis chain, and computes delta comparisons against the baseline.

---

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW 2: SINGLE CASE                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUTS:                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  case_label: "test_bolt5_level3"                                │    │
│  │  bolt_numbers: "5" or "2,5,7"                                   │    │
│  │  stiffness_levels: "3" or "3,6,4" or "1e6"                     │    │
│  │  is_baseline: false                                             │    │
│  │  verify_zero_delta: false                                       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  generate_case_bush.py                                           │   │
│  │  Creates Bush.blk with specified bolt configuration              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  NASTRAN: Fixed_base_beam.dat → RandomBeamX.dat                  │   │
│  │  (Same as Workflow 1)                                            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  compute_delta.py                                                │   │
│  │  Compares results against baseline/                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                             │                                            │
│                             ▼                                            │
│  OUTPUTS: current_run/{case_label}/                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Bush.blk, acceleration_results.csv, acceleration_delta.csv     │    │
│  │  displacement_results.csv, displacement_delta.csv, *.png        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Inputs

| Input | Type | Description | Example |
|-------|------|-------------|---------|
| `case_label` | string | Identifier for this run | `test_bolt5_level3`, `HEEDS_047` |
| `bolt_numbers` | string | Comma-separated bolt IDs (2-10) | `5` or `2,5,7` |
| `stiffness_levels` | string | Levels 1-9 or direct values | `3` or `3,6,4` or `1e6` |
| `is_baseline` | boolean | Force baseline configuration | `false` |
| `verify_zero_delta` | boolean | Fail if delta ≠ 0 (for baseline verification) | `false` |

---

## Stiffness Level Encoding

| Level | Stiffness (N·m/rad) | Description |
|-------|---------------------|-------------|
| 1 | 1×10⁴ | Loosest |
| 2 | 1×10⁵ | Very loose |
| 3 | 1×10⁶ | Loose |
| 4 | 1×10⁷ | Medium-loose |
| 5 | 1×10⁸ | Driving CBUSH K4 level |
| 6 | 1×10⁹ | Medium |
| 7 | 1×10¹⁰ | Medium-tight |
| 8 | 1×10¹¹ | Tight |
| 9 | 1×10¹² | Healthy/Baseline |

---

## Usage Examples

### Single Bolt Loosening
```
case_label: bolt5_loose
bolt_numbers: 5
stiffness_levels: 3
```
→ Loosens Bolt 5 to 1e6

### Multiple Bolts, Same Level
```
case_label: bolts_2_5_7_loose
bolt_numbers: 2,5,7
stiffness_levels: 3
```
→ Loosens Bolts 2, 5, 7 all to 1e6

### Multiple Bolts, Different Levels
```
case_label: multi_damage
bolt_numbers: 2,5,7
stiffness_levels: 3,6,4
```
→ Bolt 2 at 1e6, Bolt 5 at 1e9, Bolt 7 at 1e7

### Direct Stiffness Value
```
case_label: custom_stiffness
bolt_numbers: 5
stiffness_levels: 5.5e7
```
→ Bolt 5 at exactly 5.5×10⁷

### Baseline Verification
```
case_label: verify_baseline
is_baseline: true
verify_zero_delta: true
```
→ Should produce zero delta (validates workflow)

---

## Outputs

All outputs saved to `current_run/{case_label}/`:

| File | Description |
|------|-------------|
| `Bush.blk` | Generated stiffness configuration |
| `acceleration_results.csv` | PSD features for this case |
| `acceleration_delta.csv` | Difference from baseline |
| `displacement_results.csv` | Displacement PSD features |
| `displacement_delta.csv` | Displacement difference |
| `*.png` | PSD comparison plots |
| `randombeamx.pch` | Raw punch file |

---

## Delta Analysis

The workflow automatically computes:
```
delta = case_value - baseline_value
```

For each metric (Area, Freq_1, PSD_1, etc.) at each node/DOF.

**Interpretation:**
- Large delta at specific nodes → Damage localization
- Frequency shift → Structural stiffness change
- Amplitude increase → Resonance amplification

---

## How to Run

1. Go to **Actions** → **FEM Analysis Workflow2**
2. Click **Run workflow**
3. Fill in parameters:
   - `case_label`: Unique identifier
   - `bolt_numbers`: Which bolts to modify
   - `stiffness_levels`: How much to loosen
4. Click **Run workflow**

---

## Workflow 2 vs Workflow 4

| Aspect | Workflow 2 | Workflow 4 |
|--------|-----------|------------|
| Cases | ONE at a time | MANY automatically |
| Control | User specifies via inputs | HEEDS controls |
| Use case | Testing, recovery, debugging | Full parametric study |
| Nastran | Workflow calls directly | HEEDS calls internally |

---

## Integration with HEEDS Recovery

When a HEEDS case fails, use Workflow 2 to recover:

1. Note the failed case number from HEEDS log
2. Use `--lookup` to find bolt/level:
   ```bash
   python Scripts/generate_case_bush.py --lookup 47
   # Output: Case 47 = Bolt 7, Level 7
   ```
3. Run Workflow 2 with those parameters
4. Results can be manually added to database

---

## Prerequisites

- Baseline must exist (`baseline/acceleration_results.csv`)
- GitHub Variables configured
- Self-hosted runner online

---

## Expected Runtime

~3-5 minutes per case

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Baseline not found" | Run Workflow 1 first |
| Delta values unexpected | Verify bolt_numbers are 2-10 (not 1) |
| FATAL in F06 | Check Bush.blk format |

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-05 | Initial workflow with flexible inputs | Wayne Lee |
| 2026-01-05 | Added multi-bolt support | Wayne Lee |
| 2026-01-05 | Added delta computation | Wayne Lee |

---

## Contact

**Author**: Wayne Lee (waynelee@vt.edu)
**Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
