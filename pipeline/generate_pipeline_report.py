"""
Generate LLM-powered pipeline reports at each stage of the super workflow.

Each report uses the same grounded system prompt pattern: analyze ONLY the
provided data, no outside knowledge, temperature=0.

CHAINED AGENTS: Each report automatically reads the previous report's output
so each agent builds on the findings of the prior step. The first agent also
checks for the latest nastran utility simulation report if available.

Usage:
    python pipeline/generate_pipeline_report.py --report-type fem_health --data-file <path> --output-dir <path>
    python pipeline/generate_pipeline_report.py --report-type db_health --db-path <path> --output-dir <path>

Report types:
    1. fem_health        — Pre-run FEM health check (reads DAT file + latest nastran utility report)
    2. study_plan        — Study plan summary (reads config + .heeds file + Report 1)
    3. heeds_status      — HEEDS run status (reads study log + Report 2)
    4. db_health         — Database health (queries SQLite + CBUSH forces + Report 3)
    5. feature_matrix    — Feature matrix report (reads training_matrix.npz + Report 4)
    6. classification    — Classification results (reads classification_report.txt + Report 5)
    7. executive_summary — Pipeline executive summary (reads all prior reports)

Requires:
    ANTHROPIC_API_KEY environment variable
    pip install anthropic
"""

import sys
import os
import argparse
import json
import glob as globmod
from datetime import datetime


SYSTEM_PROMPT = (
    "You are a structural engineering pipeline analyst. Analyze ONLY the data "
    "provided to you in this message. Do not use any outside knowledge about "
    "Nastran, spacecraft, structural analysis, or machine learning. If the data "
    "does not support a conclusion, say so explicitly. Never invent numbers, "
    "results, or conclusions not present in the provided data.\n\n"
    "FORMATTING RULES:\n"
    "- Use ## for section headings (never ### or deeper)\n"
    "- Use bullet lists and tables for data presentation\n"
    "- Bold key findings and verdicts\n"
    "- Keep engineering language precise and grounded in the data"
)

# Report ordering for chaining — maps each report to the one before it
REPORT_ORDER = [
    "fem_health",        # 01 — no prior report, but checks nastran utility report
    "study_plan",        # 02 — reads 01
    "heeds_status",      # 03 — reads 02
    "db_health",         # 04 — reads 03
    "psd_signatures",    # 05 — reads 04 — actual PSD curves and signature analysis
    "feature_matrix",    # 06 — reads 05
    "classification",    # 07 — reads 06
    "executive_summary", # 08 — reads all 01-07
]

REPORT_CONFIGS = {
    "fem_health": {
        "title": "Pre-Run FEM Health Check",
        "filename": "01_fem_health.md",
        "prompt": (
            "Analyze this Nastran FEM input deck and produce a health check report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Expected Input Files\n"
            "This is a CBUSH bolt looseness parametric study. The following files are "
            "REQUIRED for the pipeline to function. For each file listed in the "
            "'Expected files' data section below, report whether it was FOUND or MISSING. "
            "Explain the role of each file:\n"
            "- Structural model (.dat) — main Nastran input deck (SOL 103 modal analysis)\n"
            "- Random response deck (.dat) — SOL 111 frequency response input\n"
            "- Bush template (.blk) — CBUSH/PBUSH property definitions (INCLUDE'd by the DAT). "
            "This is the file that HEEDS modifies per design to sweep bolt stiffness.\n"
            "- Recoveries (.blk) — XYPUNCH output recovery directives\n"
            "Flag any missing files as CRITICAL — the study cannot proceed without them.\n\n"
            "## Model Overview\n"
            "- Solution type (SOL card), element count by type, node count\n"
            "- Subcases defined and their load/BC references\n\n"
            "## CBUSH Bolt Elements — Detailed Analysis\n"
            "- Total CBUSH element count and their element IDs\n"
            "- PBUSH property cards — list each PID with K1-K6 stiffness values\n"
            "- Which CBUSH elements connect which grids (GA, GB)\n"
            "- Coordinate systems referenced (CID, OCID)\n"
            "- Flag any CBUSH with zero or missing stiffness components\n\n"
            "## Boundary Conditions\n"
            "- SPC cards — which grids, which DOFs constrained\n"
            "- SPC sets referenced by subcases\n\n"
            "## Include Files\n"
            "- All INCLUDE cards and referenced filenames\n"
            "- Cross-reference: do the INCLUDE filenames match the expected files above?\n\n"
            "## Potential Issues\n"
            "- Missing cards, orphan references, suspicious values\n"
            "- Any CBUSH elements with incomplete property definitions\n\n"
            "## Health Verdict\n"
            "- Is this FEM ready to run? Summarize pass/fail items.\n\n"
            "If a previous nastran utility simulation report is provided below, "
            "reference its findings (modal results, warnings, CBUSH forces) to "
            "inform your assessment of whether this FEM configuration is sound.\n\n"
        ),
    },
    "study_plan": {
        "title": "Study Plan Summary",
        "filename": "02_study_plan.md",
        "prompt": (
            "Analyze this study configuration and HEEDS project file. Produce a study plan summary.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Study Overview\n"
            "- Study name, type, and objective\n\n"
            "## Design Variables\n"
            "- Which bolt CBUSH elements are being swept\n"
            "- Stiffness range (min, max, number of levels)\n"
            "- How the sweep maps to physical bolt looseness states\n\n"
            "## Expected Designs\n"
            "- Total design count and how it was computed\n\n"
            "## Response Variables\n"
            "- What outputs are being tracked (accelerations, forces, etc.)\n\n"
            "## Solver Chain\n"
            "- Nastran solution sequence and post-processing steps\n\n"
            "## Assessment\n"
            "- Is the study plan well-configured? Any gaps?\n\n"
            "IMPORTANT: A previous pipeline report (FEM Health Check) is included below. "
            "Reference its findings — if it flagged CBUSH issues or missing cards, note "
            "whether the study plan accounts for them.\n\n"
        ),
    },
    "heeds_status": {
        "title": "HEEDS Run Status Report",
        "filename": "03_heeds_status.md",
        "prompt": (
            "Analyze this HEEDS study run data and produce a status report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Completion Status\n"
            "- Designs completed vs expected\n"
            "- Per-design verification — which have PCH and CSV output files\n\n"
            "## Timing Analysis\n"
            "- Total elapsed time\n"
            "- Per-design average runtime\n"
            "- Any designs that took unusually long\n\n"
            "## Warnings and Failures\n"
            "- Any failures or warnings from the study log\n"
            "- Nastran fatal/warning messages if present\n\n"
            "## Assessment\n"
            "- Did the study complete successfully?\n"
            "- Is the data ready for database import?\n\n"
            "IMPORTANT: A previous pipeline report (Study Plan Summary) is included below. "
            "Cross-reference: does the completed design count match what was planned? "
            "Were the expected response variables actually generated?\n\n"
        ),
    },
    "db_health": {
        "title": "Database Health Report",
        "filename": "04_db_health.md",
        "prompt": (
            "Analyze this database health data and produce a report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Database Overview\n"
            "- Table row counts and database file size\n\n"
            "## Study and Case Summary\n"
            "- Study metadata and case listing\n\n"
            "## PSD Data Coverage\n"
            "- Rows per case, any gaps or missing cases\n"
            "- Frequency range and point count consistency\n"
            "- NOTE: Small variations in PSD row counts between designs are normal — "
            "Nastran SOL 111 adaptively inserts extra frequency points near resonance "
            "peaks, so designs with different stiffness values (and therefore shifted "
            "resonances) may have slightly different frequency grids. Only flag row "
            "count differences as a problem if they exceed ~10% of the row count.\n\n"
            "## CBUSH Force Data\n"
            "- If CBUSH element force data is present, summarize:\n"
            "  - Which element IDs have force data\n"
            "  - Force components available (axial, shear, moment)\n"
            "  - Baseline vs swept case force comparison\n"
            "  - Amplification ratios (swept / baseline) for key force components\n\n"
            "## Parameter Distribution\n"
            "- K4 stiffness values across cases\n"
            "- Stiffness sweep range and step pattern\n\n"
            "## Baseline Status\n"
            "- Is baseline case present and complete?\n\n"
            "## Assessment\n"
            "- Is the database healthy and complete?\n"
            "- Data quality rating\n\n"
            "IMPORTANT: A previous pipeline report (HEEDS Run Status) is included below. "
            "Cross-reference: does the database case count match the verified design count "
            "from the HEEDS run? Any designs that completed but failed to import?\n\n"
        ),
    },
    "psd_signatures": {
        "title": "PSD Signature Analysis",
        "filename": "05_psd_signatures.md",
        "prompt": (
            "Analyze this PSD (Power Spectral Density) signature data from a bolt looseness "
            "study and produce a detailed engineering report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Study Overview\n"
            "- Study name, type, number of cases\n"
            "- Which bolt(s) were swept and over what stiffness range\n\n"
            "## Baseline Signature\n"
            "- List the baseline peak frequencies and amplitudes per channel (node/DOF)\n"
            "- What are the dominant resonance frequencies of this structure?\n\n"
            "## Frequency Shift with Bolt Looseness\n"
            "- Do resonant frequencies shift as bolt stiffness decreases?\n"
            "- At what stiffness level does the first detectable frequency shift appear?\n"
            "- Is the shift monotonic (consistently drops/rises with looseness) or non-linear?\n"
            "- Which channels (nodes/DOFs) show the largest frequency shifts?\n\n"
            "## Amplitude Change with Bolt Looseness\n"
            "- How does PSD amplitude change as bolts loosen?\n"
            "- What is the amplification ratio at the lowest stiffness vs baseline?\n"
            "- Which channels amplify the most?\n"
            "- Is there a stiffness threshold below which amplitude changes become large?\n\n"
            "## Most Sensitive Channels\n"
            "- Rank the top channels by sensitivity to bolt looseness\n"
            "- Physical interpretation: what do these nodes/DOFs represent structurally?\n\n"
            "## Distinguishability\n"
            "- Can different stiffness levels be distinguished from each other based on PSD shape?\n"
            "- Are there clear spectral fingerprints for different looseness severities?\n"
            "- If multiple bolts are loose (Study B+): does the signature differ from single-bolt looseness?\n\n"
            "## Assessment\n"
            "- Overall: are the PSD signatures physically meaningful and separable?\n"
            "- What features in the PSD data would be most useful for ML classification?\n"
            "- Any anomalies or unexpected behaviors in the data?\n\n"
            "IMPORTANT: A previous pipeline report (Database Health) is included below. "
            "Cross-reference: does the case count match, and are there any data gaps that "
            "affect the signature analysis?\n\n"
        ),
    },
    "feature_matrix": {
        "title": "Feature Matrix Report",
        "filename": "06_feature_matrix.md",
        "prompt": (
            "Analyze this feature extraction data and produce a report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Matrix Dimensions\n"
            "- Samples count, feature count\n"
            "- Samples-to-features ratio (is there enough data?)\n\n"
            "## Feature Types\n"
            "- Peak features — which response quantities\n"
            "- Spectral features — frequency-domain characteristics\n"
            "- Delta features — changes from baseline\n"
            "- CBUSH-related features if present\n\n"
            "## Label Distribution\n"
            "- Samples per class\n"
            "- Class balance assessment\n\n"
            "## Data Quality\n"
            "- NaN or infinite values\n"
            "- Feature statistics — mean, std, min, max ranges\n"
            "- Any features with zero variance (uninformative)\n\n"
            "## Assessment\n"
            "- Is this feature matrix ready for ML training?\n"
            "- Recommendations for feature engineering\n\n"
            "IMPORTANT: A previous pipeline report (Database Health) is included below. "
            "Cross-reference: does the sample count match the database case count? "
            "If the DB report noted any data gaps, are they reflected in the features?\n\n"
        ),
    },
    "classification": {
        "title": "Classification Report",
        "filename": "07_classification.md",
        "prompt": (
            "Analyze this ML classification data and produce a report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Model Summary\n"
            "- Model type and key hyperparameters\n\n"
            "## Performance Metrics\n"
            "- Accuracy, precision, recall, F1 per class\n"
            "- Overall accuracy and macro/weighted averages\n\n"
            "## Confusion Matrix\n"
            "- Interpret the confusion matrix — which classes are confused\n"
            "- False positive / false negative analysis\n\n"
            "## Feature Importance\n"
            "- Top 10 most important features\n"
            "- Physical interpretation — what do the top features represent\n"
            "- Are CBUSH-related features among the top predictors?\n\n"
            "## Cross-Validation\n"
            "- CV results if present, stability across folds\n\n"
            "## Assessment\n"
            "- Is this classifier reliable for bolt looseness detection?\n"
            "- What would improve performance (more data, features, tuning)?\n\n"
            "IMPORTANT: A previous pipeline report (Feature Matrix) is included below. "
            "Cross-reference: were there data quality issues in the features that may "
            "explain classification performance? Is class imbalance affecting results?\n\n"
        ),
    },
    "executive_summary": {
        "title": "Pipeline Executive Summary",
        "filename": "08_executive_summary.md",
        "prompt": (
            "Analyze all previous pipeline stage reports and produce an executive summary.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
            "## Pipeline Status Overview\n"
            "- Which stages completed successfully, which had issues\n"
            "- Overall pipeline health: PASS / PARTIAL / FAIL\n\n"
            "## Key Findings Chain\n"
            "For each stage, extract the single most important finding and show how "
            "it flows into the next stage:\n"
            "- FEM Health -> Study Plan -> HEEDS Run -> Database -> Features -> Classifier\n\n"
            "## CBUSH Bolt Looseness Detection — End-to-End Assessment\n"
            "- From FEM bolt configuration through ML classification\n"
            "- Amplification ratios observed (if reported in DB health)\n"
            "- Classifier ability to distinguish looseness states\n\n"
            "## Data Quality Assessment\n"
            "- FEM model quality\n"
            "- Database completeness\n"
            "- Feature matrix readiness\n"
            "- Classifier reliability\n\n"
            "## Recommendations\n"
            "- What should be done next\n"
            "- Priority items for improving the pipeline\n\n"
            "## Confidence Assessment\n"
            "- How trustworthy are the end-to-end results?\n\n"
        ),
    },
}


def call_anthropic(system_prompt, user_prompt, max_retries=3):
    """Call Anthropic API with grounded prompt and retry logic."""
    import time

    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return message.content[0].text
        except anthropic.RateLimitError as e:
            print(f"RETRY {attempt}/{max_retries}: Rate limited — {e}")
            if attempt < max_retries:
                wait = 2 ** attempt * 5
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)
        except anthropic.APIStatusError as e:
            print(f"RETRY {attempt}/{max_retries}: API error {e.status_code} — {e.message}")
            if attempt < max_retries and e.status_code >= 500:
                wait = 2 ** attempt * 5
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)
            else:
                print(f"FATAL: Non-retryable API error: {e}")
                sys.exit(1)
        except anthropic.APIConnectionError as e:
            print(f"RETRY {attempt}/{max_retries}: Connection error — {e}")
            if attempt < max_retries:
                wait = 2 ** attempt * 5
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)
        except Exception as e:
            print(f"FATAL: Unexpected error calling Anthropic API: {type(e).__name__}: {e}")
            sys.exit(1)

    print(f"FATAL: All {max_retries} API attempts failed")
    sys.exit(1)


def find_latest_nastran_utility_report():
    """Find the most recent simulation_report.md.

    Checks two locations in order:
    1. Stable published path: D:\\thesis_database\\fem_utility\\simulation_report.md
       (auto-populated by run_nastran_utility.py after every FEM run)
    2. Fallback: timestamped folders in Documents\\FEM_Utility\\
    """
    # 1. Check stable path first (always preferred — most recent published run)
    stable_path = os.path.join(r'D:\thesis_database', 'fem_utility', 'simulation_report.md')
    if os.path.exists(stable_path):
        return stable_path

    # 2. Fallback: search timestamped folders
    fem_utility_base = os.path.join(
        os.environ.get('USERPROFILE', r'C:\Users\waynelee'),
        'Documents', 'FEM_Utility'
    )
    if not os.path.exists(fem_utility_base):
        return None

    report_files = globmod.glob(
        os.path.join(fem_utility_base, '*', 'simulation_report.md')
    )
    if not report_files:
        return None

    latest = max(report_files, key=os.path.getmtime)
    return latest


def get_fem_utility_context():
    """Load the FEM utility report as shared context for ALL downstream LLM reports.

    This gives every report access to the baseline model properties:
    natural frequencies, mode shapes, CBUSH stiffness, force data, etc.
    Returns a formatted string, or empty string if not available.
    """
    report_path = find_latest_nastran_utility_report()
    if not report_path:
        print("Note: No FEM utility report found — downstream reports will lack model context")
        return ""

    with open(report_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    if len(content.strip()) < 100:
        return ""

    print(f"Injecting FEM utility context ({len(content):,} chars) from {report_path}")
    return (
        "\n\n=== FEM Utility Baseline Report (Model Properties & Modal Analysis) ===\n"
        "This is the Nastran FEM baseline analysis. Use this data to understand "
        "the model structure, natural frequencies, mode shapes, CBUSH stiffness values, "
        "and bolt force data. All other pipeline results build on this foundation.\n\n"
        + content
    )


def get_previous_report(output_dir, report_type):
    """Read the previous stage's report from output_dir for chaining.

    Each agent reads the report from the step before it to build context.
    """
    idx = REPORT_ORDER.index(report_type) if report_type in REPORT_ORDER else -1
    if idx <= 0:
        return None  # fem_health has no prior report (uses nastran utility instead)

    prev_type = REPORT_ORDER[idx - 1]
    prev_cfg = REPORT_CONFIGS[prev_type]
    prev_path = os.path.join(output_dir, prev_cfg["filename"])

    if os.path.exists(prev_path):
        with open(prev_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Validate: skip if report is too short, empty, or looks like an error
        if len(content.strip()) < 100:
            print(f"Note: previous report {prev_cfg['filename']} is too short ({len(content)} chars) — skipping chain")
            return None
        error_markers = ["FATAL:", "Traceback", "ERROR:", "report failed", "No data", "not found"]
        # Only skip if the ENTIRE report is an error (not just mentions one)
        first_500 = content[:500].lower()
        if any(marker.lower() in first_500 for marker in error_markers) and len(content) < 500:
            print(f"Note: previous report {prev_cfg['filename']} appears to be an error — skipping chain")
            return None

        print(f"Chained context: reading previous report {prev_cfg['filename']}")
        return f"=== Previous Pipeline Report: {prev_cfg['title']} ===\n{content}"

    print(f"Note: previous report {prev_cfg['filename']} not found (skipping chain)")
    return None


def gather_data_fem_health(data_file, config_file=None):
    """Read DAT file for FEM health check + latest nastran utility report + expected files check."""
    parts = []
    with open(data_file, "r", errors="ignore") as f:
        parts.append("=== FEM Input Deck ===\n" + f.read()[:60000])

    # Load config.yaml to determine expected input files
    expected_files = _check_expected_files(data_file, config_file)
    if expected_files:
        parts.append("=== Expected Files ===\n" + expected_files)

    # Check for latest nastran utility simulation report
    nastran_report = find_latest_nastran_utility_report()
    if nastran_report:
        mtime = datetime.fromtimestamp(os.path.getmtime(nastran_report))
        print(f"Found nastran utility report: {nastran_report} (modified: {mtime})")
        with open(nastran_report, "r", encoding="utf-8") as f:
            report_content = f.read()[:20000]
        parts.append(
            f"=== Latest Nastran Utility Report (from {mtime.strftime('%Y-%m-%d %H:%M')}) ===\n"
            + report_content
        )
    else:
        print("No previous nastran utility report found (skipping)")

    return "\n\n".join(parts)


def _check_expected_files(data_file, config_file=None):
    """Check that all expected input files exist for a bolt looseness study.

    Reads config.yaml to get the file list, then verifies each on disk.
    Falls back to well-known defaults if config.yaml is not available.
    """
    # Try to find config.yaml: explicit arg > fem_input/config.yaml > same dir as data_file
    config_path = None
    if config_file and os.path.exists(config_file):
        config_path = config_file
    else:
        # Look relative to repo root (Desktop)
        candidates = [
            os.path.join(os.path.dirname(data_file), "config.yaml"),
            os.path.join(os.path.dirname(os.path.dirname(data_file)), "fem_input", "config.yaml"),
        ]
        for c in candidates:
            if os.path.exists(c):
                config_path = c
                break

    # Define expected files with roles
    file_checks = {
        "structural_model": {
            "role": "Main Nastran input deck (SOL 103 modal analysis)",
            "default": "Fixed_base_beam.dat",
        },
        "random_response": {
            "role": "SOL 111 random response deck",
            "default": "RandomBeamX.dat",
        },
        "bush_template": {
            "role": "CBUSH/PBUSH property block (swept by HEEDS per design)",
            "default": "Bush.blk",
        },
        "recoveries": {
            "role": "XYPUNCH output recovery directives",
            "default": "Recoveries.blk",
        },
    }

    # Read filenames from config if available
    fem_input_dir = os.path.dirname(data_file)
    if config_path:
        try:
            import yaml
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f)
            files_cfg = cfg.get("files", {})
            for key in file_checks:
                if key in files_cfg:
                    file_checks[key]["filename"] = files_cfg[key]
            # Use fem_input_dir from config if specified
            if "fem_input_dir" in files_cfg:
                repo_root = os.path.dirname(config_path)
                if os.path.basename(repo_root) == "fem_input":
                    repo_root = os.path.dirname(repo_root)
                candidate_dir = os.path.join(repo_root, files_cfg["fem_input_dir"])
                if os.path.isdir(candidate_dir):
                    fem_input_dir = candidate_dir
        except Exception as e:
            print(f"Warning: could not parse config.yaml for expected files: {e}")

    # Check each file
    lines = []
    for key, info in file_checks.items():
        filename = info.get("filename", info["default"])
        filepath = os.path.join(fem_input_dir, filename)
        exists = os.path.exists(filepath)
        status = "FOUND" if exists else "MISSING"
        size_str = ""
        if exists:
            size_bytes = os.path.getsize(filepath)
            size_str = f" ({size_bytes:,} bytes)"
        lines.append(f"{key}: {filename} — {status}{size_str}")
        lines.append(f"  Role: {info['role']}")
        lines.append(f"  Path checked: {filepath}")

    if config_path:
        lines.insert(0, f"Config source: {config_path}")
    else:
        lines.insert(0, "Config source: defaults (config.yaml not found)")

    return "\n".join(lines)


def gather_data_study_plan(data_file, config_file=None):
    """Read config.yaml and .heeds file."""
    parts = []
    if config_file and os.path.exists(config_file):
        with open(config_file, "r") as f:
            parts.append("=== config.yaml ===\n" + f.read())
    if os.path.exists(data_file):
        with open(data_file, "r", errors="ignore") as f:
            content = f.read()
            # Truncate large heeds XML
            parts.append("=== HEEDS Project File ===\n" + content[:40000])
    return "\n\n".join(parts)


def gather_data_heeds_status(data_file):
    """Read study log and design verification data."""
    parts = []
    if os.path.exists(data_file):
        with open(data_file, "r", errors="ignore") as f:
            parts.append("=== Study Log ===\n" + f.read()[:30000])
    return "\n\n".join(parts) if parts else "No study log data available."


def gather_data_db_health(db_path):
    """Query database for health stats including CBUSH force data."""
    import sqlite3

    if not os.path.exists(db_path):
        return "Database not found: " + db_path

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    lines = []

    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    lines.append(f"Database: {db_path}")
    lines.append(f"Size: {size_mb:.2f} MB")

    for table in ["studies", "cases", "psd_data", "peaks", "parameters", "miles"]:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            lines.append(f"{table}: {cursor.fetchone()[0]} rows")
        except Exception:
            lines.append(f"{table}: table not found")

    try:
        cursor.execute("SELECT study_name, study_type, num_cases, status FROM studies")
        for row in cursor.fetchall():
            lines.append(f"  Study: {row[0]} ({row[1]}, {row[2]} cases, {row[3]})")
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT c.case_name, c.case_number, c.is_baseline, COUNT(p.id) "
            "FROM cases c LEFT JOIN psd_data p ON c.case_id = p.case_id "
            "GROUP BY c.case_id ORDER BY c.case_number"
        )
        rows_per_case = cursor.fetchall()
        lines.append(f"\nPer-case PSD row counts ({len(rows_per_case)} cases):")
        row_counts = []
        # Show first 20 and last 5 cases as sample, summarize the rest
        sample_rows = rows_per_case[:20] + rows_per_case[-5:] if len(rows_per_case) > 25 else rows_per_case
        for row in sample_rows:
            bl = " [BASELINE]" if row[2] else ""
            lines.append(f"  Case {row[1]} ({row[0]}): {row[3]} PSD rows{bl}")
        if len(rows_per_case) > 25:
            lines.append(f"  ... ({len(rows_per_case) - 25} more cases omitted for brevity)")
        for row in rows_per_case:
            row_counts.append(row[3])

        # Flag row count variation with context
        if row_counts and len(set(row_counts)) > 1:
            min_rc, max_rc = min(row_counts), max(row_counts)
            delta = max_rc - min_rc
            lines.append(f"\n  NOTE: PSD row counts vary ({min_rc:,} to {max_rc:,}, delta={delta}).")
            lines.append(
                "  This is EXPECTED Nastran SOL 111 behavior — the solver adaptively inserts "
                "extra frequency points near resonance peaks, so designs with shifted resonances "
                "may have slightly different frequency grids. This is NOT a data integrity issue "
                "unless the delta is very large (>10% of the row count)."
            )
            pct = (delta / min_rc * 100) if min_rc > 0 else 0
            lines.append(f"  Variation: {pct:.2f}% of minimum row count.")
            if pct > 10:
                lines.append("  WARNING: Variation exceeds 10% — investigate for possible solver issues.")
        else:
            lines.append("  All cases have identical PSD row counts.")
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT c.case_name, p.element_id, p.K4, p.K5, p.K6 "
            "FROM parameters p JOIN cases c ON p.case_id = c.case_id "
            "ORDER BY c.case_number, p.element_id"
        )
        rows = cursor.fetchall()
        if rows:
            lines.append(f"\nStiffness values per case (K4, K5, K6) — {len(rows)} total rows:")
            # Show first 30 and last 10 rows as sample
            sample = rows[:30] + rows[-10:] if len(rows) > 40 else rows
            for row in sample:
                lines.append(
                    f"  {row[0]}: element {row[1]}, "
                    f"K4={row[2]:.3e}, K5={row[3]:.3e}, K6={row[4]:.3e}"
                )
            if len(rows) > 40:
                lines.append(f"  ... ({len(rows) - 40} more rows omitted for brevity)")
    except Exception:
        pass

    # PSD peaks data — node-level response peaks from peaks table
    try:
        cursor.execute(
            "SELECT c.case_name, c.case_number, c.is_baseline, "
            "pk.node_id, pk.dof, pk.data_type, pk.area, "
            "pk.peak1_freq, pk.peak1_psd, pk.peak2_freq, pk.peak2_psd, "
            "pk.peak3_freq, pk.peak3_psd "
            "FROM peaks pk JOIN cases c ON pk.case_id = c.case_id "
            "ORDER BY c.case_number, pk.node_id, pk.dof"
        )
        peak_rows = cursor.fetchall()
        if peak_rows:
            lines.append(f"\nPSD response peaks ({len(peak_rows)} total rows):")
            for row in peak_rows[:80]:  # Cap display at 80 rows
                bl = " [BASELINE]" if row[2] else ""
                lines.append(
                    f"  Case {row[1]} ({row[0]}){bl}: node {row[3]}, "
                    f"dof={row[4]}, type={row[5]}, area={row[6]:.6e}, "
                    f"pk1={row[8]:.6e}@{row[7]:.2f}Hz" if row[7] is not None and row[8] is not None else f"pk1=N/A"
                )
            if len(peak_rows) > 80:
                lines.append(f"  ... and {len(peak_rows) - 80} more rows")

            # Compute amplification ratios: swept area / baseline area
            baseline_areas = {}
            swept_areas = {}
            for row in peak_rows:
                key = (row[3], row[4], row[5])  # (node_id, dof, data_type)
                if row[2]:  # is_baseline
                    baseline_areas[key] = row[6]  # area
                else:
                    if key not in swept_areas:
                        swept_areas[key] = []
                    swept_areas[key].append((row[0], row[6]))

            if baseline_areas and swept_areas:
                lines.append("\nPSD area amplification ratios (swept / baseline):")
                for key in sorted(baseline_areas.keys()):
                    if key in swept_areas:
                        base_val = baseline_areas[key]
                        if abs(base_val) > 1e-20:
                            for case_name, swept_val in swept_areas[key][:10]:
                                ratio = swept_val / base_val
                                lines.append(
                                    f"  node {key[0]}, dof={key[1]}, {key[2]}: "
                                    f"{case_name} = {ratio:.3f}x baseline"
                                )
    except Exception:
        pass

    # Miles equation summary — Q factors, GRMS, bandwidth per study
    try:
        cursor.execute("SELECT COUNT(*) FROM miles")
        miles_count = cursor.fetchone()[0]
        if miles_count > 0:
            lines.append(f"\n=== MILES EQUATION DATA ({miles_count} rows) ===")
            lines.append("Miles equation: GRMS = sqrt(pi/2 * fn * Q * PSD(fn))")
            lines.append("Q = fn / half_power_bandwidth (damping quality factor)")

            # Per-study summary
            cursor.execute(
                "SELECT s.study_name, COUNT(m.id), "
                "AVG(m.fn), AVG(m.Q), AVG(m.grms), AVG(m.bandwidth) "
                "FROM miles m JOIN cases c ON m.case_id = c.case_id "
                "JOIN studies s ON c.study_id = s.study_id "
                "GROUP BY s.study_id ORDER BY s.study_id"
            )
            for row in cursor.fetchall():
                lines.append(
                    f"  {row[0]}: {row[1]} rows, "
                    f"avg fn={row[2]:.2f} Hz, avg Q={row[3]:.1f}, "
                    f"avg GRMS={row[4]:.4e}, avg BW={row[5]:.2f} Hz"
                    if all(x is not None for x in row[2:6]) else
                    f"(some values NULL)"
                )

            # Q factor distribution
            cursor.execute(
                "SELECT MIN(Q), MAX(Q), AVG(Q), "
                "MIN(grms), MAX(grms), AVG(grms) "
                "FROM miles WHERE Q IS NOT NULL AND grms IS NOT NULL"
            )
            qrow = cursor.fetchone()
            if qrow and qrow[0] is not None:
                lines.append(f"\n  Q factor range: {qrow[0]:.1f} - {qrow[1]:.1f} (avg {qrow[2]:.1f})")
                lines.append(f"  GRMS range: {qrow[3]:.4e} - {qrow[4]:.4e} (avg {qrow[5]:.4e})")

            # Cases with NULL Q (couldn't find half-power points)
            cursor.execute("SELECT COUNT(*) FROM miles WHERE Q IS NULL")
            null_q = cursor.fetchone()[0]
            if null_q > 0:
                lines.append(f"  WARNING: {null_q} miles rows have NULL Q (half-power points not found)")
    except Exception:
        pass

    conn.close()
    return "\n".join(lines)


def gather_data_psd_signatures(db_path, study_name=None):
    """Extract PSD peak/signature statistics from DB for LLM signature analysis."""
    import sqlite3

    if not os.path.exists(db_path):
        return "Database not found: " + db_path

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    lines = []

    # --- Study info ---
    if study_name:
        c.execute(
            "SELECT study_id, study_name, study_type, num_cases FROM studies "
            "WHERE study_name = ?", (study_name,)
        )
    else:
        c.execute(
            "SELECT study_id, study_name, study_type, num_cases FROM studies "
            "ORDER BY study_id DESC LIMIT 1"
        )
    study_row = c.fetchone()
    if not study_row:
        conn.close()
        return f"Study not found in database: {study_name}" if study_name else "No studies found in database."
    study_id, study_name, study_type, num_cases = study_row
    lines.append(f"Study: {study_name}")
    lines.append(f"Type: {study_type}")
    lines.append(f"Cases in study: {num_cases}")

    # --- Case list with parameters ---
    c.execute(
        "SELECT case_id, case_name, case_number, is_baseline FROM cases "
        "WHERE study_id = ? ORDER BY case_number",
        (study_id,),
    )
    cases = c.fetchall()
    lines.append(f"Cases found in DB: {len(cases)}")

    # Map case_id -> {element_id -> K4}
    c.execute(
        "SELECT p.case_id, p.element_id, p.K4 FROM parameters p "
        "JOIN cases ca ON p.case_id = ca.case_id WHERE ca.study_id = ?",
        (study_id,),
    )
    param_rows = c.fetchall()
    case_stiffness = {}  # case_id -> list of (element_id, K4)
    for cid, elem, k4 in param_rows:
        case_stiffness.setdefault(cid, []).append((elem, k4))

    # --- Peaks table: node/dof level response peaks ---
    c.execute(
        "SELECT pk.case_id, pk.node_id, pk.dof, pk.data_type, "
        "pk.peak1_freq, pk.peak1_psd, pk.peak2_freq, pk.peak2_psd, pk.area "
        "FROM peaks pk JOIN cases ca ON pk.case_id = ca.case_id "
        "WHERE ca.study_id = ? ORDER BY ca.case_number, pk.node_id, pk.dof",
        (study_id,),
    )
    peak_rows = c.fetchall()

    if not peak_rows:
        conn.close()
        return "\n".join(lines) + "\n\nNo peaks data found in database."

    # Identify channels (node_id, dof, data_type)
    channels = sorted(set((r[1], r[2], r[3]) for r in peak_rows))
    lines.append(f"Response channels (node/DOF combinations): {len(channels)}")

    # Baseline: always pull from study_baseline (studies.is_baseline=1)
    baseline_case_ids = set()
    c.execute(
        "SELECT c.case_id FROM cases c "
        "JOIN studies s ON c.study_id = s.study_id "
        "WHERE s.is_baseline = 1 AND c.is_baseline = 1"
    )
    baseline_rows = c.fetchall()
    if baseline_rows:
        for row in baseline_rows:
            baseline_case_ids.add(row[0])
        # Load baseline peaks into peak_rows
        for bcid in baseline_case_ids:
            c.execute(
                "SELECT pk.case_id, pk.node_id, pk.dof, pk.data_type, "
                "pk.peak1_freq, pk.peak1_psd, pk.peak2_freq, pk.peak2_psd, pk.area "
                "FROM peaks pk WHERE pk.case_id = ? ORDER BY pk.node_id, pk.dof",
                (bcid,),
            )
            peak_rows = list(peak_rows) + c.fetchall()
        lines.append(f"Baseline: study_baseline (case_id={sorted(baseline_case_ids)})")
    else:
        lines.append("WARNING: No study_baseline found in database — PSD deltas cannot be computed")

    baseline_peaks = {}  # (node, dof, dtype) -> (freq, psd, area)
    swept_peaks = {}     # case_id -> {(node, dof, dtype) -> (freq, psd, area)}

    for cid, node, dof, dtype, f1, p1, f2, p2, area in peak_rows:
        key = (node, dof, dtype)
        if cid in baseline_case_ids:
            baseline_peaks[key] = (f1, p1, area)
        else:
            swept_peaks.setdefault(cid, {})[key] = (f1, p1, area)

    # --- Baseline signature ---
    lines.append("\n=== BASELINE PEAKS ===")
    for key in sorted(baseline_peaks.keys()):
        f1, p1, area = baseline_peaks[key]
        if f1 is None or p1 is None or area is None:
            continue
        lines.append(
            f"  Node {key[0]}, DOF {key[1]} ({key[2]}): "
            f"peak={f1:.2f} Hz @ {p1:.4e} g²/Hz, area={area:.4e}"
        )

    # --- Per-stiffness-level aggregate stats ---
    # Group cases by their min K4 (the loosened bolt stiffness)
    from collections import defaultdict
    level_groups = defaultdict(list)  # min_K4 -> [case_id, ...]
    for case_row in cases:
        cid = case_row[0]
        if cid in baseline_case_ids:
            continue
        stiffs = case_stiffness.get(cid, [])
        if stiffs:
            # For multi-bolt studies, use the min K4 (most-loosened)
            valid_k4 = [k4 for _, k4 in stiffs if k4 is not None]
            if not valid_k4:
                continue
            min_k4 = min(valid_k4)
            level_groups[min_k4].append(cid)

    lines.append("\n=== PEAK FREQUENCY SHIFTS BY STIFFNESS LEVEL ===")
    lines.append("(Mean shift across all cases at each stiffness level)")

    # Only show top-8 most sensitive channels per level to keep token count manageable
    for k4_val in sorted(level_groups.keys()):
        case_ids = level_groups[k4_val]
        lines.append(f"\nK4 = {k4_val:.2e} N/mm  ({len(case_ids)} cases):")
        # Per channel: mean freq shift and mean amp ratio vs baseline
        channel_stats = []
        for key in sorted(baseline_peaks.keys()):
            base_f, base_p, base_area = baseline_peaks[key]
            freq_deltas = []
            amp_ratios = []
            for cid in case_ids:
                cpks = swept_peaks.get(cid, {})
                if key in cpks:
                    f1, p1, area = cpks[key]
                    if f1 is not None and base_f and base_f > 0:
                        freq_deltas.append(f1 - base_f)
                    if area is not None and base_area and abs(base_area) > 1e-30:
                        amp_ratios.append(area / base_area)
            if freq_deltas and amp_ratios:
                mean_df = sum(freq_deltas) / len(freq_deltas)
                mean_ratio = sum(amp_ratios) / len(amp_ratios)
                max_ratio = max(amp_ratios)
                pct_shift = (mean_df / base_f * 100) if base_f else 0
                channel_stats.append((key, mean_df, pct_shift, mean_ratio, max_ratio))
        # Sort by max_ratio descending, show top 8
        channel_stats.sort(key=lambda x: x[4], reverse=True)
        for key, mean_df, pct_shift, mean_ratio, max_ratio in channel_stats[:8]:
            lines.append(
                f"    Node {key[0]}, DOF {key[1]}: "
                f"mean freq shift={mean_df:+.2f} Hz ({pct_shift:+.2f}%), "
                f"mean area ratio={mean_ratio:.3f}x, max area ratio={max_ratio:.3f}x"
            )
        if len(channel_stats) > 8:
            lines.append(f"    ... ({len(channel_stats) - 8} more channels omitted)")

    # --- Miles equation data per stiffness level ---
    lines.append("\n=== MILES EQUATION: Q FACTOR & GRMS BY STIFFNESS LEVEL ===")
    lines.append("Miles equation: GRMS = sqrt(pi/2 * fn * Q * PSD(fn))")
    lines.append("Q = fn / half_power_bandwidth (damping quality factor)")
    lines.append("Higher Q = sharper resonance = less damping. Lower GRMS = lower overall response energy.")

    # Get baseline Miles data
    try:
        baseline_miles = {}
        for bcid in baseline_case_ids:
            c.execute(
                "SELECT node_id, dof, data_type, mode_number, fn, Q, PSD_fn, grms, bandwidth "
                "FROM miles WHERE case_id=? ORDER BY node_id, dof, mode_number",
                (bcid,),
            )
            for m in c.fetchall():
                mkey = (m[0], m[1], m[2], m[3])  # (node, dof, dtype, mode)
                baseline_miles[mkey] = {"fn": m[4], "Q": m[5], "PSD_fn": m[6], "grms": m[7], "bw": m[8]}

        if baseline_miles:
            lines.append("\nBaseline Miles values:")
            for mkey in sorted(baseline_miles.keys()):
                bm = baseline_miles[mkey]
                if bm["Q"] is not None:
                    lines.append(
                        f"  Node {mkey[0]}, DOF {mkey[1]} ({mkey[2]}), Mode {mkey[3]}: "
                        f"fn={bm['fn']:.2f} Hz, Q={bm['Q']:.1f}, "
                        f"PSD(fn)={bm['PSD_fn']:.4e}, GRMS={bm['grms']:.4e}, BW={bm['bw']:.2f} Hz"
                    )

        # Per-stiffness-level Miles summary
        for k4_val in sorted(level_groups.keys()):
            cids = level_groups[k4_val]
            if not cids:
                continue

            placeholders = ",".join("?" * len(cids))
            c.execute(
                f"SELECT node_id, dof, data_type, mode_number, "
                f"AVG(fn), AVG(Q), AVG(PSD_fn), AVG(grms), AVG(bandwidth), "
                f"MIN(Q), MAX(Q), MIN(grms), MAX(grms) "
                f"FROM miles WHERE case_id IN ({placeholders}) AND Q IS NOT NULL "
                f"GROUP BY node_id, dof, data_type, mode_number "
                f"ORDER BY node_id, dof, mode_number",
                cids,
            )
            level_miles = c.fetchall()
            if level_miles:
                lines.append(f"\nK4 = {k4_val:.2e} ({len(cids)} cases, showing first 12 of {len(level_miles)} channels):")
                for lm in level_miles[:12]:  # Cap at 12 channels per level
                    node, dof, dtype, mode = lm[0], lm[1], lm[2], lm[3]
                    avg_fn, avg_Q, avg_psd, avg_grms, avg_bw = lm[4], lm[5], lm[6], lm[7], lm[8]
                    min_Q, max_Q, min_grms, max_grms = lm[9], lm[10], lm[11], lm[12]

                    # Compare to baseline
                    bkey = (node, dof, dtype, mode)
                    q_change = ""
                    grms_change = ""
                    if bkey in baseline_miles and baseline_miles[bkey]["Q"] is not None:
                        bl_Q = baseline_miles[bkey]["Q"]
                        bl_grms = baseline_miles[bkey]["grms"]
                        if bl_Q > 0:
                            q_change = f", Q delta={((avg_Q/bl_Q)-1)*100:+.1f}%"
                        if bl_grms and bl_grms > 0:
                            grms_change = f", GRMS ratio={avg_grms/bl_grms:.3f}x"

                    lines.append(
                        f"    Node {node}, DOF {dof}, Mode {mode}: "
                        f"avg fn={avg_fn:.2f} Hz, avg Q={avg_Q:.1f} [{min_Q:.1f}-{max_Q:.1f}], "
                        f"avg GRMS={avg_grms:.4e} [{min_grms:.4e}-{max_grms:.4e}]"
                        f"{q_change}{grms_change}"
                    )
    except Exception as e:
        lines.append(f"  (Miles data unavailable: {e})")

    # --- Top 5 most sensitive channels (by max area ratio across all levels) ---
    lines.append("\n=== TOP CHANNELS BY SENSITIVITY TO BOLT LOOSENESS ===")
    channel_max_ratio = {}
    for key in sorted(baseline_peaks.keys()):
        base_f, base_p, base_area = baseline_peaks[key]
        if not base_area or abs(base_area) < 1e-30:
            continue
        max_r = 1.0
        for cid, ch_dict in swept_peaks.items():
            if key in ch_dict:
                _, _, area = ch_dict[key]
                if area is not None:
                    r = area / base_area
                    max_r = max(max_r, r)
        channel_max_ratio[key] = max_r

    ranked = sorted(channel_max_ratio.items(), key=lambda x: x[1], reverse=True)
    for rank, (key, max_r) in enumerate(ranked[:8], 1):
        base_f = baseline_peaks[key][0]
        base_f_str = f"{base_f:.2f} Hz" if base_f is not None else "N/A"
        lines.append(
            f"  {rank}. Node {key[0]}, DOF {key[1]} ({key[2]}): "
            f"max ratio={max_r:.3f}x baseline, baseline peak={base_f_str}"
        )

    # --- Sensitivity threshold: first stiffness level that causes >10% change ---
    lines.append("\n=== DETECTABILITY THRESHOLD ===")
    lines.append("(First K4 level where ANY channel exceeds 10% area increase vs baseline)")
    sorted_levels = sorted(level_groups.keys(), reverse=True)  # highest K4 first
    for k4_val in sorted_levels:
        case_ids = level_groups[k4_val]
        triggered = False
        for key in baseline_peaks:
            base_f, base_p, base_area = baseline_peaks[key]
            if not base_area or abs(base_area) < 1e-30:
                continue
            for cid in case_ids:
                cpks = swept_peaks.get(cid, {})
                if key in cpks:
                    _, _, area = cpks[key]
                    if area is not None and area / base_area > 1.10:
                        triggered = True
                        break
            if triggered:
                break
        flag = " <-- FIRST DETECTABLE CHANGE" if triggered else ""
        lines.append(f"  K4={k4_val:.2e}: {'detectable change' if triggered else 'within 10% of baseline'}{flag}")

    # --- Sample design table (first 30 cases, top 2 channels + Miles data) ---
    lines.append("\n=== SAMPLE CASE TABLE (first 30 cases, top 2 channels + Miles) ===")
    top2 = [key for key, _ in ranked[:2]]
    if top2:
        hdr = "case_name | stiffness_K4 | " + " | ".join(
            f"Node{k[0]}_DOF{k[1]}_freq_Hz | Node{k[0]}_DOF{k[1]}_area_ratio | "
            f"Node{k[0]}_DOF{k[1]}_Q | Node{k[0]}_DOF{k[1]}_GRMS" for k in top2
        )
        lines.append(hdr)

        # Pre-fetch Miles data for the first 30 case_ids
        sample_cids = [cr[0] for cr in cases[:30] if not cr[3]]
        miles_by_case = {}
        if sample_cids:
            placeholders = ",".join("?" * len(sample_cids))
            try:
                c.execute(
                    f"SELECT case_id, node_id, dof, data_type, mode_number, Q, grms "
                    f"FROM miles WHERE case_id IN ({placeholders}) AND mode_number=1",
                    sample_cids,
                )
                for mr in c.fetchall():
                    mk = (mr[0], mr[1], mr[2], mr[3])  # (case_id, node, dof, dtype)
                    miles_by_case[mk] = {"Q": mr[5], "grms": mr[6]}
            except Exception:
                pass

        for case_row in cases[:30]:
            cid, cname, cnum, is_bl = case_row
            if is_bl:
                continue
            stiffs = case_stiffness.get(cid, [])
            k4_str = ",".join(f"{k4:.2e}" for _, k4 in stiffs) if stiffs else "N/A"
            cols = [cname, k4_str]
            for key in top2:
                base_f, _, base_area = baseline_peaks.get(key, (None, None, None))
                cpks = swept_peaks.get(cid, {})
                if key in cpks and base_area and abs(base_area) > 1e-30:
                    f1, _, area = cpks[key]
                    ratio = area / base_area if area is not None else float("nan")
                    cols.append(f"{f1:.2f}" if f1 else "N/A")
                    cols.append(f"{ratio:.3f}")
                else:
                    cols += ["N/A", "N/A"]
                # Miles Q and GRMS for this case/channel
                mk = (cid, key[0], key[1], key[2])
                if mk in miles_by_case:
                    q_val = miles_by_case[mk]["Q"]
                    g_val = miles_by_case[mk]["grms"]
                    cols.append(f"{q_val:.1f}" if q_val else "N/A")
                    cols.append(f"{g_val:.4e}" if g_val else "N/A")
                else:
                    cols += ["N/A", "N/A"]
            lines.append(" | ".join(str(x) for x in cols))

    conn.close()
    return "\n".join(lines)


def gather_data_feature_matrix(data_file):
    """Read training matrix stats."""
    import numpy as np

    if not os.path.exists(data_file):
        return "Training matrix not found: " + data_file

    data = np.load(data_file, allow_pickle=True)
    lines = []
    lines.append(f"File: {data_file}")
    lines.append(f"Arrays in file: {list(data.keys())}")

    if "X" in data:
        X = data["X"]
        lines.append(f"X shape: {X.shape} (samples x features)")
        lines.append(f"X dtype: {X.dtype}")
        lines.append(f"NaN count: {np.isnan(X).sum()}")
        lines.append(f"Inf count: {np.isinf(X).sum()}")
        lines.append(f"X mean: {np.nanmean(X):.6e}")
        lines.append(f"X std: {np.nanstd(X):.6e}")
        lines.append(f"X min: {np.nanmin(X):.6e}")
        lines.append(f"X max: {np.nanmax(X):.6e}")

        # Per-feature zero-variance check
        stds = np.nanstd(X, axis=0)
        zero_var = np.sum(stds < 1e-15)
        if zero_var > 0:
            lines.append(f"Zero-variance features: {zero_var}")

    for y_name in ["y", "y_bolt", "y_binary", "y_severity"]:
        if y_name in data:
            y = data[y_name]
            lines.append(f"\n{y_name} shape: {y.shape}")
            unique, counts = np.unique(y, return_counts=True)
            lines.append(f"{y_name} label distribution:")
            for label, count in zip(unique, counts):
                lines.append(f"  Class {label}: {count} samples")

    if "feature_names" in data:
        names = data["feature_names"]
        lines.append(f"\nFeature names ({len(names)} total):")
        for n in names[:30]:
            lines.append(f"  {n}")
        if len(names) > 30:
            lines.append(f"  ... and {len(names) - 30} more")

        # Feature naming legend so LLM can interpret results
        lines.append("\n=== FEATURE NAMING CONVENTION ===")
        lines.append("Each feature name follows the pattern: n{node}_{DOF}_{type}_{measurement}")
        lines.append("")
        lines.append("Node: physical location on structure (e.g., n222 = node 222)")
        lines.append("DOF (Direction of Freedom):")
        lines.append("  T1=translation-X, T2=translation-Y, T3=translation-Z")
        lines.append("  R1=rotation-X, R2=rotation-Y, R3=rotation-Z")
        lines.append("Data type: acc=acceleration, dis=displacement")
        lines.append("")
        lines.append("Measurement suffixes:")
        lines.append("  _area     = area under PSD curve = RMS squared (total energy)")
        lines.append("  _pk{N}a   = peak N amplitude (height of Nth resonance)")
        lines.append("  _pk{N}f   = peak N frequency (Hz) (location of Nth resonance)")
        lines.append("  _rms      = spectral RMS in band")
        lines.append("  _d_rms    = delta RMS vs baseline (change from healthy)")
        lines.append("  _d_band{N}= delta in frequency band N vs baseline")
        lines.append("  _m{N}_fn     = Miles mode N: natural frequency (Hz)")
        lines.append("  _m{N}_Q      = Miles mode N: quality factor (fn/bandwidth, higher=sharper resonance)")
        lines.append("  _m{N}_PSDfn  = Miles mode N: PSD amplitude at natural frequency")
        lines.append("  _m{N}_grms   = Miles mode N: GRMS = sqrt(pi/2 * fn * Q * PSD_fn)")
        lines.append("  _m{N}_bw     = Miles mode N: half-power bandwidth (Hz)")
        lines.append("")
        lines.append("Example: n444_T1_acc_m1_grms = GRMS of 1st resonance mode, X-acceleration at node 444")
        lines.append("Example: n222_R2_dis_area = total rotational displacement energy (Y-axis) at node 222")
        lines.append("")
        lines.append("=== CROSS-VALIDATION METHOD ===")
        lines.append("Stratified k-fold CV: data split into k equal folds, each fold tested while")
        lines.append("training on the remaining k-1 folds. Every sample gets exactly one prediction.")
        lines.append("k is set to min(5, smallest_class_count) to ensure each class appears in every fold.")
        lines.append("This is NOT an 80/20 split — it is a rotation that tests ALL data.")

    return "\n".join(lines)


def gather_data_classification(data_file):
    """Read classification report text with interpretation guide."""
    if not os.path.exists(data_file):
        return "Classification report not found: " + data_file
    with open(data_file, "r") as f:
        content = f.read()

    # Add interpretation guide for the LLM
    guide = """
=== INTERPRETATION GUIDE ===
Confusion Matrix: rows = true class, columns = predicted class.
  - Diagonal = correct predictions. Off-diagonal = misclassifications.
  - Element 0 = healthy (no bolt loosened). Elements 2-10 = which CBUSH bolt is loosened.
  - Adjacent bolt misclassifications (e.g., 9 predicted as 10) are physically expected
    because neighboring bolts produce similar structural responses.

Precision: of all cases predicted as element X, what fraction were truly element X?
Recall: of all cases that ARE element X, what fraction did we correctly identify?
F1-score: harmonic mean of precision and recall (balanced metric).

Feature importance: higher value = more influential in classification decision.
  - See Feature Matrix report for feature naming convention.
  - Physically meaningful if top features correspond to nodes near the loosened bolts.

CV accuracy: cross-validated accuracy (see Feature Matrix report for CV method details).
  +/- value is standard deviation across folds (lower = more consistent).
"""
    return content + guide


def gather_data_executive_summary(output_dir):
    """Read all prior reports for executive summary."""
    parts = []
    for i in range(1, 8):
        pattern = f"{i:02d}_"
        for fname in sorted(os.listdir(output_dir)):
            if fname.startswith(pattern) and fname.endswith(".md"):
                fpath = os.path.join(output_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    parts.append(f"=== {fname} ===\n" + f.read())
    return "\n\n".join(parts) if parts else "No prior reports found."


def write_report(output_dir, report_type, content):
    """Write report markdown file with ## headings enforced."""
    cfg = REPORT_CONFIGS[report_type]
    output_path = os.path.join(output_dir, cfg["filename"])

    # Post-process: fix headings the LLM may have generated
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # Strip top-level # headings (we add our own # title in the header)
        if line.startswith('# ') and not line.startswith('## '):
            line = '## ' + line[2:]
        # Convert ### to ## (but leave #### alone — tables sometimes use them)
        elif line.startswith('### ') and not line.startswith('#### '):
            line = '## ' + line[4:]
        fixed_lines.append(line)
    content = '\n'.join(fixed_lines)

    # Determine chain position
    idx = REPORT_ORDER.index(report_type) if report_type in REPORT_ORDER else -1
    chain_info = f"**Pipeline Position:** Report {idx + 1} of {len(REPORT_ORDER)}"
    if idx > 0:
        prev = REPORT_CONFIGS[REPORT_ORDER[idx - 1]]["title"]
        chain_info += f" (builds on: {prev})"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {cfg['title']}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**Report Type:** {report_type}  \n")
        f.write("**Generator:** Claude (Anthropic API, temperature=0)  \n")
        f.write(f"{chain_info}  \n\n")
        f.write("---\n\n")
        f.write(content)
        f.write("\n")

    print(f"Report written: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate LLM pipeline report")
    parser.add_argument(
        "--report-type",
        required=True,
        choices=list(REPORT_CONFIGS.keys()),
        help="Type of report to generate",
    )
    parser.add_argument("--data-file", help="Primary data file to analyze")
    parser.add_argument("--config-file", help="Config file (for study_plan)")
    parser.add_argument("--db-path", help="Database path (for db_health)")
    parser.add_argument("--study-name", help="Study name to filter (for psd_signatures)")
    parser.add_argument("--output-dir", required=True, help="Output directory for reports")
    parser.add_argument("--extra-data", help="Additional data to append (inline text)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    report_type = args.report_type
    cfg = REPORT_CONFIGS[report_type]

    # Gather data based on report type
    if report_type == "fem_health":
        data = gather_data_fem_health(args.data_file, args.config_file)
    elif report_type == "study_plan":
        data = gather_data_study_plan(args.data_file, args.config_file)
    elif report_type == "heeds_status":
        data = gather_data_heeds_status(args.data_file)
    elif report_type == "db_health":
        data = gather_data_db_health(args.db_path)
    elif report_type == "psd_signatures":
        data = gather_data_psd_signatures(args.db_path, study_name=args.study_name)
    elif report_type == "feature_matrix":
        data = gather_data_feature_matrix(args.data_file)
    elif report_type == "classification":
        data = gather_data_classification(args.data_file)
    elif report_type == "executive_summary":
        data = gather_data_executive_summary(args.output_dir)

    if args.extra_data:
        data += "\n\n=== Additional Context ===\n" + args.extra_data

    # Inject FEM utility baseline context into ALL reports
    # This gives every LLM report access to model properties, natural frequencies,
    # mode shapes, CBUSH stiffness, and bolt force data
    fem_context = get_fem_utility_context()
    if fem_context:
        data += fem_context

    # Chain: append previous report for context (except executive_summary which reads all)
    if report_type != "executive_summary":
        prev_report = get_previous_report(args.output_dir, report_type)
        if prev_report:
            data += "\n\n" + prev_report

    # Build prompt
    user_prompt = cfg["prompt"] + "--- BEGIN DATA ---\n" + data + "\n--- END DATA ---"

    print(f"Generating report: {cfg['title']}")
    print(f"Data size: {len(data):,} chars")

    # Call API
    report_content = call_anthropic(SYSTEM_PROMPT, user_prompt)

    # Write report
    output_path = write_report(args.output_dir, report_type, report_content)

    # Write path to GITHUB_OUTPUT if available
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"REPORT_PATH={output_path}\n")


if __name__ == "__main__":
    main()
