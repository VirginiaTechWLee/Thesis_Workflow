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
    "fem_health",       # 01 — no prior report, but checks nastran utility report
    "study_plan",       # 02 — reads 01
    "heeds_status",     # 03 — reads 02
    "db_health",        # 04 — reads 03
    "feature_matrix",   # 05 — reads 04
    "classification",   # 06 — reads 05
    "executive_summary",  # 07 — reads all 01-06
]

REPORT_CONFIGS = {
    "fem_health": {
        "title": "Pre-Run FEM Health Check",
        "filename": "01_fem_health.md",
        "prompt": (
            "Analyze this Nastran FEM input deck and produce a health check report.\n\n"
            "Use ## headings for each section (never ### or deeper).\n\n"
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
            "- All INCLUDE cards and referenced filenames\n\n"
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
            "- Frequency range and point count consistency\n\n"
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
    "feature_matrix": {
        "title": "Feature Matrix Report",
        "filename": "05_feature_matrix.md",
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
        "filename": "06_classification.md",
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
        "filename": "07_executive_summary.md",
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


def call_anthropic(system_prompt, user_prompt):
    """Call Anthropic API with grounded prompt."""
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
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text


def find_latest_nastran_utility_report():
    """Find the most recent simulation_report.md from FEM_Utility runs."""
    fem_utility_base = os.path.join(
        os.environ.get('USERPROFILE', r'C:\Users\waynelee'),
        'Documents', 'FEM_Utility'
    )
    if not os.path.exists(fem_utility_base):
        return None

    # Find all simulation_report.md files across timestamped run folders
    report_files = globmod.glob(
        os.path.join(fem_utility_base, '*', 'simulation_report.md')
    )
    if not report_files:
        return None

    # Return the most recently modified one
    latest = max(report_files, key=os.path.getmtime)
    return latest


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
        print(f"Chained context: reading previous report {prev_cfg['filename']}")
        return f"=== Previous Pipeline Report: {prev_cfg['title']} ===\n{content}"

    print(f"Note: previous report {prev_cfg['filename']} not found (skipping chain)")
    return None


def gather_data_fem_health(data_file):
    """Read DAT file for FEM health check + latest nastran utility report."""
    parts = []
    with open(data_file, "r", errors="ignore") as f:
        parts.append("=== FEM Input Deck ===\n" + f.read()[:60000])

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

    for table in ["studies", "cases", "psd_data", "peaks", "parameters"]:
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
        lines.append("\nPer-case PSD row counts:")
        for row in cursor.fetchall():
            bl = " [BASELINE]" if row[2] else ""
            lines.append(f"  Case {row[1]} ({row[0]}): {row[3]} PSD rows{bl}")
    except Exception:
        pass

    try:
        cursor.execute(
            "SELECT c.case_name, p.element_id, p.parameter_name, p.value "
            "FROM parameters p JOIN cases c ON p.case_id = c.case_id "
            "WHERE p.parameter_name LIKE '%K4%' ORDER BY c.case_number"
        )
        rows = cursor.fetchall()
        if rows:
            lines.append("\nK4 stiffness values per case:")
            for row in rows:
                lines.append(f"  {row[0]}: element {row[1]}, {row[2]} = {row[3]}")
    except Exception:
        pass

    # CBUSH element force data — check peaks table for CBUSH-related entries
    try:
        cursor.execute(
            "SELECT c.case_name, c.case_number, c.is_baseline, "
            "pk.element_id, pk.response_type, pk.peak_value, pk.frequency_hz "
            "FROM peaks pk JOIN cases c ON pk.case_id = c.case_id "
            "WHERE pk.element_id IS NOT NULL "
            "ORDER BY c.case_number, pk.element_id"
        )
        force_rows = cursor.fetchall()
        if force_rows:
            lines.append("\nCBUSH element force/response peaks:")
            for row in force_rows[:100]:  # Cap at 100 rows
                bl = " [BASELINE]" if row[2] else ""
                lines.append(
                    f"  Case {row[1]} ({row[0]}){bl}: elem {row[3]}, "
                    f"{row[4]} = {row[5]:.6e} @ {row[6]:.2f} Hz"
                )
            if len(force_rows) > 100:
                lines.append(f"  ... and {len(force_rows) - 100} more rows")

            # Compute amplification ratios: swept / baseline for matching elements
            baseline_forces = {}
            swept_forces = {}
            for row in force_rows:
                key = (row[3], row[4])  # (element_id, response_type)
                if row[2]:  # is_baseline
                    baseline_forces[key] = row[5]
                else:
                    if key not in swept_forces:
                        swept_forces[key] = []
                    swept_forces[key].append((row[0], row[5]))

            if baseline_forces and swept_forces:
                lines.append("\nAmplification ratios (swept / baseline):")
                for key in sorted(baseline_forces.keys()):
                    if key in swept_forces:
                        base_val = baseline_forces[key]
                        if abs(base_val) > 1e-20:
                            for case_name, swept_val in swept_forces[key][:10]:
                                ratio = swept_val / base_val
                                lines.append(
                                    f"  elem {key[0]}, {key[1]}: "
                                    f"{case_name} = {ratio:.3f}x baseline"
                                )
    except Exception:
        pass

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

    if "y" in data:
        y = data["y"]
        lines.append(f"\ny shape: {y.shape}")
        unique, counts = np.unique(y, return_counts=True)
        lines.append("Label distribution:")
        for label, count in zip(unique, counts):
            lines.append(f"  Class {label}: {count} samples")

    if "feature_names" in data:
        names = data["feature_names"]
        lines.append(f"\nFeature names ({len(names)} total):")
        for n in names[:20]:
            lines.append(f"  {n}")
        if len(names) > 20:
            lines.append(f"  ... and {len(names) - 20} more")

    return "\n".join(lines)


def gather_data_classification(data_file):
    """Read classification report text."""
    if not os.path.exists(data_file):
        return "Classification report not found: " + data_file
    with open(data_file, "r") as f:
        return f.read()


def gather_data_executive_summary(output_dir):
    """Read all prior reports for executive summary."""
    parts = []
    for i in range(1, 7):
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

    # Post-process: fix any ### headings the LLM may have generated
    lines = content.split('\n')
    fixed_lines = []
    for line in lines:
        # Convert ### to ## (but leave #### alone — tables sometimes use them)
        if line.startswith('### ') and not line.startswith('#### '):
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
    parser.add_argument("--output-dir", required=True, help="Output directory for reports")
    parser.add_argument("--extra-data", help="Additional data to append (inline text)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    report_type = args.report_type
    cfg = REPORT_CONFIGS[report_type]

    # Gather data based on report type
    if report_type == "fem_health":
        data = gather_data_fem_health(args.data_file)
    elif report_type == "study_plan":
        data = gather_data_study_plan(args.data_file, args.config_file)
    elif report_type == "heeds_status":
        data = gather_data_heeds_status(args.data_file)
    elif report_type == "db_health":
        data = gather_data_db_health(args.db_path)
    elif report_type == "feature_matrix":
        data = gather_data_feature_matrix(args.data_file)
    elif report_type == "classification":
        data = gather_data_classification(args.data_file)
    elif report_type == "executive_summary":
        data = gather_data_executive_summary(args.output_dir)

    if args.extra_data:
        data += "\n\n=== Additional Context ===\n" + args.extra_data

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
