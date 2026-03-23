# Thesis Pipeline — Master Task Plan & Context
**Project:** Spacecraft Bolt Looseness Detection — ML + FEM Pipeline  
**Engineer:** Wayne Lee (Batman)  
**Machine:** GL-MERCURY (VT VM, Windows Server)  
**Repo:** https://github.com/VirginiaTechWLee/Thesis_Workflow  
**Repo root on machine:** C:\Users\waynelee\Desktop  
**Status:** Super Workflow 16/16 stages GREEN ✅  
**Last updated:** 2026-03-22

---

## Critical Rules for Claude Code Sessions

1. **Always start by reading docs/SESSION_LOG.md** — it is the source of truth
2. **Always operate from C:\Users\waynelee\Desktop** — never cd into Documents subfolders or Windows will lock study folders
3. **gh CLI is at C:\Users\waynelee\gh\bin\gh.exe** — always export PATH="$PATH:/c/Users/waynelee/gh/bin" before any gh command
4. **Always run gh auth setup-git before any git push**
5. **Python is at C:\ProgramData\anaconda3\python.exe**
6. **Nastran is at C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe**
7. **HEEDS working directory is C:\Users\waynelee\Documents** — do not change this
8. **Database is at D:\thesis_database\thesis_results.db**
9. **If SESSION_LOG.md ends abruptly — Claude Code crashed, resume from last entry**
10. **Update SESSION_LOG.md at every milestone marking STATUS: ACTIVE or CRASHED**
11. **Full permission to edit any file, run any command, commit, push, trigger workflows without asking**

---

## What Has Been Built (Already Working)

### Super Workflow — 16/16 Stages GREEN
`.github/workflows/super_workflow.yml`

User drops 3 files into `fem_input/`:
- `Fixed_base_beam.dat` — Nastran structural deck
- `Bush.blk` — CBUSH bolt properties
- `config.yaml` — pipeline configuration

Pipeline runs automatically end to end:
1. ✅ Checkout repository
2. ✅ Read config.yaml
3. ✅ Validate FEM inputs
4. ✅ Generate FBM_TO_DBALL.bat from config
5. ✅ Generate baseline Bush.blk (Femap format)
6. ✅ Generate HEEDS project file (.heeds XML)
7. ✅ Kill existing HEEDS processes
8. ✅ Handle existing study folder
9. ✅ Copy files to HEEDS working directory
10. ✅ Run HEEDS parametric sweep (5 designs, all verified)
11. ✅ Setup database
12. ✅ Batch import HEEDS results (5 designs, 172K PSD rows)
13. ✅ Import baseline (case 0)
14. ✅ Show database summary
15. ✅ Extract features (756 peak features)
16. ✅ Train classifier (67% accuracy, RandomForest)

### Pipeline Scripts (config-driven, in pipeline/)
- `pipeline/config_loader.py` — loads fem_input/config.yaml
- `pipeline/validate_fem_inputs.py` — validates FEM files
- `pipeline/generate_bat.py` — generates FBM_TO_DBALL.bat
- `pipeline/generate_baseline_bush.py` — generates Bush.blk
- `pipeline/generate_heeds_project.py` — generates .heeds XML
- `pipeline/read_config.py` — outputs config values for workflow steps
- `pipeline/db_summary.py` — prints database statistics

### Key Architecture Decisions
- New config-driven scripts in `pipeline/` — do NOT modify existing scripts in `Scripts/` or `heeds/` (those are the validated beam baseline)
- `fem_input/` is the drop zone for all FEM files
- `FEM_Utility/` (to be created at C:\Users\waynelee\Documents\FEM_Utility\) is for standalone Nastran utility runs
- Database at D:\thesis_database\ — separate from repo
- HEEDS study folders at C:\Users\waynelee\Documents\ — separate from repo

### The DBALL Chain
The pipeline uses a two-step Nastran solve:
1. **SOL 103 (Fixed_base_beam.dat, scratch=no)** → generates DBALL modal database
2. **SOL 111 (RandomBeamX.dat)** → reads DBALL, computes random PSD response → produces randombeamx.pch

`scratch=no` preserves the DBALL between runs. The 10-second wait in FBM_TO_DBALL.bat ensures DBALL is fully written before SOL 111 reads it. The DBALL chain is also useful as a standalone troubleshooting step — you can validate the full SOL 103 → SOL 111 chain independently before running the full parametric sweep.

---

## Task Overview

| # | Task | Status | Priority |
|---|------|--------|----------|
| 1 | Nastran Utility Workflow | ✅ COMPLETE | HIGH |
| 2 | LLM Simulation Reports in Super Workflow | ✅ COMPLETE | HIGH |
| 3 | Full Factorial Sweep | ⬜ Planned | HIGH |
| 4 | Femap Image Automation + PDF/DOCX Reports | ⬜ Planned | HIGH |
| 5 | Master Concatenated Report | ✅ COMPLETE | MEDIUM |
| 6 | MCP Interactive Diagnostics | ⬜ Planned | NORTH STAR |

---

## Task 1 — Nastran Utility Workflow (COMPLETE ✅)

**Completed:** 2026-03-22. All stages green in 46 seconds. See `fem_input/README.md` for the FEM onboarding guide (DAT, Bush.blk, RandomBeamX.dat format requirements).

### Purpose
A standalone Nastran runner for FEM validation and troubleshooting. Completely separate from the super workflow. Runs the DBALL chain (SOL 103 → SOL 111) on any FEM in `fem_input/` and produces a self-contained timestamped run folder with an LLM-generated simulation report.

### Why This Matters
- FEM health check before committing to a full parametric sweep
- Troubleshooting tool — if super workflow fails on a new FEM, run this first to isolate whether the problem is the FEM or the pipeline
- DBALL validation — confirms FEM is DBALL-ready before HEEDS ever touches it
- LLM diagnostics — Claude reads F06 and explains results in plain English instead of manual F06 parsing
- Random vibration DBALL run serves as a troubleshooting step — validates full SOL 103 → SOL 111 chain independently

### Trigger Methods (All Four Required)
1. **MCP** — highest priority — Claude Desktop calls `run_nastran_validation` tool → hits GitHub API `repository_dispatch` → triggers workflow
2. **GitHub Actions UI** — manual workflow_dispatch with dropdowns
3. **git push** — auto-trigger ONLY on `fem_input/*.dat` or `fem_input/*.blk` changes (NOT config.yaml changes)
4. **Claude Code** — gh workflow run from terminal

### Input
Files already in `fem_input/` — no new drop zone needed, just copy from there:
- `<model>.dat` — Nastran structural deck (must be SOL SEMODES/SOL 103)
- `Bush.blk` — CBUSH properties
- `RandomBeamX.dat` — random response deck (required for full/sol111 runs)
- `config.yaml` — add `analysis.type: sol103 | sol111 | full`

### Output — Timestamped Run Folder
`C:\Users\waynelee\Documents\FEM_Utility\<study_name>_<YYYYMMDD_HHMMSS>\`

Everything in ONE self-contained folder — no subdirectories by file type:
- Input DAT file (copy)
- ALL Nastran outputs — F06, OP2, DBALL, PCH, .log, .MASTER, .IFPDAT, everything Nastran produces
- `simulation_report.md` — LLM-generated plain English report

Nothing committed to git. Add `FEM_Utility/` to `.gitignore`.

### Analysis Types
| Type | What Runs | Output |
|------|-----------|--------|
| `sol103` | SOL 103 modal only | F06 with natural frequencies, DBALL |
| `sol111` | SOL 111 random only (assumes DBALL exists) | PCH with PSD data |
| `full` | SOL 103 → 10s wait → SOL 111 (DBALL chain) | Full F06 + PCH + all outputs |

### DBALL Readiness Validation (add to validate_fem_inputs.py)
Before running Nastran, check:
1. DAT file uses `SOL SEMODES` or `SOL 103`
2. `scratch=no` present in Nastran command (preserves DBALL between runs)
3. At least one SPC or boundary condition present (no free-free models)
4. `RandomBeamX.dat` exists in `fem_input/` (required for full/sol111 runs)
5. `DLOAD` or `RANDPS` cards present in random response deck

Fail fast with clear error message if any check fails — do not waste a Nastran run on a bad FEM.

### LLM Simulation Report
Generated by `pipeline/generate_simulation_report.py` using Anthropic API.

**Grounded system prompt (CRITICAL — enforce strictly):**
> "You are a Nastran simulation analyst. Analyze ONLY the F06 content provided to you in this message. Do not use any outside knowledge about Nastran, spacecraft, or structural analysis. If the data does not support a conclusion, say so explicitly. Never invent frequencies, results, or conclusions not present in the provided data. Flag any FATAL errors, list natural frequencies, summarize random response results, and state whether the model is healthy and DBALL-ready."

**Report sections:**
1. Model Summary — nodes, elements, CBUSH count, boundary conditions parsed from F06
2. Natural Frequencies — first 10 modes with frequencies in Hz
3. Warnings and Fatals — any FATAL or WARNING messages from F06
4. DBALL Chain Status — did SOL 103 and SOL 111 complete cleanly
5. Random Response Summary — peak PSD values, dominant frequencies (if full run)
6. Health Assessment — is this FEM ready for the super workflow?

**API call rules:**
- Pass ANTHROPIC_API_KEY via env variable in workflow YAML step
- Temperature = 0 (deterministic, no creativity)
- No web search tool enabled
- Only F06 file contents passed as context — nothing else

### Files to Create
| File | Purpose |
|------|---------|
| `.github/workflows/nastran_utility.yml` | Main workflow |
| `pipeline/run_nastran_utility.py` | Nastran runner — creates timestamped folder, copies files, runs Nastran, collects all outputs |
| `pipeline/generate_simulation_report.py` | Reads F06, calls Anthropic API with grounded prompt, writes simulation_report.md |
| Updates to `fem_input/config.yaml` | Add `analysis.type` field |
| Updates to `pipeline/validate_fem_inputs.py` | Add DBALL readiness checks |
| Updates to `.gitignore` | Add `FEM_Utility/` |

### MCP Trigger API Call (document in SESSION_LOG.md)
```
POST https://api.github.com/repos/VirginiaTechWLee/Thesis_Workflow/dispatches
Authorization: Bearer <GITHUB_TOKEN>
Content-Type: application/json
Body: {"event_type": "nastran_validation"}
```

### Proof of Success
- Workflow triggers via all 4 methods
- Timestamped folder created at C:\Users\waynelee\Documents\FEM_Utility\
- All Nastran outputs present in one folder (no subdirectories)
- simulation_report.md generated with natural frequencies and health assessment
- DBALL readiness checks catch bad FEMs before Nastran runs

---

## Task 2 — LLM Simulation Reports in Super Workflow

8 report stages embedded in the existing super workflow using Anthropic API. Each report reads ONLY actual stage output — no outside knowledge allowed. Same grounded system prompt pattern as Task 1.

**Report trigger points:**
1. Pre-run FEM health check (reads DAT file)
2. Study plan summary (reads config + .heeds file)
3. HEEDS run status (reads run logs + verified design count)
4. Database health (queries SQLite for row counts, outliers)
5. Feature matrix health (reads training_matrix.npz stats)
6. Classification results (reads classification_report.txt)
7. Ensemble results (reads model accuracy + confidence)
8. Validation summary (overall pipeline health)

---

## Task 3 — Full Factorial Sweep

Update `fem_input/config.yaml` to run all 10 bolts × multiple stiffness levels.
Target: 500+ cases minimum for a credible ML classifier.
Also add proper train/test split (hold out 20-30%) before CV.
Add binary classifier (healthy vs damaged) alongside bolt localization.
Feature importance analysis — which nodes/DOFs are most diagnostic = where to place sensors on real spacecraft.

---

## Task 4 — Femap Image Automation + PDF/DOCX Reports

Femap COM automation to grab mesh views, mode shapes, BC overlays, and CBUSH locations as PNGs, then embed them in PDF/DOCX reports using python-docx or reportlab. Applies to both the super workflow and nastran utility workflow.

**Implementation:**
- Add Femap COM steps as `continue-on-error: true` — never blocks the pipeline
- Capture PNGs from Femap views: mesh, mode shapes, boundary conditions, CBUSH locations
- Embed images in PDF/DOCX using python-docx or reportlab
- Output to REPORTS_DIR alongside LLM reports

**Prerequisites:**
- Femap installed and licensed on GL-MERCURY
- pywin32 for COM automation

---

## Task 5 — Master Concatenated Report (COMPLETE ✅)

**Completed:** 2026-03-22. Script `pipeline/concatenate_reports.py` reads all numbered reports (01_*.md through 07_*.md) from REPORTS_DIR and produces `00_master_report.md` with cover page and table of contents.

**Implementation:**
- `pipeline/concatenate_reports.py` — discovers, concatenates, adds TOC
- Integrated into super_workflow.yml after executive summary report
- Runs only when `llm_reports == true`
- Non-fatal (`continue-on-error` pattern) — failure never blocks pipeline

---

## Task 6 — MCP Interactive Diagnostics (North Star)

Claude Desktop connected to live SQLite database and trained model via MCP SQLite server and filesystem MCP server.

Engineer asks natural language questions:
> "Which bolt has the highest probability of being loose?"
> "How confident are you and what frequency signatures are you seeing?"
> "What happened the last time bolt 5 was at this stiffness level?"

**This is the thesis contribution that nobody else has done** — LLM as a natural language interface for structural health monitoring diagnostics. The LLM is the interface to the entire engineering pipeline.

Setup needed:
- SQLite MCP server connected to D:\thesis_database\thesis_results.db
- Filesystem MCP server connected to repo root
- Claude Desktop config updated with both servers
- ANTHROPIC_API_KEY already configured

---

## Claude Code Prompt for Task 1

Copy and paste this entire block into a fresh Claude Code session:

---

Read docs/SESSION_LOG.md for full context. We are implementing Task 1 — the Nastran Utility Workflow. This is a standalone workflow separate from the super workflow. Here are the exact implementation steps:

STEP 1 — Add analysis section to fem_input/config.yaml with type field supporting sol103, sol111, or full. Default to full which runs the full DBALL chain (SOL 103 then SOL 111 sequentially).

STEP 2 — Create C:\Users\waynelee\Documents\FEM_Utility\ as the dedicated working directory for all standalone Nastran utility runs. Add FEM_Utility/ to .gitignore so nothing gets committed.

STEP 3 — Update pipeline/validate_fem_inputs.py to add DBALL readiness checks: 1) DAT file uses SOL SEMODES or SOL 103, 2) scratch=no present in Nastran command, 3) at least one SPC boundary condition present (no free-free models), 4) RandomBeamX.dat exists in fem_input/ for full or sol111 runs, 5) DLOAD or RANDPS cards present in random response deck. Fail immediately with clear error message if any check fails.

STEP 4 — Create pipeline/run_nastran_utility.py that: reads fem_input/config.yaml, creates a timestamped subfolder under C:\Users\waynelee\Documents\FEM_Utility\ named <study_name>_<YYYYMMDD_HHMMSS>, copies fem_input DAT and Bush.blk and RandomBeamX.dat into that folder, runs Nastran from that folder using C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe — for sol103 runs Fixed_base_beam.dat with scratch=no, for full runs Fixed_base_beam.dat with scratch=no then waits 10 seconds then runs RandomBeamX.dat, collects ALL Nastran outputs (F06, OP2, DBALL, PCH, log, MASTER, IFPDAT, everything Nastran produces) — all in one folder, no subdirectories.

STEP 5 — Create pipeline/generate_simulation_report.py that: reads the F06 file from the timestamped folder, extracts natural frequencies, FATAL and WARNING messages, DBALL chain status, random response summary, calls Anthropic API via os.environ ANTHROPIC_API_KEY with this exact grounded system prompt: You are a Nastran simulation analyst. Analyze ONLY the F06 content provided to you in this message. Do not use any outside knowledge. Flag any FATAL errors, list natural frequencies, summarize random response results, state whether the model is DBALL-ready. Use temperature=0. Writes simulation_report.md into the same timestamped folder alongside all other outputs.

STEP 6 — Create .github/workflows/nastran_utility.yml with these triggers: workflow_dispatch for manual GitHub UI trigger, push on paths fem_input/*.dat and fem_input/*.blk only (NOT fem_input/config.yaml), and repository_dispatch with event_type nastran_validation for MCP triggering. Workflow steps: validate inputs, run nastran utility, generate report. Pass env ANTHROPIC_API_KEY from secrets to the report generation step. Check if anthropic pip package is installed and install it if needed.

STEP 7 — Document the exact repository_dispatch API call in docs/SESSION_LOG.md under a section called MCP TRIGGER so Claude Desktop can use it later: POST https://api.github.com/repos/VirginiaTechWLee/Thesis_Workflow/dispatches with Authorization Bearer GITHUB_TOKEN and body event_type nastran_validation.

Always stay in C:\Users\waynelee\Desktop. Use gh at C:\Users\waynelee\gh\bin\gh.exe. Run gh auth setup-git before any push. Update SESSION_LOG.md marking STATUS ACTIVE at every milestone. If you crash and restart read SESSION_LOG.md and resume from last entry without waiting for user input. Full permission to do everything. Do not stop until nastran_utility.yml triggers successfully and a simulation_report.md appears in a timestamped folder under C:\Users\waynelee\Documents\FEM_Utility\.