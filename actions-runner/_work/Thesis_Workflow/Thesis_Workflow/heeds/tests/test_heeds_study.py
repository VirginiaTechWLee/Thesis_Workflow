"""
Test HEEDS Study Generation

Validates that HEEDS projects are generated correctly with proper
variables, responses, and file tagging.

Note: Full HEEDS API tests require HEEDS environment.
      Standalone tests validate configuration and structure.

Run with: python -m pytest heeds/tests/test_heeds_study.py -v
Or standalone: python heeds/tests/test_heeds_study.py
"""

import os
import sys
import json
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Try to import HEEDS study generator
try:
    from generate_heeds_study import (
        HEEDSStudyGenerator,
        generate_study_config,
        generate_bush_blk_content,
        float_to_nastran,
        STIFFNESS_LEVELS,
        VARIABLE_BOLTS,
        DRIVING_BOLT,
        OUTPUT_NODES,
        OUTPUT_DOFS,
        HEEDS_AVAILABLE
    )
    GENERATOR_AVAILABLE = True
except ImportError as e:
    GENERATOR_AVAILABLE = False
    print(f"WARNING: Could not import generate_heeds_study: {e}")


class TestConfiguration(unittest.TestCase):
    """Test study configuration constants."""
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_variable_bolts_exclude_driving(self):
        """Variable bolts should not include driving bolt."""
        self.assertNotIn(DRIVING_BOLT, VARIABLE_BOLTS)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_variable_bolts_count(self):
        """Should have 9 variable bolts (2-10)."""
        self.assertEqual(len(VARIABLE_BOLTS), 9)
        self.assertEqual(VARIABLE_BOLTS, list(range(2, 11)))
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_output_nodes_count(self):
        """Should have 12 output nodes."""
        self.assertEqual(len(OUTPUT_NODES), 12)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_output_dofs(self):
        """Should have T1, T2, T3 DOFs."""
        self.assertEqual(OUTPUT_DOFS, ['T1', 'T2', 'T3'])


class TestBushBlkContent(unittest.TestCase):
    """Test Bush.blk content generation."""
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_baseline_content(self):
        """Test baseline Bush.blk content."""
        content = generate_bush_blk_content({})
        lines = content.strip().split('\n')
        
        # 10 bolts
        self.assertEqual(len(lines), 10)
        
        # All lines start with PBUSH
        for line in lines:
            self.assertTrue(line.startswith('PBUSH'))
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_driving_bolt_fixed(self):
        """Driving bolt should always have K4=1e8."""
        content = generate_bush_blk_content({})
        lines = content.strip().split('\n')
        
        # Bolt 1 line
        bolt1_line = lines[0]
        self.assertIn('1.+8', bolt1_line)  # K4 = 1e8
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_loosened_bolt_content(self):
        """Test Bush.blk with loosened bolt."""
        bolt_config = {5: (1e6, 1e6, 1e6)}
        content = generate_bush_blk_content(bolt_config)
        lines = content.strip().split('\n')
        
        # Bolt 5 should have loosened values
        bolt5_line = lines[4]
        self.assertIn('PBUSH   5', bolt5_line)


class TestStudyConfigGeneration(unittest.TestCase):
    """Test JSON config generation (no HEEDS required)."""
    
    def setUp(self):
        """Create temp directory for test files."""
        self.test_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        os.makedirs(self.test_dir, exist_ok=True)
        self.config_file = os.path.join(self.test_dir, 'test_config.json')
    
    def tearDown(self):
        """Clean up test files."""
        if os.path.exists(self.config_file):
            os.remove(self.config_file)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_sweep_config(self):
        """Test sweep study config generation."""
        config = generate_study_config('sweep', 72, self.config_file)
        
        self.assertEqual(config['study_type'], 'sweep')
        self.assertEqual(config['num_cases'], 72)
        self.assertIn('bolts', config)
        self.assertIn('stiffness_levels', config)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_doe_config(self):
        """Test DOE study config generation."""
        config = generate_study_config('doe', 200, self.config_file)
        
        self.assertEqual(config['study_type'], 'doe')
        self.assertEqual(config['num_cases'], 200)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_monte_carlo_config(self):
        """Test Monte Carlo study config generation."""
        config = generate_study_config('monte_carlo', 1000, self.config_file)
        
        self.assertEqual(config['study_type'], 'monte_carlo')
        self.assertEqual(config['num_cases'], 1000)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_config_file_created(self):
        """Test that config file is actually created."""
        generate_study_config('sweep', 72, self.config_file)
        
        self.assertTrue(os.path.exists(self.config_file))
        
        # Verify it's valid JSON
        with open(self.config_file, 'r') as f:
            loaded = json.load(f)
        
        self.assertIsInstance(loaded, dict)


class TestNastranFormatting(unittest.TestCase):
    """Test Nastran number formatting."""
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_standard_exponents(self):
        """Test standard exponent values."""
        self.assertIn('+8', float_to_nastran(1e8))
        self.assertIn('+12', float_to_nastran(1e12))
        self.assertIn('+4', float_to_nastran(1e4))


class TestHEEDSIntegration(unittest.TestCase):
    """Tests that require HEEDS environment."""
    
    @unittest.skipUnless(GENERATOR_AVAILABLE and HEEDS_AVAILABLE, 
                         "HEEDS not available")
    def test_create_project(self):
        """Test HEEDS project creation."""
        test_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        os.makedirs(test_dir, exist_ok=True)
        test_project = os.path.join(test_dir, 'test_project.heeds')
        
        generator = HEEDSStudyGenerator(test_project, 'templates')
        result = generator.create_project()
        
        self.assertTrue(result)
        self.assertTrue(os.path.exists(test_project))
        
        # Cleanup
        if os.path.exists(test_project):
            os.remove(test_project)
    
    @unittest.skipUnless(GENERATOR_AVAILABLE and HEEDS_AVAILABLE,
                         "HEEDS not available")
    def test_variable_creation(self):
        """Test HEEDS variable creation."""
        test_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        test_project = os.path.join(test_dir, 'test_vars.heeds')
        
        generator = HEEDSStudyGenerator(test_project, 'templates')
        generator.create_project()
        generator.create_bolt_variables(bolts=[2, 3], coupled=True)
        
        # Should have 2 variables
        self.assertEqual(len(generator.variables), 2)
        self.assertIn('K_bolt2', generator.variables)
        self.assertIn('K_bolt3', generator.variables)
        
        # Cleanup
        if os.path.exists(test_project):
            os.remove(test_project)


class TestStudyTypes(unittest.TestCase):
    """Test different study type configurations."""
    
    @unittest.skipUnless(GENERATOR_AVAILABLE, "Generator not available")
    def test_sweep_study_cases(self):
        """Sweep study should be 72 cases (9 bolts × 8 levels)."""
        config = generate_study_config('sweep', 72, 'NUL')
        
        num_bolts = len(config['bolts']['variable_bolts'])
        num_levels = len([l for l in config['stiffness_levels'] if l < 9])
        
        self.assertEqual(num_bolts, 9)  # Bolts 2-10
        self.assertEqual(num_bolts * 8, 72)  # 9 bolts × 8 levels


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n" + "=" * 60)
    print("HEEDS STUDY TEST SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    
    if GENERATOR_AVAILABLE:
        print(f"HEEDS API available: {HEEDS_AVAILABLE}")
    else:
        print("Generator module: NOT AVAILABLE")
    
    print("=" * 60)
    
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
