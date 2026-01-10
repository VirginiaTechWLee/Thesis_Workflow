#!/usr/bin/env python3
"""
HEEDS Project Generator for Bolt Looseness Detection Study

Generates a complete .heeds XML file for diagonal bolt stiffness sweep studies.
Configurable via command line arguments or config file.

Author: Wayne Lee (Virginia Tech)
Date: January 2026
"""

import argparse
import json
import os
from datetime import datetime

# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================

DEFAULT_CONFIG = {
    # Study parameters
    "study_type": "diagonal",  # Options: "diagonal", "single_bolt", "full_factorial", "latin_hypercube"
    "num_bolts": 3,
    "dofs": ["K4", "K5", "K6"],
    "stiffness_levels": [1e4, 1e8, 1e12, 1e14],  # 4 levels: loose to tight
    "baseline_stiffness": 1e14,  # Healthy bolt stiffness
    
    # For single_bolt study type
    "target_bolt": 1,  # Which bolt to vary (others at baseline)
    
    # For latin_hypercube study type
    "num_samples": 50,  # Number of LHS samples
    
    # Response extraction nodes
    "nodes": [1, 111, 222, 333, 444, 555, 666, 777, 888, 999, 1010, 1111],
    
    # Response metrics
    "accel_metrics": ["Area", "Frequency_1", "PSD_1", "Frequency_2", "PSD_2", "Frequency_3", "PSD_3"],
    "disp_metrics": ["Area", "Frequency_1", "DISP_1", "Frequency_2", "DISP_2", "Frequency_3", "DISP_3"],
    "accel_dofs": ["T1", "T2", "T3"],
    "disp_dofs": ["T1", "T2", "T3", "R1", "R2", "R3"],
    
    # File paths (UPDATE THESE FOR YOUR SYSTEM)
    "paths": {
        "nastran_exe": r"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe",
        "working_dir": r"C:\Users\waynelee\Documents",
        "input_files": {
            "model": "Fixed_base_beam.dat",
            "batch": "FBM_TO_DBALL.bat",
            "bush_template": "Bush.blk",
            "post_processor": "Pch_TO_CSV2.py",
            "random_load": "RandomBeamX.dat",
            "recoveries": "Recoveries.blk",
            "accel_baseline": "acceleration_results_baseline.csv",
            "disp_baseline": "displacement_results_baseline.csv"
        }
    },
    
    # Output settings
    "output_file": "thesis_bolt_study.heeds",
    "study_name": "Bolt_Looseness_Diagonal_Sweep"
}


# =============================================================================
# HEEDS XML GENERATOR
# =============================================================================

class HEEDSProjectGenerator:
    """Generates HEEDS .heeds XML files for bolt looseness studies."""
    
    def __init__(self, config: dict):
        self.config = config
        self.study_type = config.get("study_type", "diagonal")
        self.num_bolts = config["num_bolts"]
        self.dofs = config["dofs"]
        self.stiffness_levels = config["stiffness_levels"]
        self.baseline = config["baseline_stiffness"]
        self.nodes = config["nodes"]
        self.paths = config["paths"]
        self.target_bolt = config.get("target_bolt", 1)
        self.num_samples = config.get("num_samples", 50)
        
    def generate(self) -> str:
        """Generate complete HEEDS XML content."""
        lines = []
        
        # XML Header
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append('<root>')
        lines.append('  <Project>')
        lines.append(f'    <!-- Generated: {datetime.now().isoformat()} -->')
        lines.append(f'    <!-- Study: {self.config["study_name"]} -->')
        lines.append(f'    <!-- Bolts: {self.num_bolts}, Levels: {len(self.stiffness_levels)} -->')
        lines.append('')
        
        # Variables section
        lines.extend(self._generate_variables())
        
        # Process/MDO section
        lines.extend(self._generate_process())
        
        # Responses section
        lines.extend(self._generate_responses())
        
        # UserDesignSets section (diagonal sweep)
        lines.extend(self._generate_user_design_sets())
        
        # Close tags
        lines.append('  </Project>')
        lines.append('</root>')
        
        return '\n'.join(lines)
    
    def _generate_variables(self) -> list:
        """Generate variable definitions for each bolt DOF."""
        lines = []
        lines.append('    <!-- ===== VARIABLES ===== -->')
        lines.append('    <Variables>')
        
        for bolt in range(1, self.num_bolts + 1):
            for dof in self.dofs:
                var_name = f"{dof}_{bolt}"
                lines.append(f'      <Variable name="{var_name}" flags="2048" numInTags="1"/>')
        
        lines.append('    </Variables>')
        lines.append('')
        return lines
    
    def _generate_process(self) -> list:
        """Generate process/MDO section with analysis configuration."""
        lines = []
        working_dir = self.paths["working_dir"].replace("\\", "/")
        input_files = self.paths["input_files"]
        
        lines.append('    <!-- ===== PROCESS/ANALYSIS ===== -->')
        lines.append('    <Process name="Process_1" current="true" parallel="true">')
        lines.append('      <MDO name="Analysis_1" active="true" solver="General">')
        lines.append('        <Data type="MDO" resource="Local">')
        lines.append(f'          <anlCommand value="{input_files["batch"]}"/>')
        lines.append(f'          <primaryInput ref="HEEDS.Input.File.{input_files["model"]}"/>')
        lines.append(f'          <anlWorkingDir value="{working_dir}"/>')
        lines.append('        </Data>')
        lines.append('        <Inputs>')
        lines.append(f'          <Input type="file" path="{input_files["bush_template"]}">')
        
        # Generate tags for Bush.blk - each bolt has K4, K5, K6 on specific rows
        for bolt in range(1, self.num_bolts + 1):
            row = 2 * bolt - 1  # Rows: 1, 3, 5, 7, ...
            lines.append(f'            <Tag variable="K4_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="6" charPos="48"/>')
            lines.append(f'            <Tag variable="K5_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="7" charPos="56"/>')
            lines.append(f'            <Tag variable="K6_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="8" charPos="64"/>')
        
        lines.append('          </Input>')
        lines.append('        </Inputs>')
        
        # Output files
        lines.append('        <Outputs>')
        lines.append('          <Output type="file" path="acceleration_results.csv"/>')
        lines.append('          <Output type="file" path="displacement_results.csv"/>')
        lines.append('          <Output type="file" path="acceleration_results_delta.csv"/>')
        lines.append('          <Output type="file" path="displacement_results_delta.csv"/>')
        lines.append('        </Outputs>')
        
        lines.append('      </MDO>')
        lines.append('    </Process>')
        lines.append('')
        return lines
    
    def _generate_responses(self) -> list:
        """Generate response definitions for all nodes and metrics."""
        lines = []
        lines.append('    <!-- ===== RESPONSES ===== -->')
        lines.append('    <Responses>')
        
        accel_metrics = self.config["accel_metrics"]
        disp_metrics = self.config["disp_metrics"]
        accel_dofs = self.config["accel_dofs"]
        disp_dofs = self.config["disp_dofs"]
        
        # Acceleration responses
        for node in self.nodes:
            for dof in accel_dofs:
                for metric in accel_metrics:
                    resp_name = f"ACCE_{dof}_{metric}_Node_{node}"
                    lines.append(f'      <Response name="{resp_name}"/>')
        
        # Acceleration Delta responses
        for node in self.nodes:
            for dof in accel_dofs:
                for metric in accel_metrics:
                    resp_name = f"ACCE_{dof}_{metric}_Node_{node}_Delta"
                    lines.append(f'      <Response name="{resp_name}"/>')
        
        # Displacement responses
        for node in self.nodes:
            for dof in disp_dofs:
                for metric in disp_metrics:
                    resp_name = f"DISP_{dof}_{metric}_Node_{node}"
                    lines.append(f'      <Response name="{resp_name}"/>')
        
        # Displacement Delta responses
        for node in self.nodes:
            for dof in disp_dofs:
                for metric in disp_metrics:
                    resp_name = f"DISP_{dof}_{metric}_Node_{node}_Delta"
                    lines.append(f'      <Response name="{resp_name}"/>')
        
        lines.append('    </Responses>')
        lines.append('')
        return lines
    
    def _generate_user_design_sets(self) -> list:
        """Generate UserDesignSets based on study type."""
        if self.study_type == "diagonal":
            return self._generate_diagonal_sweep()
        elif self.study_type == "single_bolt":
            return self._generate_single_bolt_sweep()
        elif self.study_type == "full_factorial":
            return self._generate_full_factorial()
        elif self.study_type == "latin_hypercube":
            return self._generate_latin_hypercube()
        elif self.study_type == "pairwise":
            return self._generate_pairwise()
        else:
            raise ValueError(f"Unknown study type: {self.study_type}")
    
    def _generate_diagonal_sweep(self) -> list:
        """Diagonal sweep: For each bolt, sweep through stiffness levels
        while keeping all other bolts at baseline (healthy) stiffness.
        """
        lines = []
        lines.append('    <!-- ===== USER DESIGN SETS (Diagonal Sweep) ===== -->')
        
        set_num = 1
        
        for bolt in range(1, self.num_bolts + 1):
            lines.append(f'    <!-- Bolt {bolt} sweep -->')
            lines.append(f'    <UserDesignSet name="Set_{set_num}_Bolt_{bolt}">')
            lines.append('      <Designs>')
            
            design_num = 1
            for level in self.stiffness_levels:
                lines.append(f'        <Design id="{design_num}">')
                
                # Set all bolts
                for b in range(1, self.num_bolts + 1):
                    for dof in self.dofs:
                        # Current bolt gets the sweep level, others get baseline
                        value = level if b == bolt else self.baseline
                        lines.append(f'          <Var name="{dof}_{b}" value="{value:.6e}"/>')
                
                lines.append('        </Design>')
                design_num += 1
            
            lines.append('      </Designs>')
            lines.append('    </UserDesignSet>')
            lines.append('')
            set_num += 1
        
        # Calculate total evaluations
        total_evals = self.num_bolts * len(self.stiffness_levels)
        lines.append(f'    <!-- Total evaluations: {total_evals} -->')
        lines.append('')
        
        return lines
    
    def _generate_single_bolt_sweep(self) -> list:
        """Single bolt sweep: Vary only one specified bolt through all levels."""
        lines = []
        bolt = self.target_bolt
        lines.append(f'    <!-- ===== USER DESIGN SETS (Single Bolt {bolt} Sweep) ===== -->')
        lines.append(f'    <UserDesignSet name="Set_1_Bolt_{bolt}_Sweep">')
        lines.append('      <Designs>')
        
        design_num = 1
        for level in self.stiffness_levels:
            lines.append(f'        <Design id="{design_num}">')
            
            for b in range(1, self.num_bolts + 1):
                for dof in self.dofs:
                    value = level if b == bolt else self.baseline
                    lines.append(f'          <Var name="{dof}_{b}" value="{value:.6e}"/>')
            
            lines.append('        </Design>')
            design_num += 1
        
        lines.append('      </Designs>')
        lines.append('    </UserDesignSet>')
        lines.append(f'    <!-- Total evaluations: {len(self.stiffness_levels)} -->')
        lines.append('')
        
        return lines
    
    def _generate_full_factorial(self) -> list:
        """Full factorial: All combinations of all bolts at all levels.
        WARNING: Grows exponentially! 3 bolts × 4 levels = 4^3 = 64 runs
        """
        import itertools
        
        lines = []
        lines.append('    <!-- ===== USER DESIGN SETS (Full Factorial) ===== -->')
        lines.append('    <!-- WARNING: Exponential growth - use carefully! -->')
        
        # Generate all combinations
        bolt_levels = [self.stiffness_levels for _ in range(self.num_bolts)]
        combinations = list(itertools.product(*bolt_levels))
        
        # Split into chunks of 64 designs per set (HEEDS limit)
        chunk_size = 64
        set_num = 1
        
        for chunk_start in range(0, len(combinations), chunk_size):
            chunk = combinations[chunk_start:chunk_start + chunk_size]
            
            lines.append(f'    <UserDesignSet name="Set_{set_num}_FullFactorial">')
            lines.append('      <Designs>')
            
            for design_num, combo in enumerate(chunk, 1):
                lines.append(f'        <Design id="{design_num}">')
                
                for bolt_idx, level in enumerate(combo):
                    bolt = bolt_idx + 1
                    for dof in self.dofs:
                        lines.append(f'          <Var name="{dof}_{bolt}" value="{level:.6e}"/>')
                
                lines.append('        </Design>')
            
            lines.append('      </Designs>')
            lines.append('    </UserDesignSet>')
            lines.append('')
            set_num += 1
        
        lines.append(f'    <!-- Total evaluations: {len(combinations)} -->')
        lines.append('')
        
        return lines
    
    def _generate_latin_hypercube(self) -> list:
        """Latin Hypercube Sampling: Space-filling design for efficient exploration."""
        import random
        
        lines = []
        lines.append('    <!-- ===== USER DESIGN SETS (Latin Hypercube Sampling) ===== -->')
        
        n_samples = self.num_samples
        n_vars = self.num_bolts  # One stiffness per bolt (all DOFs same)
        
        # Generate LHS indices
        min_stiff = min(self.stiffness_levels)
        max_stiff = max(self.stiffness_levels)
        
        # Create LHS samples (log scale for stiffness)
        import math
        log_min = math.log10(min_stiff)
        log_max = math.log10(max_stiff)
        
        # Simple LHS: divide each dimension into n_samples intervals
        samples = []
        for _ in range(n_samples):
            sample = []
            for _ in range(n_vars):
                # Random value in log space
                log_val = random.uniform(log_min, log_max)
                sample.append(10 ** log_val)
            samples.append(sample)
        
        # Split into chunks
        chunk_size = 64
        set_num = 1
        
        for chunk_start in range(0, len(samples), chunk_size):
            chunk = samples[chunk_start:chunk_start + chunk_size]
            
            lines.append(f'    <UserDesignSet name="Set_{set_num}_LHS">')
            lines.append('      <Designs>')
            
            for design_num, sample in enumerate(chunk, 1):
                lines.append(f'        <Design id="{design_num}">')
                
                for bolt_idx, stiffness in enumerate(sample):
                    bolt = bolt_idx + 1
                    for dof in self.dofs:
                        lines.append(f'          <Var name="{dof}_{bolt}" value="{stiffness:.6e}"/>')
                
                lines.append('        </Design>')
            
            lines.append('      </Designs>')
            lines.append('    </UserDesignSet>')
            lines.append('')
            set_num += 1
        
        lines.append(f'    <!-- Total evaluations: {n_samples} -->')
        lines.append('')
        
        return lines
    
    def _generate_pairwise(self) -> list:
        """Pairwise: Test pairs of bolts at different levels.
        Useful for detecting interaction effects between bolts.
        """
        import itertools
        
        lines = []
        lines.append('    <!-- ===== USER DESIGN SETS (Pairwise Interactions) ===== -->')
        
        # Get all pairs of bolts
        bolt_pairs = list(itertools.combinations(range(1, self.num_bolts + 1), 2))
        
        set_num = 1
        total_designs = 0
        
        for bolt_a, bolt_b in bolt_pairs:
            lines.append(f'    <!-- Bolt {bolt_a} x Bolt {bolt_b} -->')
            lines.append(f'    <UserDesignSet name="Set_{set_num}_Bolt{bolt_a}_x_Bolt{bolt_b}">')
            lines.append('      <Designs>')
            
            design_num = 1
            for level_a in self.stiffness_levels:
                for level_b in self.stiffness_levels:
                    lines.append(f'        <Design id="{design_num}">')
                    
                    for b in range(1, self.num_bolts + 1):
                        for dof in self.dofs:
                            if b == bolt_a:
                                value = level_a
                            elif b == bolt_b:
                                value = level_b
                            else:
                                value = self.baseline
                            lines.append(f'          <Var name="{dof}_{b}" value="{value:.6e}"/>')
                    
                    lines.append('        </Design>')
                    design_num += 1
                    total_designs += 1
            
            lines.append('      </Designs>')
            lines.append('    </UserDesignSet>')
            lines.append('')
            set_num += 1
        
        lines.append(f'    <!-- Total evaluations: {total_designs} -->')
        lines.append('')
        
        return lines
    
    def get_study_summary(self) -> str:
        """Return a summary of the study configuration."""
        # Calculate total evaluations based on study type
        if self.study_type == "diagonal":
            total_evals = self.num_bolts * len(self.stiffness_levels)
        elif self.study_type == "single_bolt":
            total_evals = len(self.stiffness_levels)
        elif self.study_type == "full_factorial":
            total_evals = len(self.stiffness_levels) ** self.num_bolts
        elif self.study_type == "latin_hypercube":
            total_evals = self.num_samples
        elif self.study_type == "pairwise":
            from math import comb
            num_pairs = comb(self.num_bolts, 2)
            total_evals = num_pairs * (len(self.stiffness_levels) ** 2)
        else:
            total_evals = "unknown"
        
        study_descriptions = {
            "diagonal": "Vary one bolt at a time, others at baseline",
            "single_bolt": f"Vary only bolt {self.target_bolt}, others at baseline",
            "full_factorial": "All combinations of all bolts (WARNING: exponential!)",
            "latin_hypercube": "Space-filling random sampling",
            "pairwise": "Test all pairs of bolts for interaction effects"
        }
        
        summary = f"""
HEEDS Study Configuration Summary
==================================
Study Name: {self.config["study_name"]}
Study Type: {self.study_type}
Description: {study_descriptions.get(self.study_type, "Custom")}

Parameters:
  - Bolts: {self.num_bolts}
  - DOFs per bolt: {', '.join(self.dofs)}
  - Stiffness levels: {len(self.stiffness_levels)}
  - Levels: {[f'{l:.0e}' for l in self.stiffness_levels]}
  - Baseline (healthy): {self.baseline:.0e}

Response Extraction:
  - Nodes: {len(self.nodes)}
  - Accel DOFs: {', '.join(self.config['accel_dofs'])}
  - Disp DOFs: {', '.join(self.config['disp_dofs'])}

Evaluations:
  - Total Nastran runs: {total_evals}

Output: {self.config['output_file']}
"""
        return summary


# =============================================================================
# MAIN
# =============================================================================

def load_config(config_file: str) -> dict:
    """Load configuration from JSON file, merged with defaults."""
    config = DEFAULT_CONFIG.copy()
    
    if config_file and os.path.exists(config_file):
        with open(config_file, 'r') as f:
            user_config = json.load(f)
        
        # Deep merge user config into defaults
        for key, value in user_config.items():
            if isinstance(value, dict) and key in config:
                config[key].update(value)
            else:
                config[key] = value
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Generate HEEDS project file for bolt looseness study",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use defaults (3 bolts, 4 levels)
  python generate_heeds_project.py
  
  # Custom bolt count and levels
  python generate_heeds_project.py --bolts 5 --levels 1e4 1e6 1e8 1e10 1e12 1e14
  
  # Use config file
  python generate_heeds_project.py --config my_study_config.json
  
  # Specify output file
  python generate_heeds_project.py --output my_study.heeds
        """
    )
    
    parser.add_argument("--config", "-c", help="JSON config file path")
    parser.add_argument("--output", "-o", help="Output .heeds file path")
    parser.add_argument("--study-type", "-t", 
                        choices=["diagonal", "single_bolt", "full_factorial", "latin_hypercube", "pairwise"],
                        help="Type of study design")
    parser.add_argument("--bolts", "-b", type=int, help="Number of bolts")
    parser.add_argument("--levels", "-l", nargs="+", type=float, help="Stiffness levels (e.g., 1e4 1e8 1e12)")
    parser.add_argument("--baseline", type=float, help="Baseline (healthy) stiffness")
    parser.add_argument("--target-bolt", type=int, help="Target bolt for single_bolt study type")
    parser.add_argument("--samples", type=int, help="Number of samples for latin_hypercube study")
    parser.add_argument("--working-dir", "-w", help="HEEDS working directory")
    parser.add_argument("--nastran", help="Path to nastranw.exe")
    parser.add_argument("--summary", "-s", action="store_true", help="Print summary only, don't generate file")
    parser.add_argument("--print-config", action="store_true", help="Print default config as JSON")
    
    args = parser.parse_args()
    
    # Print default config if requested
    if args.print_config:
        print(json.dumps(DEFAULT_CONFIG, indent=2, default=str))
        return
    
    # Load config
    config = load_config(args.config)
    
    # Override with command line arguments
    if args.study_type:
        config["study_type"] = args.study_type
    if args.bolts:
        config["num_bolts"] = args.bolts
    if args.levels:
        config["stiffness_levels"] = args.levels
    if args.baseline:
        config["baseline_stiffness"] = args.baseline
    if args.target_bolt:
        config["target_bolt"] = args.target_bolt
    if args.samples:
        config["num_samples"] = args.samples
    if args.output:
        config["output_file"] = args.output
    if args.working_dir:
        config["paths"]["working_dir"] = args.working_dir
    if args.nastran:
        config["paths"]["nastran_exe"] = args.nastran
    
    # Generate
    generator = HEEDSProjectGenerator(config)
    
    # Print summary
    print(generator.get_study_summary())
    
    if args.summary:
        return
    
    # Generate XML
    xml_content = generator.generate()
    
    # Write output
    output_path = config["output_file"]
    with open(output_path, 'w') as f:
        f.write(xml_content)
    
    print(f"Generated: {output_path}")
    print(f"File size: {len(xml_content):,} bytes")


if __name__ == "__main__":
    main()
