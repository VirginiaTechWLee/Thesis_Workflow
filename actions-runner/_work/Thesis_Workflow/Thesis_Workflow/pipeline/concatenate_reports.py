"""
Concatenate all numbered pipeline reports into a single master document.

Reads 01_*.md through 07_*.md from the reports directory and produces a single
markdown file with a cover page and table of contents.

Usage:
    python pipeline/concatenate_reports.py --reports-dir <path> [--output <path>]

If --output is omitted, writes to <reports-dir>/00_master_report.md
"""

import os
import re
import sys
import argparse
from datetime import datetime


def discover_reports(reports_dir):
    """Find all numbered report files (01_ through 99_) in order."""
    reports = []
    for fname in sorted(os.listdir(reports_dir)):
        if re.match(r"^\d{2}_.*\.md$", fname) and not fname.startswith("00_"):
            fpath = os.path.join(reports_dir, fname)
            reports.append((fname, fpath))
    return reports


def extract_title(content):
    """Extract the first H1 title from markdown content."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return None


def build_master(reports_dir, reports):
    """Build the master report markdown string."""
    parts = []

    # --- Cover page ---
    study_name = os.path.basename(reports_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts.append("# Master Pipeline Report")
    parts.append("")
    parts.append(f"**Study:** {study_name}  ")
    parts.append(f"**Generated:** {timestamp}  ")
    parts.append(f"**Reports included:** {len(reports)}  ")
    parts.append("")
    parts.append("---")
    parts.append("")

    # --- Table of contents ---
    parts.append("## Table of Contents")
    parts.append("")
    toc_entries = []
    for fname, fpath in reports:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        title = extract_title(content) or fname
        # Create anchor from title
        anchor = re.sub(r"[^a-z0-9 -]", "", title.lower())
        anchor = re.sub(r"\s+", "-", anchor).strip("-")
        toc_entries.append((title, anchor, fname, content))
        parts.append(f"- [{title}](#{anchor})")

    parts.append("")
    parts.append("---")
    parts.append("")

    # --- Report sections ---
    for title, anchor, fname, content in toc_entries:
        parts.append(content.rstrip())
        parts.append("")
        parts.append("---")
        parts.append("")

    # --- Footer ---
    parts.append(f"*End of master report — {len(reports)} sections, generated {timestamp}*")
    parts.append("")

    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Concatenate pipeline reports")
    parser.add_argument("--reports-dir", required=True, help="Directory containing numbered reports")
    parser.add_argument("--output", help="Output file path (default: <reports-dir>/00_master_report.md)")
    args = parser.parse_args()

    if not os.path.isdir(args.reports_dir):
        print(f"ERROR: Reports directory not found: {args.reports_dir}")
        sys.exit(1)

    reports = discover_reports(args.reports_dir)
    if not reports:
        print(f"WARNING: No numbered report files found in {args.reports_dir}")
        sys.exit(0)

    print(f"Found {len(reports)} reports:")
    for fname, _ in reports:
        print(f"  {fname}")

    master = build_master(args.reports_dir, reports)

    output_path = args.output or os.path.join(args.reports_dir, "00_master_report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(master)

    print(f"Master report written: {output_path}")
    print(f"Size: {len(master):,} chars")


if __name__ == "__main__":
    main()
