"""
Generate an LLM-powered simulation report from Nastran F06 output.

Reads the F06 file, calls the Anthropic API with a grounded system prompt
(no outside knowledge allowed), and writes simulation_report.md.

Usage:
    python pipeline/generate_simulation_report.py --run-folder <path>
    python pipeline/generate_simulation_report.py --f06 <path> --output <path>

Requires:
    ANTHROPIC_API_KEY environment variable
    pip install anthropic
"""

import sys
import os
import argparse
import glob as globmod
import re


def find_f06_files(run_folder):
    """Find all F06 files in the run folder."""
    return sorted(globmod.glob(os.path.join(run_folder, '*.f06')) +
                  globmod.glob(os.path.join(run_folder, '*.F06')))


def extract_f06_summary(f06_path, max_chars=80000):
    """Read F06 and extract key sections to stay within token limits.
    Keeps: header, eigenvalue table, warnings/fatals, and tail."""
    with open(f06_path, 'r', errors='ignore') as f:
        content = f.read()

    # If small enough, pass the whole thing
    if len(content) <= max_chars:
        return content

    # Extract key sections for large F06 files
    sections = []

    # Header (first 200 lines)
    lines = content.split('\n')
    sections.append('\n'.join(lines[:200]))

    # Eigenvalue / natural frequency tables
    for pattern in [r'R E A L   E I G E N V A L U E S.*?(?=\n\s*\n|\x0c)',
                    r'EIGENVALUE.*?(?=\n\s*\n|\x0c)']:
        matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
        for m in matches[:3]:
            sections.append(m[:5000])

    # FATAL and WARNING messages (with context)
    for line_num, line in enumerate(lines):
        if re.search(r'(FATAL|WARNING|USER INFORMATION)', line, re.IGNORECASE):
            start = max(0, line_num - 2)
            end = min(len(lines), line_num + 5)
            sections.append('\n'.join(lines[start:end]))

    # Tail (last 100 lines)
    sections.append('\n'.join(lines[-100:]))

    combined = '\n\n--- [section break] ---\n\n'.join(sections)
    return combined[:max_chars]


def generate_report(f06_content, f06_filename):
    """Call Anthropic API to generate simulation report."""
    try:
        import anthropic
    except ImportError:
        print("ERROR: anthropic package not installed. Run: pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = (
        "You are a Nastran simulation analyst. Analyze ONLY the F06 content "
        "provided to you in this message. Do not use any outside knowledge about "
        "Nastran, spacecraft, or structural analysis. If the data does not support "
        "a conclusion, say so explicitly. Never invent frequencies, results, or "
        "conclusions not present in the provided data. Flag any FATAL errors, "
        "list natural frequencies, summarize random response results, and state "
        "whether the model is healthy and DBALL-ready."
    )

    user_prompt = (
        f"Analyze this Nastran F06 output file ({f06_filename}) and produce a "
        "simulation report with these sections:\n\n"
        "1. **Model Summary** — nodes, elements, CBUSH count, boundary conditions "
        "parsed from the F06\n"
        "2. **Natural Frequencies** — first 10 modes with frequencies in Hz\n"
        "3. **Warnings and Fatals** — any FATAL or WARNING messages from the F06\n"
        "4. **DBALL Chain Status** — did SOL 103 and/or SOL 111 complete cleanly\n"
        "5. **Random Response Summary** — peak PSD values, dominant frequencies "
        "(if present)\n"
        "6. **Health Assessment** — is this FEM ready for the super workflow?\n\n"
        "--- BEGIN F06 CONTENT ---\n"
        f"{f06_content}\n"
        "--- END F06 CONTENT ---"
    )

    print(f"Calling Anthropic API (model: claude-sonnet-4-20250514)...")
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )

    return message.content[0].text


def main():
    parser = argparse.ArgumentParser(description="Generate LLM simulation report from Nastran F06")
    parser.add_argument('--run-folder', help='Path to timestamped run folder')
    parser.add_argument('--f06', help='Path to specific F06 file')
    parser.add_argument('--output', help='Output path for simulation_report.md')
    args = parser.parse_args()

    # Determine F06 file(s) and output path
    if args.run_folder:
        f06_files = find_f06_files(args.run_folder)
        output_path = args.output or os.path.join(args.run_folder, 'simulation_report.md')
    elif args.f06:
        f06_files = [args.f06]
        output_path = args.output or os.path.join(os.path.dirname(args.f06), 'simulation_report.md')
    else:
        print("ERROR: Specify --run-folder or --f06")
        sys.exit(1)

    if not f06_files:
        print("ERROR: No F06 files found")
        sys.exit(1)

    print(f"Found {len(f06_files)} F06 file(s)")

    # Combine F06 content from all files
    all_content = []
    for f06_path in f06_files:
        fname = os.path.basename(f06_path)
        print(f"  Reading: {fname}")
        content = extract_f06_summary(f06_path)
        all_content.append(f"=== {fname} ===\n{content}")

    combined_content = '\n\n'.join(all_content)
    combined_filename = ', '.join(os.path.basename(f) for f in f06_files)

    # Generate report
    report = generate_report(combined_content, combined_filename)

    # Write report
    with open(output_path, 'w') as f:
        f.write(f"# Nastran Simulation Report\n\n")
        f.write(f"**Generated:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**F06 Files:** {combined_filename}  \n")
        f.write(f"**Generator:** Claude (Anthropic API, temperature=0)  \n\n")
        f.write("---\n\n")
        f.write(report)
        f.write("\n")

    print(f"\nReport written to: {output_path}")

    # Write path to GITHUB_OUTPUT if available
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"REPORT_PATH={output_path}\n")


if __name__ == '__main__':
    main()
