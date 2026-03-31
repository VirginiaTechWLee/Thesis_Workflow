# Session Log — Thesis Pipeline Development

## Date: 2026-03-30 (Evening Session ~7:00 PM)

### Mission
Full end-to-end proof test of the thesis pipeline running LOCALLY.
DB goes from EMPTY to FULL. All 4 studies generated FRESH today.
No stale data. No skipped steps. Treat it like an engineer testing for the first time.

---

## Fix History (this session)

### Fix 1: Steps 4-7 converted to in-process execution
- Python 3.13 subprocess + sqlite3 = segfault (0xC0000005)
- Steps 4 (Miles), 5 (Features), 6 (Train), 7 (Reports) now call functions directly
- Step 4: `compute_miles.populate_miles_table(DB_PATH)`
- Step 5: `extract_features.build_training_matrix(db_path, output_path, noise_floor=1e-5)`
- Step 6: `train_classifier.main()` with sys.argv override
- Step 7: `run_local_report.generate_one_report(...)` directly
- Same pattern as step 3 (import) which was converted in prior session

### Fix 2: Removed numpy from batch_import_to_database.py
- `find_peaks()` and `calculate_area()` rewritten in pure Python
- numpy + sqlite3 in same process was causing segfaults after ~20 designs
- No more `import numpy as np` in that file
- Trapezoidal integration done with a simple for loop

### Fix 3: Added reconnect-every-10-designs workaround
- `batch_import_to_database.py` closes and reopens sqlite3 connection every 10 designs
- `RECONNECT_EVERY = 10`
- Resets C-level state to prevent memory corruption
- **NOT YET TESTED** — first real test will be when Study A import runs after HEEDS

### Fix 4: Fixed HEEDS launch — wrong executable
- `config.yaml` had `heeds_mdo_path: C:\HEEDS\MDO\Ver2410\Python3\python.exe` (WRONG)
- Changed to `heeds_mdo_path: C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe`
- Matches GitHub workflow `vars.HEEDS_MDO_PATH`
- That's why all 4 studies failed with `NameError: name 'ript' is not defined`
- The Python interpreter was parsing `-b -script` as Python code

### Fix 5: Created utility scripts (read paths from config.yaml)
- `pipeline/clean_heeds.py` — deletes study folders, .heeds files, DB, reports
- `pipeline/clean_database.py` — truncates all DB data, keeps schema intact

---

## Current State (before launching pipeline)
- All old study folders DELETED (A, B, C, D)
- All old .heeds files DELETED
- Database DELETED and RECREATED (empty schema)
- Old reports DELETED
- Old training_matrix.npz DELETED
- config.yaml: study_A_single_bolt_sweep, heeds_mdo_path = HEEDSMDO.exe

---

## Pipeline Run Log

### Run 1: ~7:13 PM — FAILED (HEEDS wrong executable)
- FEM Utility completed (SOL 103 + SOL 111 baseline)
- All 4 HEEDS launches failed: `NameError: name 'ript' is not defined`
- Root cause: heeds_mdo_path pointed to Python interpreter, not HEEDSMDO.exe
- Fixed in config.yaml

### Run 2: ~7:20 PM — LAUNCHED (HEEDS exe fixed)
- Command: `python run_pipeline.py --chain all --non-interactive`
- Log file: `D:\thesis_database\full_run_20260330_192500.log`
- FEM Utility: completed (SOL 103 + SOL 111)
- Study A HEEDS: COMPLETE (73 designs)
- Study A Import: FAILED (UNIQUE constraint — fixed with frequency column)
- Study B HEEDS: COMPLETE (288 designs)
- Study B Import: FAILED (same bug — will be retried)
- Study C HEEDS: IN PROGRESS — 302/672 at 11:02 PM
- ETA: ~1 AM for C to finish, then D (501), all HEEDS done ~2 AM

---

## Expected Flow
1. Step 1: FEM Utility — Nastran SOL 103 + SOL 111 (runs ONCE)
2. Per study (A→B→C→D):
   - Step 2: HEEDS — generate .heeds, copy files, launch HEEDSMDO.exe, monitor POST_0
   - Step 3: Import POST_0 into DB (in-process, reconnect every 10 designs)
   - Step 4: Compute Miles equation (in-process)
   - Step 5: Extract ML features (in-process)
   - Step 6: Train classifier (in-process)
   - Step 7: LLM reports x8 (in-process)
   - Step 8: Word report (Node.js — not affected by sqlite3 bug)

## Study Details
| Study | Designs | Type |
|-------|---------|------|
| study_A_single_bolt_sweep | 73 | single bolt, 9 bolts x 9 levels |
| study_B_two_bolt_sweep | 288 | two-bolt combinations |
| study_C_three_bolt_sweep | 672 | three-bolt combinations |
| study_D_monte_carlo | 501 | random sampling, seed=42 |

## POST_0 Folder Paths (will be generated fresh today)
```
C:\Users\waynelee\Documents\study_A_single_bolt_sweep_Study_1\POST_0
C:\Users\waynelee\Documents\study_B_two_bolt_sweep_Study_1\POST_0
C:\Users\waynelee\Documents\study_C_three_bolt_sweep_Study_1\POST_0
C:\Users\waynelee\Documents\study_D_monte_carlo_Study_1\POST_0
```

## Validation Checklist
- [ ] Study A POST_0 last file has today's date (3/30/2026)
- [ ] Study B POST_0 last file has today's date
- [ ] Study C POST_0 last file has today's date
- [ ] Study D POST_0 last file has today's date
- [ ] DB import completes without segfault (reconnect workaround works)
- [ ] Miles equation completes for all studies
- [ ] Feature extraction produces training_matrix.npz
- [ ] Classifier trains successfully
- [ ] All 8 LLM reports generated per study
- [ ] Word report generated per study
- [ ] Final DB has all 1,534 designs (73+288+672+501)

## Known Limitations
- HEEDS results won't have force PSD or f06 data (old templates)
- Force:0, ForcePeaks:0, ESE:0 is expected
- Classifier trains on accel/disp features only

---

## Key Paths (from config.yaml — NEVER guess)
| Variable | Value |
|----------|-------|
| HEEDS working dir | `C:\Users\waynelee\Documents` |
| Database | `D:\thesis_database\thesis_results.db` |
| HEEDS exe | `C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe` |
| Nastran exe | `C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe` |
| Python exe | `C:\ProgramData\anaconda3\python.exe` |
| Pipeline scripts | `C:\Users\waynelee\Desktop\pipeline\` |
| DB scripts | `C:\Users\waynelee\Desktop\heeds\database\` |
| ML scripts | `C:\Users\waynelee\Desktop\Scripts\` |
| Config | `C:\Users\waynelee\Desktop\fem_input\config.yaml` |
| API key | `C:\Users\waynelee\Desktop\.env` |

---

### Fix 6: Added HEEDS completion fallback
- If all expected PCH files are present but HEEDS doesn't write "End of HEEDS run" to log
- Waits 60s after last PCH appears, then proceeds
- Prevents infinite loop if HEEDS doesn't communicate completion

## Strain Energy Status
- `ESE = ALL` in RandomBeamX.dat — Nastran writes ESE for EVERY element to f06
- Parser: `parse_f06_strain_energy()` in batch_import reads element_id, type, energy, percent
- DB table: `strain_energy(case_id, element_id, element_type, subcase_id, strain_energy, percent_total)`
- f06 file stays in `Design{N}/Analysis_1/randombeamx.f06` (not cleaned up by bat)
- ESE is per-element (CBUSH bolts 1-10, CBEAM, etc.), not per-node
- CBUSH strain energy = key feature for bolt looseness detection

## Force PSD Status
- `XYPUNCH,FORCE,PSDF` in Recoveries.blk for all 10 CBUSH elements
- `SET 2 = 1,2,3,4,5,6,7,8,9,10` and `FORCE(PLOT,PHASE,CORNER,PSDF) = 2` in RandomBeamX.dat
- Force PSD goes to PCH file alongside accel/disp
- Parser: `parse_pch_file()` handles `$EL FOR` headers
- DB tables: `force_psd_data`, `force_peaks`

### Fix 7: Strain energy parser — added frequency column, BUSH-only filter
- f06 has ESE at every frequency step (not just one summary)
- Added `frequency REAL` column to strain_energy table
- UNIQUE constraint now: `(case_id, element_id, subcase_id, frequency)`
- Parser filters to `ELEMENT-TYPE = BUSH` only (bolts 1-10)
- BEAM elements are structural noise (0.001% of energy) — skipped
- ~10 bolts x ~200 freq steps = ~2,000 rows per design

### Fix 8: Chain retry logic — no more break on failure
- Old: if import failed, `break` skipped all remaining steps for that study
- New: keeps trying remaining steps even if one fails
- Added retry pass at end: re-runs all failed imports + downstream (Miles, features, train, reports)
- HEEDS data stays on disk — just needs re-import

## Errors Encountered This Run

### Study A import failed (Run 2, ~7:45 PM)
- Error: `sqlite3.IntegrityError: UNIQUE constraint failed: strain_energy.case_id, strain_energy.element_id, strain_energy.subcase_id`
- Root cause: f06 has ESE at every frequency step, parser stored duplicates
- Fix: added `frequency` column to schema + parser
- Study A data is on disk — will be re-imported by retry pass

---
*Log started 2026-03-30 ~7:20 PM*
