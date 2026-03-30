"""
run_pipeline.py -- Local end-to-end pipeline orchestrator.

Runs every stage of the bolt-looseness thesis pipeline on the local machine,
independent of GitHub Actions.  Each step checks prerequisites, logs timing,
and supports granular skip flags for iterative development.

Usage examples:
    python run_pipeline.py                        # full pipeline, interactive
    python run_pipeline.py --non-interactive       # CI mode, never prompts
    python run_pipeline.py --skip-fem --skip-heeds # skip FEM + HEEDS
    python run_pipeline.py --from-step 5           # resume from feature extraction
    python run_pipeline.py --skip-reports           # everything except LLM reports

Requires:
    ANTHROPIC_API_KEY environment variable (for LLM report steps)
    Node.js on PATH (for final Word report)
    C:\\ProgramData\\anaconda3\\python.exe (Anaconda interpreter)
"""

import argparse
import os
import subprocess
import sys
import time
import shutil
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PYTHON = r"C:\ProgramData\anaconda3\python.exe"
NODE = "node"

DB_PATH = r"D:\thesis_database\thesis_results.db"
NPZ_PATH = r"D:\thesis_database\training_matrix.npz"
REPORTS_DIR = r"C:\Users\waynelee\Desktop\reports"
FEM_UTILITY_DIR = r"D:\thesis_database\fem_utility"

SCRIPTS_DIR = r"C:\Users\waynelee\Desktop\Scripts"
DB_SCRIPTS_DIR = r"C:\Users\waynelee\Desktop\heeds\database"
PIPELINE_DIR = r"C:\Users\waynelee\Desktop\pipeline"

# Study name used for report context
DEFAULT_STUDY = "study_A_single_bolt_sweep"

# LLM report types in chained order
REPORT_TYPES = [
    "fem_health",
    "study_plan",
    "heeds_status",
    "db_health",
    "psd_signatures",
    "feature_matrix",
    "classification",
    "executive_summary",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
_LOG_FILE = None


def log(msg, level="INFO"):
    """Print a timestamped log line. Always flushes."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    if _LOG_FILE:
        _LOG_FILE.write(line + "\n")
        _LOG_FILE.flush()


def log_separator(title):
    """Print a bold section separator."""
    bar = "=" * 70
    print("", flush=True)
    log(bar)
    log(f"  {title}")
    log(bar)


# ---------------------------------------------------------------------------
# Config loading (optional pipeline/config.yaml)
# ---------------------------------------------------------------------------
def load_config():
    """Load config.yaml if present, otherwise return empty dict."""
    config_path = os.path.join(PIPELINE_DIR, "config.yaml")
    if not os.path.isfile(config_path):
        return {}
    try:
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        log(f"Loaded config from {config_path}")
        return cfg
    except ImportError:
        log("PyYAML not installed -- skipping config.yaml", level="WARN")
        return {}
    except Exception as exc:
        log(f"Failed to parse config.yaml: {exc}", level="WARN")
        return {}


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------
def run_command(cmd, cwd=None, label="command"):
    """
    Run a subprocess with PYTHONUNBUFFERED=1.  Returns (returncode, elapsed_s).
    stdout/stderr are streamed to the console in real time.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    log(f"Running: {' '.join(cmd)}")
    if cwd:
        log(f"  cwd: {cwd}")

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            # Stream stdout/stderr directly to console
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode == 0:
            log(f"{label} completed successfully ({elapsed:.1f}s)")
        else:
            log(f"{label} FAILED with return code {proc.returncode} ({elapsed:.1f}s)",
                level="ERROR")
        return proc.returncode, elapsed

    except FileNotFoundError as exc:
        elapsed = time.perf_counter() - t0
        log(f"{label} FAILED -- executable not found: {exc}", level="ERROR")
        return 1, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        log(f"{label} FAILED -- {exc}", level="ERROR")
        return 1, elapsed


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
def check_python():
    """Verify the Anaconda interpreter exists."""
    if not os.path.isfile(PYTHON):
        log(f"Anaconda Python not found at {PYTHON}", level="ERROR")
        log("Install Anaconda or update PYTHON path in this script.", level="ERROR")
        return False
    return True


def check_node():
    """Verify Node.js is available on PATH."""
    if shutil.which(NODE) is None:
        log("Node.js not found on PATH", level="ERROR")
        log("Install Node.js or add it to PATH for the final report step.", level="ERROR")
        return False
    return True


def check_file_exists(path, description):
    """Return True if the file exists, otherwise log an error."""
    if os.path.isfile(path):
        log(f"Prerequisite OK: {description} -> {path}")
        return True
    log(f"Prerequisite MISSING: {description} -> {path}", level="ERROR")
    return False


def check_dir_exists(path, description):
    """Return True if the directory exists, otherwise log an error."""
    if os.path.isdir(path):
        log(f"Prerequisite OK: {description} -> {path}")
        return True
    log(f"Prerequisite MISSING: {description} -> {path}", level="ERROR")
    return False


# ---------------------------------------------------------------------------
# Decision helper for failures
# ---------------------------------------------------------------------------
def should_continue(step_name, interactive):
    """After a step fails, decide whether to continue or abort."""
    if not interactive:
        log(f"Non-interactive mode: continuing past failed step '{step_name}'",
            level="WARN")
        return True

    print(flush=True)
    while True:
        try:
            choice = input(
                f"Step '{step_name}' failed.  Continue to next step? [y/n]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(flush=True)
            return False
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("  Please enter 'y' or 'n'.", flush=True)


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def step_1_fem_utility(config):
    """Step 1: Run the Nastran FEM utility for model validation."""
    log_separator("STEP 1 / 8 -- FEM Utility (model validation)")

    script = os.path.join(PIPELINE_DIR, "run_nastran_utility.py")
    if not check_file_exists(script, "run_nastran_utility.py"):
        return 1

    cmd = [PYTHON, script]

    # Pass config.yaml if it exists
    config_yaml = os.path.join(PIPELINE_DIR, "config.yaml")
    if os.path.isfile(config_yaml):
        cmd += ["--config", config_yaml]

    # Must run from Desktop so templates/ is found relative to CWD
    desktop = os.path.dirname(PIPELINE_DIR)
    rc, _ = run_command(cmd, cwd=desktop, label="FEM Utility")
    return rc


def step_2_heeds(config):
    """Step 2: Run HEEDS study — mirrors super_workflow.yml stages 3-5.

    Sequence (same as GitHub workflow):
      1. generate_bat.py        → FBM_TO_DBALL.bat
      2. generate_baseline_bush.py → Misc/Bush.blk (Femap format)
      3. generate_heeds_project.py → heeds/projects/{study}.heeds
      4. Copy all files to HEEDS_WORKING_DIR
      5. Launch HEEDS MDO in batch mode (-b -script run_study_v2.py)
      6. Monitor POST_0 for completion ("End of HEEDS run" in Study_1.log)
    """
    log_separator("STEP 2 / 8 -- HEEDS Study")

    desktop = os.path.dirname(PIPELINE_DIR)

    # Read HEEDS paths from config (same values as GitHub repo variables)
    try:
        import yaml
        config_yaml = os.path.join(desktop, "fem_input", "config.yaml")
        with open(config_yaml) as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        log(f"Failed to read config.yaml: {e}", level="ERROR")
        return 1

    study_name = cfg.get('study', {}).get('name', 'study_A_single_bolt_sweep')
    expected_designs = int(cfg.get('study', {}).get('expected_designs', 73))
    heeds_mdo = cfg.get('paths', {}).get('heeds_mdo_path', r'C:\HEEDS\MDO\Ver2410\Python3\python.exe')
    heeds_working_dir = cfg.get('paths', {}).get('heeds_working_dir', r'C:\Users\waynelee\Documents')
    study_folder = os.path.join(heeds_working_dir, f"{study_name}_Study_1")
    post0_folder = os.path.join(study_folder, "POST_0")

    # --- Check if study already completed ---
    study_log = os.path.join(study_folder, "Study_1.log")
    if os.path.exists(study_log):
        with open(study_log, 'r', errors='ignore') as f:
            if "End of HEEDS run" in f.read():
                pch_count = len(list(Path(post0_folder).rglob("*.pch"))) if os.path.exists(post0_folder) else 0
                log(f"Previous HEEDS run completed ({pch_count} PCH files found)")
                log(f"Skipping HEEDS — using existing results in {post0_folder}")
                return 0

    # --- Stage 3a: Generate FBM_TO_DBALL.bat ---
    log("Generating FBM_TO_DBALL.bat...")
    rc, _ = run_command(
        [PYTHON, os.path.join(PIPELINE_DIR, "generate_bat.py"), "--output", "FBM_TO_DBALL.bat"],
        cwd=desktop, label="generate_bat.py")
    if rc != 0:
        return rc

    # --- Stage 3b: Generate baseline Bush.blk (Femap format) ---
    log("Generating baseline Bush.blk (Femap format)...")
    os.makedirs(os.path.join(desktop, "Misc"), exist_ok=True)
    rc, _ = run_command(
        [PYTHON, os.path.join(PIPELINE_DIR, "generate_baseline_bush.py"),
         "--output", "Misc/Bush.blk"],
        cwd=desktop, label="generate_baseline_bush.py")
    if rc != 0:
        return rc

    # --- Stage 3c: Generate HEEDS project file ---
    log(f"Generating HEEDS project: {study_name}.heeds...")
    os.makedirs(os.path.join(desktop, "heeds", "projects"), exist_ok=True)
    rc, _ = run_command(
        [PYTHON, os.path.join(PIPELINE_DIR, "generate_heeds_project.py"),
         "--output", f"heeds/projects/{study_name}.heeds"],
        cwd=desktop, label="generate_heeds_project.py")
    if rc != 0:
        return rc

    # --- Stage 4: Copy files to HEEDS working directory ---
    log(f"Copying files to HEEDS working dir: {heeds_working_dir}")
    heeds_file = os.path.join(desktop, "heeds", "projects", f"{study_name}.heeds")
    copies = [
        (heeds_file, f"{study_name}.heeds"),
        (os.path.join(desktop, "Misc", "Bush.blk"), "Bush.blk"),
        (os.path.join(desktop, "FBM_TO_DBALL.bat"), "FBM_TO_DBALL.bat"),
        (os.path.join(desktop, "templates", cfg['files'].get('structural_model', 'Fixed_base_beam.dat')),
         cfg['files'].get('structural_model', 'Fixed_base_beam.dat')),
        (os.path.join(desktop, "templates", "Recoveries.blk"), "Recoveries.blk"),
        (os.path.join(desktop, "templates", cfg['files'].get('random_response', 'RandomBeamX.dat')),
         cfg['files'].get('random_response', 'RandomBeamX.dat')),
        (os.path.join(desktop, "Scripts", cfg['files'].get('postprocessor', 'Pch_TO_CSV2.py')),
         cfg['files'].get('postprocessor', 'Pch_TO_CSV2.py')),
    ]
    # Optional baseline CSVs
    for csv in ["acceleration_results.csv", "displacement_results.csv"]:
        src = os.path.join(desktop, "baseline", csv)
        if os.path.exists(src):
            copies.append((src, csv.replace(".csv", "_baseline.csv")))

    for src, dst_name in copies:
        dst = os.path.join(heeds_working_dir, dst_name)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            log(f"  Copied: {dst_name}")
        else:
            log(f"  WARNING: Source not found: {src}", level="WARN")

    # --- Stage 5: Launch HEEDS ---
    run_script = os.path.join(desktop, "run_study_v2.py")
    heeds_project = os.path.join(heeds_working_dir, f"{study_name}.heeds")

    if not check_file_exists(run_script, "run_study_v2.py"):
        return 1
    if not check_file_exists(heeds_project, f"{study_name}.heeds"):
        return 1

    log(f"Launching HEEDS: {heeds_mdo} -b -script {run_script} -project {heeds_project}")
    import subprocess as sp
    proc = sp.Popen(
        [heeds_mdo, "-b", "-script", run_script, "-project", heeds_project],
        cwd=heeds_working_dir,
    )
    log(f"HEEDS started (PID: {proc.pid})")

    # --- Stage 6: Monitor for completion ---
    log(f"Monitoring POST_0 for {expected_designs} designs...")
    import time as _time
    t0 = _time.time()
    last_count = 0

    while True:
        _time.sleep(30)
        elapsed = _time.time() - t0

        # Primary completion signal: Study_1.log contains "End of HEEDS run"
        if os.path.exists(study_log):
            with open(study_log, 'r', errors='ignore') as f:
                if "End of HEEDS run" in f.read():
                    pch_count = len(list(Path(post0_folder).rglob("*.pch"))) if os.path.exists(post0_folder) else 0
                    log(f"HEEDS complete! {pch_count} PCH files in {elapsed/60:.1f} min")
                    break

        # Progress display (PCH count — informational only, NOT a gate)
        pch_count = len(list(Path(post0_folder).rglob("*.pch"))) if os.path.exists(post0_folder) else 0
        if pch_count != last_count:
            log(f"  [{int(elapsed)}s] {pch_count}/{expected_designs} designs complete")
            last_count = pch_count

        # Check if HEEDS process died unexpectedly
        if proc.poll() is not None:
            log(f"HEEDS process exited with code {proc.returncode}", level="ERROR")
            if pch_count > 0:
                log(f"  {pch_count} designs completed before exit — results may be usable")
            return 1 if pch_count == 0 else 0

    return 0


def step_3_import(config):
    """Step 3: Import PCH results into the SQLite database.

    Mirrors super_workflow.yml: batch_import_to_database.py --post0_dir POST_0
    """
    log_separator("STEP 3 / 8 -- Database Import (batch_import_to_database)")

    script = os.path.join(DB_SCRIPTS_DIR, "batch_import_to_database.py")
    if not check_file_exists(script, "batch_import_to_database.py"):
        return 1

    # Read HEEDS working dir from config (same location GitHub workflow uses)
    try:
        import yaml
        config_yaml = os.path.join(os.path.dirname(PIPELINE_DIR), "fem_input", "config.yaml")
        with open(config_yaml) as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}

    heeds_working_dir = cfg.get('paths', {}).get('heeds_working_dir', r'C:\Users\waynelee\Documents')
    study_name = cfg.get('study', {}).get('name', 'study_A_single_bolt_sweep')

    # Find POST_0 in the standard HEEDS output structure
    post0_dir = os.path.join(heeds_working_dir, f"{study_name}_Study_1", "POST_0")

    if not os.path.isdir(post0_dir):
        log(f"POST_0 not found: {post0_dir}", level="ERROR")
        log("Run HEEDS (step 2) first, or check HEEDS_WORKING_DIR in config.yaml")
        return 1

    pch_count = len(list(Path(post0_dir).rglob("*.pch")))
    log(f"Found POST_0 with {pch_count} PCH files: {post0_dir}")

    cmd = [
        PYTHON, script,
        "--post0_dir", post0_dir,
        "--study", study_name,
        "--db_path", DB_PATH,
        "--reset_study",  # clear old data before re-import (same as workflow)
    ]
    rc, _ = run_command(cmd, cwd=DB_SCRIPTS_DIR, label="Database Import")
    return rc


def step_4_miles(config):
    """Step 4: Compute Miles equation parameters."""
    log_separator("STEP 4 / 8 -- Miles Equation (compute_miles)")

    script = os.path.join(DB_SCRIPTS_DIR, "compute_miles.py")
    if not check_file_exists(script, "compute_miles.py"):
        return 1

    if not check_file_exists(DB_PATH, "thesis_results.db"):
        return 1

    cmd = [PYTHON, script, "--db_path", DB_PATH]
    rc, _ = run_command(cmd, cwd=DB_SCRIPTS_DIR, label="Miles Equation")
    return rc


def step_5_features(config):
    """Step 5: Extract ML features from the database."""
    log_separator("STEP 5 / 8 -- Feature Extraction (extract_features)")

    script = os.path.join(SCRIPTS_DIR, "extract_features.py")
    if not check_file_exists(script, "extract_features.py"):
        return 1

    if not check_file_exists(DB_PATH, "thesis_results.db"):
        return 1

    cmd = [
        PYTHON, script,
        "--db", DB_PATH,
        "--output", NPZ_PATH,
        "--noise-floor", "1e-5",
    ]
    rc, _ = run_command(cmd, cwd=SCRIPTS_DIR, label="Feature Extraction")
    return rc


def step_6_train(config):
    """Step 6: Train the bolt-looseness classifier."""
    log_separator("STEP 6 / 8 -- Train Classifier (train_classifier)")

    script = os.path.join(SCRIPTS_DIR, "train_classifier.py")
    if not check_file_exists(script, "train_classifier.py"):
        return 1

    if not check_file_exists(NPZ_PATH, "training_matrix.npz"):
        log("Feature matrix not found. Run step 5 first.", level="ERROR")
        return 1

    cmd = [PYTHON, script, "--input", NPZ_PATH]
    rc, _ = run_command(cmd, cwd=SCRIPTS_DIR, label="Train Classifier")
    return rc


def step_7_reports(config):
    """Step 7: Generate all 8 chained LLM pipeline reports."""
    log_separator("STEP 7 / 8 -- LLM Pipeline Reports (generate_pipeline_report)")

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("ANTHROPIC_API_KEY not set. LLM reports require an API key.", level="ERROR")
        return 1

    script = os.path.join(PIPELINE_DIR, "run_local_report.py")
    if not check_file_exists(script, "run_local_report.py"):
        return 1

    # Ensure output directory exists
    os.makedirs(REPORTS_DIR, exist_ok=True)

    failures = 0
    for i, report_type in enumerate(REPORT_TYPES, 1):
        log(f"  Report {i}/{len(REPORT_TYPES)}: {report_type}")

        cmd = [
            PYTHON, script,
            "--db_path", DB_PATH,
            "--study", DEFAULT_STUDY,
            "--report_type", report_type,
            "--output_dir", REPORTS_DIR,
        ]
        rc, _ = run_command(cmd, cwd=PIPELINE_DIR, label=f"Report: {report_type}")

        if rc != 0:
            log(f"Report '{report_type}' failed (rc={rc})", level="ERROR")
            failures += 1
            # Continue to next report -- partial reports are still useful

    if failures:
        log(f"{failures}/{len(REPORT_TYPES)} reports failed", level="WARN")
    return 1 if failures == len(REPORT_TYPES) else 0


def step_8_docx(config):
    """Step 8: Build the final consolidated Word report."""
    log_separator("STEP 8 / 8 -- Final Word Report (build_final_report.js)")

    script = os.path.join(PIPELINE_DIR, "build_final_report.js")
    if not check_file_exists(script, "build_final_report.js"):
        return 1

    if not check_node():
        return 1

    # Ensure node_modules are installed
    pkg_json = os.path.join(PIPELINE_DIR, "package.json")
    node_modules = os.path.join(PIPELINE_DIR, "node_modules")
    if os.path.isfile(pkg_json) and not os.path.isdir(node_modules):
        log("Installing Node.js dependencies (npm install)...")
        rc, _ = run_command(["npm", "install"], cwd=PIPELINE_DIR, label="npm install")
        if rc != 0:
            return rc

    cmd = [NODE, script]
    rc, _ = run_command(cmd, cwd=PIPELINE_DIR, label="Final Word Report")
    return rc


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------
STEPS = [
    # (step_num, name, function, skip_flag_attr)
    (1, "FEM Utility",          step_1_fem_utility,  "skip_fem"),
    (2, "HEEDS Studies",        step_2_heeds,        "skip_heeds"),
    (3, "Database Import",      step_3_import,       "skip_import"),
    (4, "Miles Equation",       step_4_miles,        "skip_import"),   # same flag as import
    (5, "Feature Extraction",   step_5_features,     "skip_ml"),
    (6, "Train Classifier",     step_6_train,        "skip_ml"),
    (7, "LLM Pipeline Reports", step_7_reports,      "skip_reports"),
    (8, "Final Word Report",    step_8_docx,         "skip_reports"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Run the complete bolt-looseness thesis pipeline end-to-end.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python run_pipeline.py                         # full interactive run\n"
            "  python run_pipeline.py --non-interactive        # CI mode\n"
            "  python run_pipeline.py --skip-fem --skip-heeds  # skip early steps\n"
            "  python run_pipeline.py --from-step 5            # resume from features\n"
        ),
    )
    parser.add_argument(
        "--skip-fem", action="store_true",
        help="Skip step 1 (FEM utility / Nastran validation)",
    )
    parser.add_argument(
        "--skip-heeds", action="store_true",
        help="Skip step 2 (HEEDS study execution)",
    )
    parser.add_argument(
        "--skip-import", action="store_true",
        help="Skip steps 3-4 (database import + Miles equation)",
    )
    parser.add_argument(
        "--skip-ml", action="store_true",
        help="Skip steps 5-6 (feature extraction + classifier training)",
    )
    parser.add_argument(
        "--skip-reports", action="store_true",
        help="Skip steps 7-8 (LLM reports + final Word document)",
    )
    parser.add_argument(
        "--from-step", type=int, default=1, metavar="N",
        help="Resume from step N (1-8). Steps before N are skipped.",
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Never prompt on failure -- continue to next step automatically.",
    )
    parser.add_argument(
        "--log-file", metavar="PATH",
        help="Write a copy of all log output to this file.",
    )
    parser.add_argument(
        "--chain", nargs="*", metavar="STUDY",
        help=(
            "Run multiple studies in sequence (A→B→C→D). "
            "FEM validation runs once, then HEEDS+import+ML repeats per study, "
            "reports run once at the end on the combined dataset.\n"
            "Presets: --chain all (runs A B C D)\n"
            "Custom:  --chain study_A_single_bolt_sweep study_B_two_bolt_sweep"
        ),
    )
    parser.add_argument(
        "--study", metavar="NAME",
        help="Override study name from config.yaml for a single run.",
    )

    args = parser.parse_args()
    interactive = not args.non_interactive

    # Validate --from-step
    if not 1 <= args.from_step <= 8:
        parser.error("--from-step must be between 1 and 8")

    # Open log file if requested
    global _LOG_FILE
    if args.log_file:
        os.makedirs(os.path.dirname(os.path.abspath(args.log_file)), exist_ok=True)
        _LOG_FILE = open(args.log_file, "a", encoding="utf-8")

    # --- Chain mode: run multiple studies sequentially ---
    if args.chain is not None:
        run_chain(args)
        return

    # --- Single study mode ---
    if args.study:
        _update_config_study_name(args.study)

    run_single(args)


# ---------------------------------------------------------------------------
# Study chain presets
# ---------------------------------------------------------------------------
CHAIN_PRESETS = {
    "all": [
        "study_A_single_bolt_sweep",
        "study_B_two_bolt_sweep",
        "study_C_three_bolt_sweep",
        "study_D_monte_carlo",
    ],
    "AB": [
        "study_A_single_bolt_sweep",
        "study_B_two_bolt_sweep",
    ],
    "ABC": [
        "study_A_single_bolt_sweep",
        "study_B_two_bolt_sweep",
        "study_C_three_bolt_sweep",
    ],
}

# Expected design counts for each study (for logging only)
STUDY_DESIGNS = {
    "study_A_single_bolt_sweep": 73,
    "study_B_two_bolt_sweep": 288,
    "study_C_three_bolt_sweep": 672,
    "study_D_monte_carlo": 501,
}


def _update_config_study_name(study_name):
    """Update study.name in config.yaml so downstream scripts pick it up."""
    config_path = os.path.join(os.path.dirname(PIPELINE_DIR), "fem_input", "config.yaml")
    if not os.path.isfile(config_path):
        log(f"config.yaml not found: {config_path}", level="WARN")
        return

    import re
    with open(config_path, 'r') as f:
        content = f.read()

    # Update study name
    content = re.sub(
        r'(name:\s*)(\S+)',
        rf'\g<1>{study_name}',
        content,
        count=1,
    )

    # Update expected_designs if known
    if study_name in STUDY_DESIGNS:
        content = re.sub(
            r'(expected_designs:\s*)\d+',
            rf'\g<1>{STUDY_DESIGNS[study_name]}',
            content,
            count=1,
        )

    # Update study type
    type_map = {
        "study_A_single_bolt_sweep": "single_bolt_sweep",
        "study_B_two_bolt_sweep": "two_bolt_sweep",
        "study_C_three_bolt_sweep": "three_bolt_sweep",
        "study_D_monte_carlo": "monte_carlo",
    }
    if study_name in type_map:
        content = re.sub(
            r'(type:\s*)(\S+)(.*# sweep)',
            rf'\g<1>{type_map[study_name]}\g<3>',
            content,
            count=1,
        )

    with open(config_path, 'w') as f:
        f.write(content)

    log(f"Updated config.yaml: study.name = {study_name}")


def run_chain(args):
    """Run multiple studies in sequence: FEM once → (HEEDS+import+ML) per study → reports once."""
    interactive = not args.non_interactive

    # Resolve study list
    studies = args.chain
    if not studies or studies == []:
        studies = CHAIN_PRESETS["all"]
    elif len(studies) == 1 and studies[0] in CHAIN_PRESETS:
        studies = CHAIN_PRESETS[studies[0]]

    log_separator("THESIS PIPELINE -- CHAINED STUDIES")
    log(f"Studies to run: {len(studies)}")
    for i, s in enumerate(studies, 1):
        designs = STUDY_DESIGNS.get(s, "?")
        log(f"  {i}. {s} ({designs} designs)")
    log(f"Mode: {'non-interactive' if not interactive else 'interactive'}")
    print("", flush=True)

    if not check_python():
        log("Aborting -- Anaconda Python not available.", level="FATAL")
        sys.exit(1)

    config = load_config()
    t_chain_start = time.perf_counter()
    chain_results = {}  # study_name -> {step: rc}

    # --- Step 1: FEM Utility (once) ---
    if not getattr(args, 'skip_fem', False) and args.from_step <= 1:
        rc = step_1_fem_utility(config)
        if rc != 0 and not should_continue("FEM Utility", interactive):
            sys.exit(1)
    else:
        log("Step 1 (FEM Utility): SKIPPED")

    # --- For each study: HEEDS → Import → Miles → Features → Train ---
    for study_idx, study_name in enumerate(studies, 1):
        log_separator(f"STUDY {study_idx}/{len(studies)}: {study_name}")

        # Update config.yaml for this study
        _update_config_study_name(study_name)
        config = load_config()  # reload

        study_results = {}

        # Steps 2-6 per study
        per_study_steps = [
            (2, "HEEDS",             step_2_heeds,    "skip_heeds"),
            (3, "Database Import",   step_3_import,   "skip_import"),
            (4, "Miles Equation",    step_4_miles,    "skip_import"),
            (5, "Feature Extraction", step_5_features, "skip_ml"),
            (6, "Train Classifier",  step_6_train,    "skip_ml"),
        ]

        for step_num, name, func, skip_attr in per_study_steps:
            if step_num < args.from_step:
                study_results[step_num] = "skipped"
                continue
            if getattr(args, skip_attr, False):
                study_results[step_num] = "skipped"
                continue

            rc = func(config)
            study_results[step_num] = rc

            if rc != 0:
                log(f"{study_name} / {name} FAILED (rc={rc})", level="ERROR")
                if not should_continue(f"{study_name}/{name}", interactive):
                    log("Aborting chain.", level="FATAL")
                    sys.exit(1)
                break  # skip remaining steps for this study

        chain_results[study_name] = study_results

    # --- Steps 7-8: Reports (once, on combined dataset) ---
    if not getattr(args, 'skip_reports', False):
        log_separator("FINAL REPORTS (combined dataset)")
        step_7_reports(config)
        step_8_docx(config)
    else:
        log("Steps 7-8 (Reports): SKIPPED")

    # --- Chain Summary ---
    elapsed = time.perf_counter() - t_chain_start
    log_separator("CHAIN SUMMARY")
    for study_name, results in chain_results.items():
        failures = sum(1 for rc in results.values() if rc not in (0, "skipped"))
        status = "OK" if failures == 0 else f"{failures} FAILURE(S)"
        log(f"  {study_name:45s} {status}")
    log(f"Total elapsed: {elapsed:.0f}s ({elapsed/60:.1f} min, {elapsed/3600:.1f} hr)")

    total_failures = sum(
        1 for r in chain_results.values()
        for rc in r.values() if rc not in (0, "skipped")
    )
    if total_failures:
        log(f"Chain finished with {total_failures} failure(s).", level="WARN")
        sys.exit(1)
    else:
        log("Chain finished successfully — all studies complete.")
        sys.exit(0)


def run_single(args):
    """Run a single study through all 8 steps (original behavior)."""
    interactive = not args.non_interactive

    # Load optional config
    config = load_config()

    # Banner
    log_separator("THESIS PIPELINE -- LOCAL ORCHESTRATOR")
    log(f"Python:   {PYTHON}")
    log(f"Node:     {shutil.which(NODE) or 'NOT FOUND'}")
    log(f"Database: {DB_PATH}")
    log(f"NPZ:     {NPZ_PATH}")
    log(f"Reports:  {REPORTS_DIR}")
    log(f"Mode:     {'non-interactive' if not interactive else 'interactive'}")
    if args.from_step > 1:
        log(f"Resuming from step {args.from_step}")
    print("", flush=True)

    # Pre-flight: verify Python exists
    if not check_python():
        log("Aborting -- Anaconda Python not available.", level="FATAL")
        sys.exit(1)

    # Run steps
    t_pipeline = time.perf_counter()
    results = {}  # step_num -> (name, rc)

    for step_num, name, func, skip_attr in STEPS:
        # Skip if before --from-step
        if step_num < args.from_step:
            log(f"Step {step_num} ({name}): SKIPPED (--from-step {args.from_step})")
            results[step_num] = (name, "skipped")
            continue

        # Skip if flag is set
        if getattr(args, skip_attr, False):
            log(f"Step {step_num} ({name}): SKIPPED (--{skip_attr.replace('_', '-')})")
            results[step_num] = (name, "skipped")
            continue

        # Execute
        rc = func(config)
        results[step_num] = (name, rc)

        if rc != 0:
            if not should_continue(name, interactive):
                log(f"Aborting pipeline at step {step_num}.", level="FATAL")
                break

    # Summary
    elapsed_total = time.perf_counter() - t_pipeline
    log_separator("PIPELINE SUMMARY")

    for step_num in sorted(results):
        name, rc = results[step_num]
        if rc == "skipped":
            status = "SKIPPED"
        elif rc == 0:
            status = "OK"
        else:
            status = f"FAILED (rc={rc})"
        log(f"  Step {step_num}: {name:30s} {status}")

    log(f"Total elapsed time: {elapsed_total:.1f}s "
        f"({elapsed_total / 60:.1f} min)")

    # Exit code: 0 if all executed steps passed, 1 otherwise
    failed = [n for n, (_, rc) in results.items() if rc not in (0, "skipped")]
    if failed:
        log(f"Pipeline finished with {len(failed)} failure(s).", level="WARN")
        sys.exit(1)
    else:
        log("Pipeline finished successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
