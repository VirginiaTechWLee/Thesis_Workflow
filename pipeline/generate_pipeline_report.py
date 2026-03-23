"""
Generate LLM-powered pipeline reports at each stage of the super workflow.

Each report uses the same grounded system prompt pattern: analyze ONLY the
provided data, no outside knowledge, temperature=0.

Usage:
    python pipeline/generate_pipeline_report.py --report-type fem_health --data-file <path> --output-dir <path>
    python pipeline/generate_pipeline_report.py --report-type db_health --db-path <path> --output-dir <path>

Report types:
    1. fem_health        — Pre-run FEM health check (reads DAT file)
    2. study_plan        — Study plan summary (reads config + .heeds file)
    3. heeds_status      — HEEDS run status (reads study log + design count)
    4. db_health         — Database health (queries SQLite)
    5. feature_matrix    — Feature matrix report (reads training_matrix.npz stats)
    6. classification    — Classification results (reads classification_report.txt)
    7. executive_summary — Pipeline executive summary (reads all prior reports)

Requires:
    ANTHROPIC_API_KEY environment variable
    pip install anthropic
"""

import sys
import os
import argparse
import json
from datetime import datetime


SYSTEM_PROMPT = (
    "You are a structural engineering pipeline analyst. Analyze ONLY the data "
    "provided to you in this message. Do not use any outside knowledge about "
    "Nastran, spacecraft, structural analysis, or machine learning. If the data "
    "does not support a conclusion, say so explicitly. Never invent numbers, "
    "results, or conclusions not present in the provided data."
)

REPORT_CONFIGS = {
    "fem_health": {
        "title": "Pre-Run FEM Health Check",
        "filename": "01_fem_health.md",
        "prompt": (
            "Analyze this Nastran FEM input deck and produce a health check report:\n"
            "1. Model overview — solution type, element count, node count\n"
            "2. CBUSH bolt elements — count, property IDs, stiffness values\n"
            "3. Boundary conditions — SPC cards, constraints\n"
            "4. Include files referenced\n"
            "5. Any potential issues or missing cards\n"
            "6. Health verdict — is this FEM ready to run?\n\n"
        ),
    },
    "study_plan": {
        "title": "Study Plan Summary",
        "filename": "02_study_plan.md",
        "prompt": (
            "Analyze this study configuration and HEEDS project file. Produce a study plan summary:\n"
            "1. Study name and type\n"
            "2. Design variables — which bolts are being swept, stiffness range\n"
            "3. Number of expected designs\n"
            "4. Response variables being tracked\n"
            "5. Solver chain — what Nastran runs are configured\n"
            "6. Assessment — is this study plan well-configured?\n\n"
        ),
    },
    "heeds_status": {
        "title": "HEEDS Run Status Report",
        "filename": "03_heeds_status.md",
        "prompt": (
            "Analyze this HEEDS study run data and produce a status report:\n"
            "1. Designs completed vs expected\n"
            "2. Per-design verification — which have PCH and CSV files\n"
            "3. Timing — total elapsed, per-design average\n"
            "4. Any failures or warnings from the study log\n"
            "5. Assessment — did the study complete successfully?\n\n"
        ),
    },
    "db_health": {
        "title": "Database Health Report",
        "filename": "04_db_health.md",
        "prompt": (
            "Analyze this database health data and produce a report:\n"
            "1. Table row counts and database size\n"
            "2. Study and case summary\n"
            "3. PSD data coverage — rows per case, any gaps\n"
            "4. Parameter distribution — stiffness values across cases\n"
            "5. Baseline status — is baseline case present\n"
            "6. Assessment — is the database healthy and complete?\n\n"
        ),
    },
    "feature_matrix": {
        "title": "Feature Matrix Report",
        "filename": "05_feature_matrix.md",
        "prompt": (
            "Analyze this feature extraction data and produce a report:\n"
            "1. Matrix dimensions — samples, features\n"
            "2. Feature types — peak features, spectral features, delta features\n"
            "3. Label distribution — how many samples per class\n"
            "4. Any NaN or infinite values\n"
            "5. Feature statistics — mean, std, min, max ranges\n"
            "6. Assessment — is this feature matrix ready for ML training?\n\n"
        ),
    },
    "classification": {
        "title": "Classification Report",
        "filename": "06_classification.md",
        "prompt": (
            "Analyze this ML classification data and produce a report:\n"
            "1. Model type and parameters\n"
            "2. Accuracy, precision, recall, F1 per class\n"
            "3. Confusion matrix interpretation\n"
            "4. Top important features — what physical meaning do they suggest\n"
            "5. Cross-validation results if present\n"
            "6. Assessment — is this classifier reliable? What would improve it?\n\n"
        ),
    },
    "executive_summary": {
        "title": "Pipeline Executive Summary",
        "filename": "07_executive_summary.md",
        "prompt": (
            "Analyze the previous pipeline stage reports and produce an executive summary:\n"
            "1. Overall pipeline status — which stages passed/failed\n"
            "2. Key findings from each stage\n"
            "3. Data quality assessment — FEM, database, features, classifier\n"
            "4. Recommendations — what should be done next\n"
            "5. Confidence assessment — how trustworthy are the results\n\n"
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


def gather_data_fem_health(data_file):
    """Read DAT file for FEM health check."""
    with open(data_file, "r", errors="ignore") as f:
        return f.read()[:60000]


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
    """Query database for health stats."""
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
    """Write report markdown file."""
    cfg = REPORT_CONFIGS[report_type]
    output_path = os.path.join(output_dir, cfg["filename"])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# {cfg['title']}\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**Report Type:** {report_type}  \n")
        f.write("**Generator:** Claude (Anthropic API, temperature=0)  \n\n")
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
