"""
Generate HEEDS Study for Bolt Looseness Detection

This script programmatically creates HEEDS MDO projects for parametric
studies of CBUSH bolt stiffness effects on structural dynamics.

Usage:
    # Run from HEEDS Python environment or with HEEDS API available
    python generate_heeds_study.py --study sweep --cases 72 --output my_study.heeds
    python generate_heeds_study.py --study monte_carlo --cases 1000 --output mc_study.heeds
    python generate_heeds_study.py --study doe --cases 100 --output doe_study.heeds

Study Types:
    sweep       - Single bolt sweep (72 cases: 9 bolts × 8 levels)
    doe         - Design of Experiments (Latin Hypercube, etc.)
    monte_carlo - Random sampling across parameter space
    optimization - Find worst-case bolt configuration

Author: Wayne Lee (Virginia Tech)
Thesis: ML-Based Bolt Looseness Detection via PSD Analysis
"""

import os
import sys
import argparse
from typing import List, Dict, Tuple, Optional

# Try to import HEEDS - will fail if not in HEEDS environment
try:
    import HEEDS
    HEEDS_AVAILABLE = True
except ImportError:
    HEEDS_AVAILABLE = False
    print("WARNING: HEEDS module not available. Running in config-only mode.")


# =============================================================================
# CONFIGURATION
# =============================================================================

# Stiffness level encoding (level 1-9 -> actual stiffness)
STIFFNESS_LEVELS = {
    1: 1e4,    # loosest
    2: 1e5,
    3: 1e6,
    4: 1e7,
    5: 1e8,    # driving CBUSH K4 level
    6: 1e9,
    7: 1e10,
    8: 1e11,
    9: 1e12,   # healthy/baseline
}

# Parameter ranges
STIFFNESS_MIN = 1e4      # Loosest possible
STIFFNESS_MAX = 1e14     # Tightest possible
STIFFNESS_BASELINE = 1e12  # Healthy bolt

# Bolt configuration
NUM_BOLTS = 10
DRIVING_BOLT = 1         # Bolt 1 is the driving CBUSH (fixed K4=1e8)
VARIABLE_BOLTS = list(range(2, 11))  # Bolts 2-10 are variable

# Output nodes for PSD extraction
OUTPUT_NODES = [1, 111, 222, 333, 444, 555, 666, 777, 888, 999, 1010, 1111]
OUTPUT_DOFS = ['T1', 'T2', 'T3']  # Translational DOFs

# File paths (relative to project folder)
BUSH_BLK_TEMPLATE = "Bush.blk"
FIXED_BASE_BEAM = "Fixed_base_beam.dat"
RANDOM_BEAM = "RandomBeamX.dat"
RECOVERIES_BLK = "Recoveries.blk"
OUTPUT_PCH = "randombeamx.pch"
OUTPUT_CSV_ACCEL = "acceleration_results.csv"
OUTPUT_CSV_DISP = "displacement_results.csv"


# =============================================================================
# BUSH.BLK GENERATION
# =============================================================================

def float_to_nastran(value: float) -> str:
    """Convert float to Nastran shorthand notation (e.g., 1e8 -> '1.+8')."""
    if value == 0:
        return "0.0"
    
    exp = 0
    v = abs(value)
    if v >= 1:
        while v >= 10:
            v /= 10
            exp += 1
    else:
        while v < 1:
            v *= 10
            exp -= 1
    
    mantissa = value / (10 ** exp)
    
    if exp >= 0:
        return f"{mantissa:.6g}+{exp}"
    else:
        return f"{mantissa:.6g}{exp}"


def generate_bush_blk_content(bolt_stiffnesses: Dict[int, Tuple[float, float, float]]) -> str:
    """
    Generate Bush.blk content for given bolt stiffnesses.
    
    Args:
        bolt_stiffnesses: Dict mapping bolt_id (1-10) to (K4, K5, K6) tuple
        
    Returns:
        String content for Bush.blk file
    """
    K_TRANS = "1.+6"  # Translational stiffness (K1, K2, K3)
    
    lines = []
    for bolt_id in range(1, 11):
        if bolt_id in bolt_stiffnesses:
            k4, k5, k6 = bolt_stiffnesses[bolt_id]
            k4_str = float_to_nastran(k4)
            k5_str = float_to_nastran(k5)
            k6_str = float_to_nastran(k6)
        elif bolt_id == DRIVING_BOLT:
            # Driving CBUSH - fixed configuration
            k4_str, k5_str, k6_str = "1.+8", "1.+12", "1.+12"
        else:
            # Healthy bolt
            k4_str, k5_str, k6_str = "1.+12", "1.+12", "1.+12"
        
        line = f"PBUSH   {bolt_id}       K       {K_TRANS}    {K_TRANS}    {K_TRANS}    {k4_str}    {k5_str}    {k6_str}"
        lines.append(line)
    
    return "\n".join(lines) + "\n"


# =============================================================================
# HEEDS PROJECT GENERATION
# =============================================================================

class HEEDSStudyGenerator:
    """Generate HEEDS MDO projects for bolt looseness parametric studies."""
    
    def __init__(self, project_path: str, templates_dir: str):
        """
        Initialize the study generator.
        
        Args:
            project_path: Output path for .heeds file
            templates_dir: Directory containing template files
        """
        self.project_path = project_path
        self.templates_dir = templates_dir
        self.project = None
        self.process = None
        self.study = None
        self.analysis = None
        self.variables = {}
        self.responses = {}
        
    def create_project(self) -> bool:
        """Create a new HEEDS project."""
        if not HEEDS_AVAILABLE:
            print("ERROR: HEEDS module not available")
            return False
        
        # Create project with default Process and Study
        result = HEEDS.createProject()
        self.project, self.process, self.study, self.analysis = result
        
        # Save immediately to establish project folder
        self.project.save(self.project_path)
        
        print(f"Created project: {self.project_path}")
        return True
    
    def configure_analysis(self, analysis_command: str, analysis_name: str = "Nastran_PSD"):
        """
        Configure the analysis component.
        
        Args:
            analysis_command: Command/script to run Nastran analysis
            analysis_name: Name for the analysis
        """
        self.analysis.setName(analysis_name)
        self.analysis.set('anlCommand', analysis_command)
        
        print(f"Configured analysis: {analysis_name}")
        print(f"  Command: {analysis_command}")
    
    def add_input_files(self):
        """Add input files to the analysis."""
        # Add Bush.blk as the parameterized input
        bush_path = os.path.join(self.templates_dir, BUSH_BLK_TEMPLATE)
        self.bush_input = self.analysis.addInputFile(bush_path)
        
        # Add other required files (not parameterized)
        for filename in [FIXED_BASE_BEAM, RANDOM_BEAM, RECOVERIES_BLK]:
            filepath = os.path.join(self.templates_dir, filename)
            if os.path.exists(filepath):
                self.analysis.addInputFile(filepath)
        
        print("Added input files")
    
    def add_output_files(self):
        """Add output files for response extraction."""
        # PCH file for raw PSD data
        self.pch_output = self.analysis.addOutputFile(OUTPUT_PCH)
        
        # CSV files for processed results
        self.csv_accel = self.analysis.addOutputFile(OUTPUT_CSV_ACCEL)
        self.csv_disp = self.analysis.addOutputFile(OUTPUT_CSV_DISP)
        
        print("Added output files")
    
    def create_bolt_variables(self, 
                               bolts: List[int] = None,
                               vary_k4: bool = True,
                               vary_k5: bool = True, 
                               vary_k6: bool = True,
                               min_stiffness: float = STIFFNESS_MIN,
                               max_stiffness: float = STIFFNESS_MAX,
                               baseline: float = STIFFNESS_BASELINE,
                               coupled: bool = True):
        """
        Create variables for bolt stiffnesses.
        
        Args:
            bolts: List of bolt IDs to parameterize (default: 2-10)
            vary_k4, vary_k5, vary_k6: Which rotational DOFs to vary
            min_stiffness: Minimum stiffness value
            max_stiffness: Maximum stiffness value
            baseline: Baseline stiffness value
            coupled: If True, K4=K5=K6 for each bolt (reduces variables)
        """
        if bolts is None:
            bolts = VARIABLE_BOLTS
        
        for bolt_id in bolts:
            if coupled:
                # Single variable controls K4, K5, K6 together
                var_name = f"K_bolt{bolt_id}"
                var = self.project.createVariable(
                    var_name,
                    type='Continuous',
                    min=min_stiffness,
                    baseline=baseline,
                    max=max_stiffness,
                    comment=f"Coupled rotational stiffness for Bolt {bolt_id}"
                )
                self.variables[var_name] = var
                print(f"  Created variable: {var_name} [{min_stiffness:.0e} - {max_stiffness:.0e}]")
            else:
                # Separate variables for K4, K5, K6
                for k_name, vary in [('K4', vary_k4), ('K5', vary_k5), ('K6', vary_k6)]:
                    if vary:
                        var_name = f"{k_name}_bolt{bolt_id}"
                        var = self.project.createVariable(
                            var_name,
                            type='Continuous',
                            min=min_stiffness,
                            baseline=baseline,
                            max=max_stiffness,
                            comment=f"{k_name} stiffness for Bolt {bolt_id}"
                        )
                        self.variables[var_name] = var
                        print(f"  Created variable: {var_name}")
        
        print(f"Created {len(self.variables)} variables")
    
    def create_discrete_bolt_variables(self,
                                        bolts: List[int] = None,
                                        levels: List[int] = None):
        """
        Create discrete variables for bolt stiffnesses (for sweep studies).
        
        Args:
            bolts: List of bolt IDs to parameterize
            levels: List of stiffness levels (1-9)
        """
        if bolts is None:
            bolts = VARIABLE_BOLTS
        if levels is None:
            levels = list(range(1, 9))  # Levels 1-8
        
        # Create discrete set for stiffness levels
        stiffness_values = [str(STIFFNESS_LEVELS[level]) for level in levels]
        discrete_set = self.project.createAttribute('StiffnessLevels', HEEDS.DiscreteSet)
        discrete_set.setItems(*stiffness_values)
        
        for bolt_id in bolts:
            var_name = f"K_bolt{bolt_id}"
            var = self.project.createVariable(
                var_name,
                type='Discrete',
                set=discrete_set,
                comment=f"Stiffness level for Bolt {bolt_id}"
            )
            self.variables[var_name] = var
        
        print(f"Created {len(self.variables)} discrete variables")
    
    def tag_bush_input(self, coupled: bool = True):
        """
        Tag variables to Bush.blk input file.
        
        The Bush.blk format is:
        PBUSH   ID      K       K1      K2      K3      K4      K5      K6
        Col:    1-8     9-16    17-24   25-32   33-40   41-48   49-56   57-64
        
        Args:
            coupled: If True, same variable tags K4, K5, K6
        """
        # Bush.blk uses fixed-width Nastran format
        # Each row is a bolt, columns are:
        # 1-8: PBUSH, 9-16: ID, 17-24: K, 25-32: K1, 33-40: K2, 41-48: K3, 49-56: K4, 57-64: K5, 65-72: K6
        
        for bolt_id in VARIABLE_BOLTS:
            row = bolt_id  # Row number matches bolt ID
            
            if coupled:
                var_name = f"K_bolt{bolt_id}"
                if var_name in self.variables:
                    var = self.variables[var_name]
                    # Tag K4 (column 49-56), K5 (57-64), K6 (65-72)
                    self.bush_input.addTag(row, 49, var)  # K4
                    self.bush_input.addTag(row, 57, var)  # K5
                    self.bush_input.addTag(row, 65, var)  # K6
            else:
                for k_idx, (k_name, col) in enumerate([('K4', 49), ('K5', 57), ('K6', 65)]):
                    var_name = f"{k_name}_bolt{bolt_id}"
                    if var_name in self.variables:
                        self.bush_input.addTag(row, col, self.variables[var_name])
        
        print("Tagged Bush.blk input file")
    
    def create_responses(self, nodes: List[int] = None, dofs: List[str] = None):
        """
        Create response variables for PSD outputs.
        
        Args:
            nodes: List of node IDs to extract
            dofs: List of DOF names (T1, T2, T3, R1, R2, R3)
        """
        if nodes is None:
            nodes = OUTPUT_NODES
        if dofs is None:
            dofs = OUTPUT_DOFS
        
        # Create responses for each node/DOF combination
        for node in nodes:
            for dof in dofs:
                # Area under PSD curve
                resp_area = self.project.createResponse(f"ACCE_{node}_{dof}_Area")
                self.responses[f"ACCE_{node}_{dof}_Area"] = resp_area
                
                # Peak frequencies (top 3)
                for i in range(1, 4):
                    resp_freq = self.project.createResponse(f"ACCE_{node}_{dof}_Freq{i}")
                    resp_psd = self.project.createResponse(f"ACCE_{node}_{dof}_PSD{i}")
                    self.responses[f"ACCE_{node}_{dof}_Freq{i}"] = resp_freq
                    self.responses[f"ACCE_{node}_{dof}_PSD{i}"] = resp_psd
        
        print(f"Created {len(self.responses)} responses")
    
    def tag_csv_output(self):
        """Tag responses to CSV output file for extraction."""
        # The CSV format from Pch_TO_CSV2.py has:
        # Row 1: Header (Measurement, Node_1, Node_111, ...)
        # Row 2+: Data rows (ACCE_T1_Area, value, value, ...)
        
        # This depends on the exact CSV format - may need adjustment
        # For now, we'll use row-column indexing
        
        row = 2  # Start after header
        for resp_name, resp in self.responses.items():
            # Find the column for this response
            # This is a simplified approach - real implementation needs CSV parsing
            self.csv_accel.addTag(row, 1, resp)
            row += 1
        
        print("Tagged CSV output file")
    
    def configure_study(self,
                        study_type: str = 'DOE',
                        num_evals: int = 72,
                        method: str = 'LatinHypercube',
                        study_name: str = 'bolt_study'):
        """
        Configure the study parameters.
        
        Args:
            study_type: 'DOE', 'OPT', or 'Exploration'
            num_evals: Number of evaluations to run
            method: Algorithm (SHERPA, LatinHypercube, FullFactorial, MonteCarlo, etc.)
            study_name: Name for the study
        """
        self.study.setName(study_name)
        self.study.set('strAgentType', study_type)
        self.study.set('numEvals', num_evals)
        
        if study_type == 'DOE':
            self.study.set('method', method)
        elif study_type == 'OPT':
            self.study.set('method', 'SHERPA')
        
        # Save all designs for ML training
        self.study.set('saveDesigns', 'All')
        
        # Enable script execution for post-processing
        self.study.set('RunOpt_ScriptExecution', True)
        
        print(f"Configured study: {study_name}")
        print(f"  Type: {study_type}")
        print(f"  Method: {method}")
        print(f"  Evaluations: {num_evals}")
    
    def add_success_condition(self):
        """Add condition to check for successful Nastran run."""
        cond = self.project.createAttribute('nastran_success', HEEDS.Condition)
        # Check that the PCH file contains expected output
        cond.addFileContainsItem(findRef=self.pch_output, findText='$ACCE')
        self.analysis.set('condRef#success', cond)
        
        print("Added success condition")
    
    def validate_and_save(self) -> bool:
        """Validate the study setup and save the project."""
        ok = self.study.checkAndReport()
        if ok:
            self.project.save(self.project_path)
            print(f"Project saved: {self.project_path}")
        else:
            print("ERROR: Study has setup errors")
            HEEDS.logMessage("Study validation failed")
        
        return ok
    
    def generate_sweep_study(self, output_path: str = None):
        """
        Generate a single-bolt sweep study (72 cases).
        
        This creates a study where one bolt at a time is varied through
        8 stiffness levels, while all other bolts remain healthy.
        """
        if output_path:
            self.project_path = output_path
        
        self.create_project()
        self.configure_analysis("FBM_TO_DBALL.bat")  # Batch file for Nastran
        self.add_input_files()
        self.add_output_files()
        self.create_discrete_bolt_variables()
        self.tag_bush_input()
        self.create_responses()
        self.tag_csv_output()
        self.add_success_condition()
        self.configure_study(
            study_type='DOE',
            num_evals=72,
            method='FullFactorial',
            study_name='single_bolt_sweep'
        )
        return self.validate_and_save()
    
    def generate_doe_study(self, num_cases: int = 100, output_path: str = None):
        """
        Generate a DOE study with Latin Hypercube sampling.
        """
        if output_path:
            self.project_path = output_path
        
        self.create_project()
        self.configure_analysis("FBM_TO_DBALL.bat")
        self.add_input_files()
        self.add_output_files()
        self.create_bolt_variables(coupled=True)  # Continuous variables
        self.tag_bush_input()
        self.create_responses()
        self.tag_csv_output()
        self.add_success_condition()
        self.configure_study(
            study_type='DOE',
            num_evals=num_cases,
            method='LatinHypercube',
            study_name='doe_study'
        )
        return self.validate_and_save()
    
    def generate_monte_carlo_study(self, num_cases: int = 1000, output_path: str = None):
        """
        Generate a Monte Carlo study with random sampling.
        """
        if output_path:
            self.project_path = output_path
        
        self.create_project()
        self.configure_analysis("FBM_TO_DBALL.bat")
        self.add_input_files()
        self.add_output_files()
        self.create_bolt_variables(coupled=True)
        self.tag_bush_input()
        self.create_responses()
        self.tag_csv_output()
        self.add_success_condition()
        self.configure_study(
            study_type='DOE',
            num_evals=num_cases,
            method='MonteCarlo',
            study_name='monte_carlo_study'
        )
        return self.validate_and_save()


# =============================================================================
# STANDALONE CONFIGURATION GENERATOR (No HEEDS Required)
# =============================================================================

def generate_study_config(study_type: str, num_cases: int, output_file: str):
    """
    Generate a JSON configuration file for study parameters.
    This can be used when HEEDS API is not available.
    """
    import json
    
    config = {
        "study_type": study_type,
        "num_cases": num_cases,
        "bolts": {
            "driving_bolt": DRIVING_BOLT,
            "variable_bolts": VARIABLE_BOLTS,
            "stiffness_min": STIFFNESS_MIN,
            "stiffness_max": STIFFNESS_MAX,
            "stiffness_baseline": STIFFNESS_BASELINE,
        },
        "stiffness_levels": STIFFNESS_LEVELS,
        "output_nodes": OUTPUT_NODES,
        "output_dofs": OUTPUT_DOFS,
        "files": {
            "bush_blk": BUSH_BLK_TEMPLATE,
            "fixed_base_beam": FIXED_BASE_BEAM,
            "random_beam": RANDOM_BEAM,
            "output_pch": OUTPUT_PCH,
            "output_csv_accel": OUTPUT_CSV_ACCEL,
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"Generated config: {output_file}")
    return config


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Generate HEEDS studies for bolt looseness detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_heeds_study.py --study sweep --output sweep_study.heeds
  python generate_heeds_study.py --study doe --cases 100 --output doe_study.heeds
  python generate_heeds_study.py --study monte_carlo --cases 1000 --output mc_study.heeds
  python generate_heeds_study.py --config-only --study sweep --output config.json
        """
    )
    
    parser.add_argument('--study', type=str, required=True,
                        choices=['sweep', 'doe', 'monte_carlo'],
                        help='Study type to generate')
    parser.add_argument('--cases', type=int, default=72,
                        help='Number of cases (default: 72 for sweep, varies for others)')
    parser.add_argument('--output', '-o', type=str, required=True,
                        help='Output file path (.heeds or .json)')
    parser.add_argument('--templates', type=str, default='templates',
                        help='Templates directory path')
    parser.add_argument('--config-only', action='store_true',
                        help='Generate config JSON only (no HEEDS required)')
    
    args = parser.parse_args()
    
    if args.config_only:
        # Generate JSON config without HEEDS
        generate_study_config(args.study, args.cases, args.output)
        return 0
    
    if not HEEDS_AVAILABLE:
        print("ERROR: HEEDS module not available. Use --config-only for standalone mode.")
        return 1
    
    # Create study generator
    generator = HEEDSStudyGenerator(args.output, args.templates)
    
    # Generate appropriate study type
    if args.study == 'sweep':
        ok = generator.generate_sweep_study()
    elif args.study == 'doe':
        ok = generator.generate_doe_study(args.cases)
    elif args.study == 'monte_carlo':
        ok = generator.generate_monte_carlo_study(args.cases)
    else:
        print(f"Unknown study type: {args.study}")
        return 1
    
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
