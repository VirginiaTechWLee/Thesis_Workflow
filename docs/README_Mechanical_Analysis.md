# Baseline Beam Mechanical Analysis

## Overview

This document provides the mechanical and dynamic analysis of the baseline beam configuration used in the bolt looseness detection study. It validates the physics of the finite element model, explains the structural behavior, and establishes predictions for how the beam will respond under varied bolt stiffness conditions.

---

## Table of Contents

1. [Physical Model Description](#physical-model-description)
2. [Material Properties](#material-properties)
3. [CBUSH Element Configuration](#cbush-element-configuration)
4. [Baseline Stiffness Encoding](#baseline-stiffness-encoding)
5. [Dynamic Analysis Results](#dynamic-analysis-results)
6. [PSD Response Interpretation](#psd-response-interpretation)
7. [Physics Validation](#physics-validation)
8. [Predictions for Parametric Cases](#predictions-for-parametric-cases)
9. [Machine Learning Data Rationale](#machine-learning-data-rationale)
10. [Future Work: Experimental Validation](#future-work-experimental-validation)

---

## Physical Model Description

### Beam Geometry

The finite element model represents a cantilever beam with distributed bolted joints:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CANTILEVER BEAM MODEL                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  FIXED                                                               FREE    │
│   END                                                                END     │
│    │                                                                  │      │
│    ▼                                                                  ▼      │
│   [1]═══[2]═══[3]═══[4]═══[5]═══[6]═══[7]═══[8]═══[9]═══[10]        │      │
│    │     │     │     │     │     │     │     │     │      │          │      │
│    ║     ║     ║     ║     ║     ║     ║     ║     ║      ║   CBUSH  │      │
│    │     │     │     │     │     │     │     │     │      │  Elements│      │
│  [111]═[222]═[333]═[444]═[555]═[666]═[777]═[888]═[999]═[1010]═[1111] │      │
│                                                              ▲       │      │
│                                                              │       │      │
│                                                         Response     │      │
│                                                         Monitored    │      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Geometric Parameters:**

| Parameter | Value | Units |
|-----------|-------|-------|
| Total Length | 1100 | mm |
| Number of Elements | 10 | - |
| Element Length | 100 | mm |
| Cross-Section | Square | - |
| Width × Height | 16.09 × 16.09 | mm |

### Dual-Node Architecture

The model uses a dual-node architecture that separates beam elements from bolt connections:

- **Upper Row (Nodes 1-10)**: Structural beam nodes connected by CBEAM elements
- **Lower Row (Nodes 111-1111)**: Response monitoring nodes connected via CBUSH elements
- **CBUSH Elements (1-10)**: Represent bolted joints with controllable stiffness

This architecture provides:
1. **Independent Parameter Control**: Each bolt can be varied without affecting adjacent connections
2. **Numerical Stability**: Separation prevents ill-conditioning
3. **Physical Realism**: Accurately represents bolted beam joints
4. **Clear Response Monitoring**: Lower row nodes provide clean acceleration/displacement output

---

## Material Properties

### Aluminum 6061-T6

The beam material is aerospace-grade aluminum, commonly used in spacecraft structures:

| Property | Value | Units |
|----------|-------|-------|
| Elastic Modulus (E) | 68.98 | GPa |
| Poisson's Ratio (ν) | 0.33 | - |
| Density (ρ) | 2711 | kg/m³ |
| Structural Damping | 0.02 | (2% critical) |

### Why Aluminum 6061-T6?

- **Representative**: Common aerospace structural material
- **Well-Characterized**: Established material properties
- **Appropriate Stiffness**: Provides realistic modal frequencies in measurable range
- **Scalable**: Results can be extrapolated to similar metallic structures

---

## CBUSH Element Configuration

### CBUSH Degrees of Freedom

Each CBUSH element has 6 independent stiffness parameters:

| DOF | Symbol | Type | Baseline Value |
|-----|--------|------|----------------|
| K1 | Translation X | Axial | 1.0E+6 N/m |
| K2 | Translation Y | Lateral | 1.0E+6 N/m |
| K3 | Translation Z | Vertical | 1.0E+6 N/m |
| K4 | Rotation X | Roll | **Variable** |
| K5 | Rotation Y | Pitch | **Variable** |
| K6 | Rotation Z | Yaw | **Variable** |

### Why Focus on Rotational Stiffness (K4, K5, K6)?

Beam structures are particularly sensitive to rotational stiffness because:

1. **Bending Behavior**: Moment transfer across joints depends on rotational stiffness
2. **Modal Sensitivity**: Natural frequencies shift significantly with rotational stiffness changes
3. **Physical Relevance**: Bolt loosening primarily affects rotational constraint before translational
4. **Detection Sensitivity**: Rotational stiffness variations produce larger PSD changes than translational

### Stiffness Range

The study spans 10 orders of magnitude in rotational stiffness:

| Encoded Value | Stiffness (N·m/rad) | Description |
|---------------|---------------------|-------------|
| 1 | 1×10⁴ | Extremely loose (near pinned) |
| 2 | 1×10⁵ | Very loose |
| 3 | 1×10⁶ | Loose |
| 4 | 1×10⁷ | Medium-loose |
| **5** | **1×10⁸** | **Driving CBUSH (reference)** |
| 6 | 1×10⁹ | Medium |
| 7 | 1×10¹⁰ | Medium-tight |
| 8 | 1×10¹¹ | Tight |
| **9** | **1×10¹²** | **Very tight (baseline/healthy)** |
| 10 | 1×10¹³ | Extremely tight |
| 11 | 1×10¹⁴ | Ultra tight |

---

## Baseline Stiffness Encoding

### The Driving CBUSH Concept

**Critical Understanding**: Bolt 1 is NOT a "loose" bolt - it is the **Driving CBUSH** that provides excitation input to the structure.

```
BASELINE CONFIGURATION:

Bolt 1:  K4=1e8,  K5=1e12, K6=1e12  (encoded: 5,9,9) ← DRIVING CBUSH
Bolt 2:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 3:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 4:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 5:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 6:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 7:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 8:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 9:  K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
Bolt 10: K4=1e12, K5=1e12, K6=1e12  (encoded: 9,9,9) ← Healthy
```

### Why This Configuration?

1. **Bolt 1 K4 at 1e8**: Provides controlled compliance for driving excitation
2. **Bolt 1 K5, K6 at 1e12**: Maintains structural integrity in other directions
3. **Bolts 2-10 at 1e12**: Represents "fully tight" healthy bolted joints
4. **Parametric Studies**: Only vary Bolts 2-10 to study looseness detection

---

## Dynamic Analysis Results

### Analysis Workflow

The baseline analysis uses a two-step Nastran process:

1. **SOL SEMODES**: Extract natural frequencies and mode shapes
2. **SOL 111 (Restart)**: Random vibration analysis using modal superposition

### Excitation Profile

Random base excitation applied in X, Y, Z directions:

| Frequency Range | PSD Level | Units |
|-----------------|-----------|-------|
| 20 - 2000 Hz | 1.0 | g²/Hz |

This flat spectrum ensures all structural modes are excited equally.

### Modal Frequencies (Baseline)

The natural frequencies extracted from `fixed_base_beam.f06` (SOL SEMODES):

| Mode | Frequency (Hz) | In Analysis Range | Description |
|------|----------------|-------------------|-------------|
| 1 | **62.55** | ✓ | First bending (fundamental) |
| 2 | **253.41** | ✓ | Second bending |
| 3 | **1102.35** | ✓ | Third bending |
| 4 | **1485.45** | ✓ | Fourth bending |
| 5 | **1759.88** | ✓ | Fifth bending |
| 6 | 3318.65 | ✗ | Above 2000 Hz analysis range |
| 7 | 3818.15 | ✗ | Above 2000 Hz analysis range |
| 8 | 5240.91 | ✗ | Above 2000 Hz analysis range |
| 9 | 6364.08 | ✗ | Above 2000 Hz analysis range |
| 10 | 6754.13 | ✗ | Above 2000 Hz analysis range |

*Source: baseline/fixed_base_beam.f06, CYCLES output from eigenvalue extraction*

### PSD Response Characteristics

From the baseline PSD data (28,728 data points stored):

**Node 1111 (Free End) - T1 Direction:**
- Shows clear resonance peaks at **253 Hz** and **1485 Hz**
- These correspond to **Mode 2** and **Mode 4** from the modal analysis
- Peak PSD values reach 2.26×10⁸ (g²/Hz) at Mode 2
- Peak PSD values reach 2.26×10⁸ (g²/Hz)
- Free end has highest response - correct cantilever behavior

**Node 1 (Fixed End):**
- Relatively flat PSD response (~1.49×10⁵ g²/Hz)
- Minimal variation with frequency
- Fixed boundary constraint prevents large motion

---

## PSD Response Interpretation

### Why PSD Analysis?

Power Spectral Density (PSD) analysis reveals:

1. **Frequency Content**: Where energy is concentrated
2. **Resonant Amplification**: How much the structure amplifies input at natural frequencies
3. **Modal Participation**: Which modes dominate the response
4. **Damping Effects**: Peak width indicates energy dissipation

### Cantilever Beam Mode Shapes

Understanding mode shapes is critical for interpreting PSD response and designing effective bolt looseness detection strategies.

**Mode 1 (First Bending) - Fundamental Frequency**
```
Fixed                                                    Free
  │                                                       │
  ├───────────────────────────────────────────────────────┤ Undeformed
  │                                                       │
  ├─────────────────────────────────────────────────╮     │
  │                                              ╭──╯     │ Mode 1
  │                                           ╭──╯        │ Max at tip
  │                                        ╭──╯           │
  ├────────────────────────────────────────╯              │
```
- Zero displacement at fixed end (boundary condition)
- Maximum displacement at free end
- No nodes (zero crossings) along beam
- Lowest frequency (~4 Hz in this model)

**Mode 2 (Second Bending)**
```
Fixed                                                    Free
  │                                                       │
  ├───────────────────────────────────────────────────────┤ Undeformed
  │                                                       │
  ├─────────────────────╮                                 │
  │                     ╰───────╮                    ╭────┤ Mode 2
  │                             ╰────────────────────╯    │
  │                        ▲                              │
  │                      NODE                             │
  │                   (zero crossing)                     │
```
- Zero at fixed end
- **One node at ~78% from root** (zero displacement point)
- Free end moves opposite direction from mid-beam
- Higher frequency than Mode 1

**Mode 3 (Third Bending)**
```
Fixed                                                    Free
  │                                                       │
  ├───────────────────────────────────────────────────────┤ Undeformed
  │                                                       │
  ├────────────╮              ╭────────╮                  │
  │            ╰──────╮  ╭────╯        ╰──────────────────┤ Mode 3
  │                   ╰──╯                                │
  │              ▲              ▲                         │
  │            NODE 1        NODE 2                       │
```
- **Two nodes** along beam length
- Three regions moving in alternating directions
- Even higher frequency

### Response Variation by Mode and Location

The PSD response at any location depends on which modes are excited and the mode shape amplitude at that location:

| Location | Mode 1 Response | Mode 2 Response | Mode 3 Response |
|----------|-----------------|-----------------|-----------------|
| Fixed end (Node 1) | Zero | Zero | Zero |
| Mid-beam | Medium | High | Variable |
| ~78% from root | High | **ZERO (node)** | Variable |
| Free end (Node 1111) | **Maximum** | Medium | Variable |

### Implications for Bolt Looseness Detection

Mode shapes have direct implications for detection sensitivity:

1. **Bolt location relative to mode shapes matters**: A loose bolt near a mode shape node has minimal effect on that mode's frequency, while a loose bolt at an antinode has maximum effect.

2. **Multi-node monitoring is essential**: A single sensor might miss damage at certain locations for certain modes. This study monitors 12 nodes to capture response variations across the entire beam.

3. **Multi-frequency analysis improves detection**: Different modes are sensitive to damage at different locations. Analyzing the full PSD curve (not just the first peak) enables detection regardless of damage location.

4. **Free end generally has highest response**: For the fundamental mode (which typically dominates), the free end (Node 1111) shows maximum response, making it a good indicator of overall structural health.

### Key Metrics Extracted

For each node and DOF, we extract:

| Metric | Description | Physical Meaning |
|--------|-------------|------------------|
| Area | Integral of PSD over frequency | Total response energy |
| Peak 1 Frequency | Highest PSD peak location | Dominant resonance |
| Peak 1 PSD | Amplitude at Peak 1 | Resonant amplification |
| Peak 2/3 Frequency | Secondary peak locations | Higher modes |
| Peak 2/3 PSD | Amplitude at secondary peaks | Mode participation |

---

## Physics Validation

### Expected vs. Observed Cantilever Behavior

The baseline results are validated against classic cantilever beam dynamics:

| Behavior | Expected | Observed | ✓/✗ |
|----------|----------|----------|-----|
| Maximum response at free end | Yes | Node 1111 highest | ✓ |
| Minimum response at fixed end | Yes | Node 1 flattest | ✓ |
| Response increases from root to tip | Yes | Monotonic increase | ✓ |
| Multiple resonance peaks | Yes | Peaks at 253.41, 1485.45 Hz | ✓ |
| Displacement PSD < Acceleration PSD | Yes | 1/ω² relationship | ✓ |
| PSD peaks match modal frequencies | Yes | Mode 2 = 253.41 Hz, Mode 4 = 1485.45 Hz | ✓ |

### Modal Frequency Validation

The PSD peaks observed in the random vibration response directly correspond to the natural frequencies from modal analysis:

| PSD Peak (Hz) | Modal Frequency (Hz) | Mode | Match |
|---------------|---------------------|------|-------|
| ~253 | 253.41 | Mode 2 | ✓ |
| ~1485 | 1485.45 | Mode 4 | ✓ |

**Why Mode 1 (62.55 Hz) is less prominent in PSD:**
- Mode 1 is at the lower end of the excitation range (20-2000 Hz)
- The T1 (axial) direction may have lower participation for the fundamental bending mode
- Mode 2 dominates due to higher modal participation in the monitored DOF

### Mode Shape Validation

At each natural frequency, the response pattern should match theoretical mode shapes:

**Mode 1 (62.55 Hz - First Bending):**
- Maximum deflection at tip
- Zero deflection at root
- Single antinode

**Mode 2 (253.41 Hz - Second Bending):**
- Node (zero crossing) at ~78% from root (~858 mm from fixed end)
- Two antinodes
- **This is the dominant peak in PSD response**

**Mode 3 (1102.35 Hz - Third Bending):**
- Two nodes along beam length
- Three antinodes

**Mode 4 (1485.45 Hz - Fourth Bending):**
- Three nodes along beam length
- Four antinodes
- **Second major peak in PSD response**

### Why This Validation Matters

Establishing that the baseline model produces physically correct behavior is essential before:
1. Generating parametric training data
2. Training ML models on synthetic data
3. Making predictions about real structures

---

## Predictions for Parametric Cases

### Effect of Reducing Bolt Stiffness

When a bolt stiffness is reduced from 1e12 to lower values:

| Effect | Prediction | Physical Reason |
|--------|------------|-----------------|
| Natural frequencies | **Decrease** | Reduced structural stiffness |
| Peak PSD amplitudes | **Increase** | Less energy dissipation at joint |
| Peak widths | **Broader** | More damping from loose joint friction |
| Mode shapes | **Localized changes** | Flexibility concentrated at loose joint |

### Location Sensitivity

The effect of loosening depends on bolt location:

| Bolt Location | Effect on Response |
|---------------|-------------------|
| Near fixed end (Bolt 2-3) | Large frequency shift, moderate amplitude change |
| Mid-span (Bolt 5-6) | Moderate frequency shift, localized amplitude change |
| Near free end (Bolt 9-10) | Smaller frequency shift, large amplitude change at tip |

### Stiffness Level Effects

| Stiffness Reduction | Expected Signature |
|--------------------|-------------------|
| 1e12 → 1e11 | Subtle changes, difficult to detect |
| 1e12 → 1e10 | Measurable frequency shift (~1-5%) |
| 1e12 → 1e8 | Significant changes, easily detectable |
| 1e12 → 1e6 | Major structural change, different mode shapes |
| 1e12 → 1e4 | Near-pinned behavior, fundamentally different dynamics |

---

## Machine Learning Data Rationale

### Why Full PSD Curves?

The database stores full PSD curves (266 frequency points × all nodes × all DOFs) rather than just peaks because:

1. **Curve Shape Information**: Peak-only extraction loses bandwidth, asymmetry, and secondary features
2. **Anomaly Detection**: Unusual curve shapes may indicate damage not captured by peaks
3. **Feature Engineering**: ML algorithms can learn optimal features from raw data
4. **Future Flexibility**: New feature extraction methods can be applied without re-running simulations

### Training Data Strategy

| Case Type | Purpose | Count |
|-----------|---------|-------|
| Baseline | Reference condition | 8 samples |
| Single-bolt loosening | Individual bolt signatures | 9 bolts × 8 levels = 72 samples |
| Multi-bolt (future) | Combined effects | TBD |

### Why Varying Bolts 2-10 Only?

Bolt 1 (Driving CBUSH) remains constant because:
1. It provides the excitation mechanism
2. Varying it would change the input, not just the response
3. Parametric studies should isolate output effects from input changes

### Expected ML Outcomes

With sufficient training data, ML models should be able to:

1. **Classify**: Which bolt(s) are loose
2. **Quantify**: Severity of loosening (stiffness level)
3. **Localize**: Position along beam
4. **Generalize**: Detect loosening patterns not explicitly in training set

---

## Future Work: Experimental Validation

### Why Physical Testing Matters

Finite element models, no matter how carefully validated, contain assumptions that may not hold in reality:

- Idealized boundary conditions
- Perfect material properties
- No manufacturing variations
- Simplified damping models

### Proposed Validation Approach

1. **Build Physical Beam**: Match FEM geometry and materials
2. **Instrument**: Accelerometers at FEM node locations
3. **Apply Excitation**: Random vibration matching FEM input
4. **Compare**: FEM predictions vs. measured response
5. **Calibrate**: Adjust model parameters to match reality

### What Test Data Would Provide

| Benefit | Description |
|---------|-------------|
| Model Validation | Confidence that synthetic training data is realistic |
| Damping Characterization | Real joints have complex damping not captured in FEM |
| Boundary Condition Verification | Fixed end may not be perfectly rigid |
| Noise Characterization | Real sensors have noise not in simulation |
| Transfer Learning | Ability to fine-tune ML models with real data |

### Interim Strategy

Until physical test data is available:
1. Use conservative assumptions in FEM
2. Include damping sensitivity studies
3. Document model limitations clearly
4. Design ML models for robustness to model uncertainty

---

## Summary

This baseline beam configuration provides:

1. **Physically Valid Model**: Correct cantilever behavior with bolted joints
2. **Controlled Parameters**: Independent variation of bolt stiffness
3. **Comprehensive Data**: Full PSD curves at all monitored locations
4. **ML-Ready Database**: 28,728+ data points per case in SQLite
5. **Scalable Framework**: Ready for parametric studies and HEEDS integration

The baseline establishes the "healthy" reference against which all degraded conditions will be compared, enabling systematic study of bolt looseness detection through dynamic response analysis.

---

## References

- MSC Nastran 2025.1 Quick Reference Guide
- NASA-HDBK-7005: Dynamic Environmental Criteria
- Ewins, D.J. "Modal Testing: Theory, Practice and Application"
- Inman, D.J. "Engineering Vibration"

---

## Version History

| Date | Change | Author |
|------|--------|--------|
| 2026-01-03 | Initial document | Wayne Lee |
| 2026-01-03 | Added actual modal frequencies from fixed_base_beam.f06 | Wayne Lee |
| 2026-01-03 | Validated PSD peaks against modal analysis | Wayne Lee |

---

## Contact

- **Author**: Wayne Lee (waynelee@vt.edu)
- **Repository**: https://github.com/VirginiaTechWLee/Thesis_Workflow
