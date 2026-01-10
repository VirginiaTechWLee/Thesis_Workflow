"""
HEEDS Study Runner - Driver Script for Batch Execution

This script opens an existing .heeds project and runs the study in batch mode.
It is designed to be executed through HEEDSMDO.exe, not standalone Python.

Usage:
    HEEDSMDO.exe -b -script "run_study.py" -project "path/to/study.heeds" [-study "Study_1"]

Arguments (accessed via HEEDS.app().data()):
    -project    Path to the .heeds project file (required)
    -study      Name of the study to run (default: "Study_1")
    -timeout    Maximum runtime in minutes (default: 60)

Author: Wayne Lee (Virginia Tech)
"""

import time
import sys

# Import HEEDS module (only available when run through HEEDSMDO.exe)
try:
    import HEEDS
    print("HEEDS module loaded successfully!")
except ImportError as e:
    print(f"ERROR: HEEDS module not available: {e}")
    print("This script must be run through HEEDSMDO.exe with -script flag")
    sys.exit(1)


def main():
    """Main entry point for running HEEDS study."""
    
    app = HEEDS.app()
    
    # Get command line arguments via HEEDS API
    project_path = app.data("-project")
    study_name = app.data("-study") or "Study_1"
    timeout_str = app.data("-timeout") or "60"
    
    try:
        timeout_minutes = int(timeout_str)
    except (ValueError, TypeError):
        timeout_minutes = 60
    
    print("=" * 60)
    print("HEEDS Study Runner")
    print("=" * 60)
    print(f"Project path: {project_path}")
    print(f"Study name:   {study_name}")
    print(f"Timeout:      {timeout_minutes} minutes")
    print("=" * 60)
    
    # Validate project path
    if not project_path:
        print("ERROR: No project path provided!")
        print("Usage: HEEDSMDO.exe -b -script run_study.py -project path/to/study.heeds")
        return 1
    
    # Open the project
    print(f"\nOpening project: {project_path}")
    try:
        project = HEEDS.openProject(project_path)
        print("Project opened successfully!")
    except Exception as e:
        print(f"ERROR: Failed to open project: {e}")
        return 1
    
    # Get the study
    print(f"\nGetting study: {study_name}")
    try:
        study = project.study(study_name)
        print(f"Study '{study_name}' found!")
    except Exception as e:
        print(f"ERROR: Failed to get study '{study_name}': {e}")
        print("Available studies may be listed in the project.")
        return 1
    
    # Start the study run
    print("\nStarting study run...")
    try:
        study.run()
        print("Study started!")
    except Exception as e:
        print(f"ERROR: Failed to start study: {e}")
        return 1
    
    # Monitor progress
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    check_interval = 30  # seconds
    
    print(f"\nMonitoring study progress (checking every {check_interval}s)...")
    print("-" * 40)
    
    while True:
        elapsed = time.time() - start_time
        elapsed_min = elapsed / 60
        
        # Check if study is still running
        try:
            is_running = study.isRunning()
        except Exception as e:
            print(f"WARNING: Could not check study status: {e}")
            is_running = False
        
        if not is_running:
            print(f"\nStudy completed after {elapsed_min:.1f} minutes!")
            break
        
        # Check timeout
        if elapsed > timeout_seconds:
            print(f"\nWARNING: Study timed out after {timeout_minutes} minutes!")
            print("Study may still be running in the background.")
            break
        
        # Progress update
        print(f"  [{elapsed_min:5.1f} min] Study still running...")
        time.sleep(check_interval)
    
    print("-" * 40)
    
    # Save project (captures any results)
    print("\nSaving project...")
    try:
        project.save()
        print("Project saved successfully!")
    except Exception as e:
        print(f"WARNING: Could not save project: {e}")
    
    # Summary
    print("\n" + "=" * 60)
    print("HEEDS Study Runner - Complete")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
