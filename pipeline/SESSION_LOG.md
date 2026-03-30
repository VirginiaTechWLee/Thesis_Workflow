# Session Log — Thesis Pipeline Development

## Date: 2026-03-29

### Mission
Complete Studies A through D with full pipeline automation. Build a one-button system that any mechanical engineer can run on any FEM.

---

### Current Database State
| Study | study_id | Cases | is_baseline | Status |
|-------|----------|-------|-------------|--------|
| study_baseline | 0 | 1 | 1 | Healthy FEM reference |
| study_A_single_bolt_sweep | 1 | 73 | 0 | Complete |
| study_B_two_bolt_sweep | 2 | 287 | 0 | Complete |
| study_C_three_bolt_sweep | 3 | 672 | 0 | Complete |
| study_D_monte_carlo | 4 | TBD (500+) | 0 | Pending |

- DB Size: 3,349 MB
- Total PSD rows: 30,253,284
- Miles equation rows: 245,983
- Peaks: 111,564
- Parameters: 10,330

---

### Step Plan (in order)

#### Step 1: ML Feature Extraction + Classifier on A+B+C [COMPLETE]
- 1,033 samples x 2,343 features (756 peaks + 96 spectral + 72 delta + 1,495 Miles - 76 zero-variance)
- Log-transform on 998 amplitude columns + StandardScaler normalization
- **GradientBoosting: 98.65% accuracy (+/- 0.39%)** — best model
- **RandomForest: 98.45% accuracy (+/- 0.19%)**
- 10-class bolt localization (element 0=healthy, elements 2-10=loosened bolts)
- Top features: R2 displacement area (node 222), R2 displacement area (nodes 555, 666, 444)
- Miles features appear in top 20: PSDfn, grms contributing to classification
- Weak spots: element 0 (only 2 healthy samples), element 10 (only 8 samples)
- Saved: D:\thesis_database\bolt_classifier.pkl, classification_report.txt

#### Step 2: Run Study D (Monte Carlo)
- 500+ random designs from discrete stiffness levels
- Trigger via super_workflow.yml with study_type=study_D
- Expected runtime: ~2+ hours for 500 Nastran runs

#### Step 3: Re-run ML with A+B+C+D Combined
- Compare classifier accuracy before/after Monte Carlo
- Monte Carlo adds unseen random bolt combinations vs structured sweeps
- Expect improved generalization

#### Step 4: Validate LLM Analysis Reports
- Most critical step — this is the user-facing output
- Verify LLM conclusions match actual DB data
- Check: sensitive nodes, detectability thresholds, Q factor trends, GRMS patterns
- Report must be trustworthy for a boss-level demo

#### Step 5: Add CBUSH Forces + Strain Energy
- **Nastran DAT file status:**
  - SOL 111 (RandomBeamX.dat): HAS `FORCE(PLOT,PHASE,CORNER,PSDF) = 2` — forces ARE requested
  - SOL 111: Does NOT have ESE (strain energy) — need to add
  - SOL SEMODES (Fixed_base_beam.dat): HAS both FORCE and ESE
- **Action needed:**
  - Add ESE card to SOL 111 deck
  - Add DB tables for forces and strain energy
  - Update PCH parser to read force/strain energy data types
  - Re-run baseline with updated request
  - Re-run all studies to get force/strain energy for every case
- **Area under PSD curve**: Already captured in peaks table (`area` column = integral of PSD = RMS squared)

#### Step 6: Full End-to-End Test from Clean DB
- Wipe database completely
- Run entire pipeline from scratch (baseline + A + B + C + D)
- Proves system is self-sufficient and one-button
- This is the "walk away and come back" demo

---

### Key Decisions Made Today

1. **Baseline is its own study** — study_baseline at study_id=0, not duplicated per-study
2. **Default folder_mode changed to skip_if_exists** — prevents accidental data loss
3. **No artificial timeouts** — HEEDS can run for days on big FEMs
4. **Looseness threshold is K-ratio only** — forces/strain energy are FEATURES, not labels
   - Labels = ground truth (which bolt had K reduced)
   - Features = structural response (PSD, forces, Miles, strain energy)
   - Prevents circular logic in classifier
5. **Only sweeping rotational stiffness (K4, K5, K6)** — K1-K3 not varied in HEEDS
6. **Miles equation added to DB and ML features** — fn, Q, PSD_fn, GRMS, bandwidth per resonance
7. **Log-transform + StandardScaler normalization** — compresses orders of magnitude for ML

### Pending Future Work (Post Step 6)
- Multi-label classification for multi-bolt studies (B/C/D bitmask labels)
- MCP interactive diagnostics
- LLM analysis of ML results (the "AI analyzing AI" layer)
- Test on a different FEM to prove generalization
- HEEDS command-line resume capability (question for Ernesto at Siemens)

---

### Files Modified This Session
| File | Change |
|------|--------|
| `heeds/database/compute_miles.py` | NEW — computes Miles equation from PSD data |
| `heeds/database/setup_database.py` | Added miles table, is_baseline column |
| `Scripts/extract_features.py` | Added Miles features, log-transform, StandardScaler |
| `pipeline/generate_pipeline_report.py` | Added Miles data to DB health + PSD signature reports |
| `pipeline/db_summary.py` | Added miles table to summary |
| `.github/workflows/super_workflow.yml` | Added compute_miles step (Stage 6b) |
