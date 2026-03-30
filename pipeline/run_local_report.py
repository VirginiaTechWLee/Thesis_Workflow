"""
Standalone CLI wrapper to run LLM pipeline reports locally (outside GitHub Actions).

Reuses all gather_data and generation logic from generate_pipeline_report.py.

Usage examples:
    python run_local_report.py --db_path D:/thesis_database/thesis_results.db \
        --study study_A_single_bolt_sweep --report_type psd_signatures \
        --output_dir D:/thesis_database/reports/study_A

    python run_local_report.py --db_path D:/thesis_database/thesis_results.db \
        --study study_A_single_bolt_sweep --report_type all \
        --output_dir D:/thesis_database/reports/study_A

    python run_local_report.py --db_path D:/thesis_database/thesis_results.db \
        --report_type db_health --output_dir D:/thesis_database/reports/study_A

Requires:
    ANTHROPIC_API_KEY environment variable (key name: GitHub_Thesis_Workflow)
    pip install anthropic
"""

import sys
import os
import argparse

# Allow importing from the same directory regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_pipeline_report import (
    REPORT_CONFIGS,
    REPORT_ORDER,
    SYSTEM_PROMPT,
    call_anthropic,
    get_previous_report,
    write_report,
    gather_data_db_health,
    gather_data_psd_signatures,
    gather_data_executive_summary,
    gather_data_fem_health,
    gather_data_study_plan,
    gather_data_heeds_status,
    gather_data_feature_matrix,
    gather_data_classification,
)

# Report types that only need a DB path (no separate data file)
DB_REPORT_TYPES = {"db_health", "psd_signatures"}

# Report types that can auto-discover their data files from the repo/DB directory
AUTO_DISCOVER_TYPES = {"feature_matrix", "classification", "fem_health", "study_plan", "heeds_status"}

# Report types that read prior reports from output_dir
SUMMARY_REPORT_TYPES = {"executive_summary"}

# Report types that ALWAYS need an explicit data file (none — all can auto-discover now)
FILE_REPORT_TYPES = set()

# All report types that can be generated with just --db_path
LOCAL_DB_TYPES = list(DB_REPORT_TYPES | SUMMARY_REPORT_TYPES | AUTO_DISCOVER_TYPES)


def resolve_study_id(db_path, study_name):
    """Look up the study_id for a given study name."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT study_id FROM studies WHERE study_name = ?", (study_name,)
    ).fetchone()
    conn.close()
    if row is None:
        # List available studies to help the user
        conn = sqlite3.connect(db_path)
        studies = conn.execute("SELECT study_name FROM studies").fetchall()
        conn.close()
        names = [s[0] for s in studies]
        print(f"ERROR: Study '{study_name}' not found in database.")
        print(f"Available studies: {', '.join(names)}")
        sys.exit(1)
    return row[0]


def generate_one_report(report_type, db_path, output_dir, data_file=None,
                        config_file=None, study_name=None):
    """Generate a single report, gathering data and calling the Anthropic API."""
    cfg = REPORT_CONFIGS[report_type]
    print(f"\n{'='*60}")
    print(f"Generating: {cfg['title']} ({report_type})")
    print(f"{'='*60}")

    # Gather data
    if report_type in DB_REPORT_TYPES:
        if not db_path:
            print(f"ERROR: --db_path required for {report_type}")
            sys.exit(1)
        if report_type == "db_health":
            data = gather_data_db_health(db_path)
        elif report_type == "psd_signatures":
            data = gather_data_psd_signatures(db_path, study_name=study_name)
    elif report_type in AUTO_DISCOVER_TYPES:
        # Auto-discover data files from DB directory or repo, or use explicit --data_file
        resolved_file = data_file
        resolved_config = config_file
        if not resolved_file:
            db_dir = os.path.dirname(db_path) if db_path else None
            # Discover repo root: walk up from this script's location
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            if report_type == "feature_matrix" and db_dir:
                resolved_file = os.path.join(db_dir, "training_matrix.npz")
            elif report_type == "classification" and db_dir:
                resolved_file = os.path.join(db_dir, "classification_report.txt")
            elif report_type == "fem_health":
                # Look for .dat files in fem_input/ or templates/
                for candidate in [
                    os.path.join(repo_root, "fem_input", "Fixed_base_beam.dat"),
                    os.path.join(repo_root, "templates", "RandomBeamX.dat"),
                ]:
                    if os.path.exists(candidate):
                        resolved_file = candidate
                        break
                if not resolved_config:
                    cfg_candidate = os.path.join(repo_root, "fem_input", "config.yaml")
                    if os.path.exists(cfg_candidate):
                        resolved_config = cfg_candidate
            elif report_type == "study_plan":
                # Look for .heeds files in heeds/projects/
                import glob
                heeds_dir = os.path.join(repo_root, "heeds", "projects")
                heeds_files = sorted(glob.glob(os.path.join(heeds_dir, "*.heeds")))
                if heeds_files:
                    resolved_file = heeds_files[-1]  # Latest .heeds file
                if not resolved_config:
                    cfg_candidate = os.path.join(repo_root, "fem_input", "config.yaml")
                    if os.path.exists(cfg_candidate):
                        resolved_config = cfg_candidate
            elif report_type == "heeds_status":
                # Look for HEEDS log files
                for candidate in [
                    os.path.join(repo_root, "pipeline", "HEEDSMDO.log"),
                ]:
                    if os.path.exists(candidate):
                        resolved_file = candidate
                        break

            if resolved_file and os.path.exists(resolved_file):
                print(f"Auto-discovered: {resolved_file}")
                if resolved_config:
                    print(f"Auto-discovered config: {resolved_config}")
            elif resolved_file:
                print(f"SKIP: {report_type} — file not found: {resolved_file}")
                return None
            else:
                print(f"SKIP: {report_type} — could not auto-discover data file")
                return None

        if report_type == "feature_matrix":
            data = gather_data_feature_matrix(resolved_file)
        elif report_type == "classification":
            data = gather_data_classification(resolved_file)
        elif report_type == "fem_health":
            data = gather_data_fem_health(resolved_file, resolved_config)
        elif report_type == "study_plan":
            data = gather_data_study_plan(resolved_file, resolved_config)
        elif report_type == "heeds_status":
            data = gather_data_heeds_status(resolved_file)
    elif report_type == "executive_summary":
        data = gather_data_executive_summary(output_dir)
    elif report_type in FILE_REPORT_TYPES:
        if not data_file:
            print(f"ERROR: --data_file required for {report_type}")
            sys.exit(1)
        if report_type == "fem_health":
            data = gather_data_fem_health(data_file, config_file)
        elif report_type == "study_plan":
            data = gather_data_study_plan(data_file, config_file)
        elif report_type == "heeds_status":
            data = gather_data_heeds_status(data_file)
    else:
        print(f"ERROR: Unknown report type '{report_type}'")
        sys.exit(1)

    # Chain: append previous report for context
    if report_type != "executive_summary":
        prev_report = get_previous_report(output_dir, report_type)
        if prev_report:
            data += "\n\n" + prev_report

    # Build prompt and call API
    user_prompt = cfg["prompt"] + "--- BEGIN DATA ---\n" + data + "\n--- END DATA ---"
    print(f"Data size: {len(data):,} chars")

    report_content = call_anthropic(SYSTEM_PROMPT, user_prompt)

    # Write report
    output_path = write_report(output_dir, report_type, report_content)
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Run LLM pipeline reports locally (standalone, no GitHub Actions)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Single DB-based report:\n"
            "  python run_local_report.py --db_path D:\\thesis_database\\thesis_results.db \\\n"
            "      --report_type psd_signatures --output_dir D:\\thesis_database\\reports\\study_A\n\n"
            "  # All DB-based reports for a study:\n"
            "  python run_local_report.py --db_path D:\\thesis_database\\thesis_results.db \\\n"
            "      --study study_A_single_bolt_sweep --report_type all \\\n"
            "      --output_dir D:\\thesis_database\\reports\\study_A\n\n"
            "  # File-based report (FEM health):\n"
            "  python run_local_report.py --data_file path\\to\\model.dat \\\n"
            "      --report_type fem_health --output_dir D:\\thesis_database\\reports\\study_A\n"
        ),
    )
    parser.add_argument(
        "--db_path", help="Path to thesis_results.db SQLite database"
    )
    parser.add_argument(
        "--study", help="Study name (e.g. study_A_single_bolt_sweep). Used for filtering/context."
    )
    parser.add_argument(
        "--report_type",
        required=True,
        choices=list(REPORT_CONFIGS.keys()) + ["all"],
        help="Report type to generate, or 'all' for all DB-based reports + executive summary",
    )
    parser.add_argument(
        "--output_dir",
        required=True,
        help="Directory where .md reports are written",
    )
    parser.add_argument(
        "--data_file",
        help="Primary data file (for fem_health, study_plan, heeds_status, feature_matrix, classification)",
    )
    parser.add_argument(
        "--config_file",
        help="Config YAML file (for fem_health, study_plan)",
    )

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    # Validate API key early
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY environment variable not set.")
        print("Set it with:  set ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Resolve study if provided (validates it exists)
    if args.study and args.db_path:
        resolve_study_id(args.db_path, args.study)
        print(f"Study: {args.study}")

    if args.report_type == "all":
        # Generate all reports that can run with the available inputs.
        # DB-based reports run if --db_path is set.
        # File-based reports run only if --data_file is also set.
        # Executive summary always runs last (reads prior reports from output_dir).
        generated = []
        skipped = []

        for rt in REPORT_ORDER:
            if rt in DB_REPORT_TYPES and args.db_path:
                path = generate_one_report(
                    rt, args.db_path, args.output_dir, study_name=args.study
                )
                generated.append((rt, path))
            elif rt in AUTO_DISCOVER_TYPES and (args.data_file or args.db_path):
                path = generate_one_report(
                    rt, args.db_path, args.output_dir,
                    data_file=args.data_file, study_name=args.study,
                )
                if path:  # None means file not found, skip silently
                    generated.append((rt, path))
                else:
                    skipped.append(rt)
            elif rt in FILE_REPORT_TYPES and args.data_file:
                path = generate_one_report(
                    rt, args.db_path, args.output_dir,
                    data_file=args.data_file, config_file=args.config_file,
                    study_name=args.study,
                )
                generated.append((rt, path))
            elif rt == "executive_summary":
                # Only generate if at least one prior report exists
                if generated:
                    path = generate_one_report(
                        rt, args.db_path, args.output_dir, study_name=args.study
                    )
                    generated.append((rt, path))
                else:
                    skipped.append(rt)
            else:
                skipped.append(rt)

        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Generated {len(generated)} report(s):")
        for rt, path in generated:
            print(f"  {rt}: {path}")
        if skipped:
            print(f"Skipped {len(skipped)} (missing inputs): {', '.join(skipped)}")
    else:
        # Single report
        generate_one_report(
            args.report_type,
            args.db_path,
            args.output_dir,
            data_file=args.data_file,
            config_file=args.config_file,
            study_name=args.study,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
