"""
Generate FBM_TO_DBALL.bat from config.yaml.

This creates the Nastran solver chain batch script with paths from config
instead of hardcoded values.

Usage:
    python pipeline/generate_bat.py
    python pipeline/generate_bat.py --output path/to/FBM_TO_DBALL.bat
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config


def generate_bat(config_path=None, output_path='FBM_TO_DBALL.bat'):
    """Generate FBM_TO_DBALL.bat from config.yaml."""
    config = load_config(config_path)

    nastran = config['paths']['nastran_exe']
    python_exe = config['paths']['python_exe']
    model = config['files']['structural_model']
    random_resp = config['files']['random_response']
    postprocessor = config['files']['postprocessor']

    content = (
        '@echo off\r\n'
        'REM Auto-generated from fem_input/config.yaml - DO NOT EDIT\r\n'
        f'REM Model: {model}\r\n'
        f'"{nastran}" {model} scratch=no\r\n'
        'IF ERRORLEVEL 1 (\r\n'
        '    echo The first Nastran command failed. Exiting.\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'echo Waiting for 10 seconds before proceeding to the next command...\r\n'
        'timeout /t 10 /nobreak >nul\r\n'
        f'"{nastran}" {random_resp}\r\n'
        'IF ERRORLEVEL 1 (\r\n'
        '    echo The second Nastran command failed. Exiting.\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'echo Both Nastran commands completed successfully.\r\n'
        'REM Post-process PCH to CSV\r\n'
        'echo Running post-processor...\r\n'
        f'"{python_exe}" {postprocessor}\r\n'
        'IF ERRORLEVEL 1 (\r\n'
        '    echo Post-processing failed. Exiting.\r\n'
        '    exit /b 1\r\n'
        ')\r\n'
        'echo Post-processing completed successfully.\r\n'
    )

    with open(output_path, 'w', newline='') as f:
        f.write(content)

    print(f"Generated: {output_path}")
    print(f"  Nastran: {nastran}")
    print(f"  Model: {model}")
    print(f"  Post-processor: {postprocessor}")
    return output_path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate FBM_TO_DBALL.bat from config")
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--output', '-o', default='FBM_TO_DBALL.bat')
    args = parser.parse_args()
    generate_bat(args.config, args.output)
