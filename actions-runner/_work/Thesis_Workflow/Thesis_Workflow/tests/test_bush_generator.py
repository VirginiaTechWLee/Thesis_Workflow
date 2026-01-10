"""
Test Bush.blk Generation

Validates that Bush.blk files are generated correctly with proper
Nastran formatting and stiffness values.

Run with: python -m pytest tests/test_bush_generator.py -v
Or standalone: python tests/test_bush_generator.py
"""

import os
import sys
import unittest

# Add Scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Scripts'))

from generate_case_bush import (
    generate_bush_blk,
    parse_stiffness,
    float_to_nastran,
    sweep_case_to_bolt_level,
    bolt_level_to_sweep_case,
    STIFFNESS_LEVELS
)


class TestNastranFormatting(unittest.TestCase):
    """Test Nastran number formatting."""
    
    def test_float_to_nastran_positive_exponent(self):
        """Test conversion of positive exponent values."""
        self.assertEqual(float_to_nastran(1e8), "1.+8")
        self.assertEqual(float_to_nastran(1e12), "1.+12")
        self.assertEqual(float_to_nastran(1e4), "1.+4")
    
    def test_float_to_nastran_decimal(self):
        """Test conversion of decimal values."""
        result = float_to_nastran(5.5e7)
        self.assertIn("5.5", result)
        self.assertIn("+7", result)
    
    def test_parse_stiffness_level(self):
        """Test parsing stiffness levels 1-9."""
        nastran, value = parse_stiffness("1")
        self.assertEqual(value, 1e4)
        
        nastran, value = parse_stiffness("9")
        self.assertEqual(value, 1e12)
    
    def test_parse_stiffness_direct(self):
        """Test parsing direct stiffness values."""
        nastran, value = parse_stiffness("1e8")
        self.assertEqual(value, 1e8)
        
        nastran, value = parse_stiffness("5.5e7")
        self.assertEqual(value, 5.5e7)


class TestCaseMapping(unittest.TestCase):
    """Test case number to bolt/level mapping."""
    
    def test_case_0_is_baseline(self):
        """Case 0 should return None (baseline)."""
        bolt, level = sweep_case_to_bolt_level(0)
        self.assertIsNone(bolt)
        self.assertIsNone(level)
    
    def test_case_1_is_bolt2_level1(self):
        """Case 1 = Bolt 2, Level 1."""
        bolt, level = sweep_case_to_bolt_level(1)
        self.assertEqual(bolt, 2)
        self.assertEqual(level, 1)
    
    def test_case_8_is_bolt2_level8(self):
        """Case 8 = Bolt 2, Level 8."""
        bolt, level = sweep_case_to_bolt_level(8)
        self.assertEqual(bolt, 2)
        self.assertEqual(level, 8)
    
    def test_case_9_is_bolt3_level1(self):
        """Case 9 = Bolt 3, Level 1."""
        bolt, level = sweep_case_to_bolt_level(9)
        self.assertEqual(bolt, 3)
        self.assertEqual(level, 1)
    
    def test_case_72_is_bolt10_level8(self):
        """Case 72 = Bolt 10, Level 8."""
        bolt, level = sweep_case_to_bolt_level(72)
        self.assertEqual(bolt, 10)
        self.assertEqual(level, 8)
    
    def test_roundtrip_all_cases(self):
        """Verify bolt_level_to_sweep_case reverses sweep_case_to_bolt_level."""
        for case in range(1, 73):
            bolt, level = sweep_case_to_bolt_level(case)
            recovered_case = bolt_level_to_sweep_case(bolt, level)
            self.assertEqual(case, recovered_case, 
                f"Case {case} -> Bolt {bolt}, Level {level} -> Case {recovered_case}")


class TestBushBlkGeneration(unittest.TestCase):
    """Test Bush.blk file generation."""
    
    def setUp(self):
        """Create temp directory for test files."""
        self.test_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        os.makedirs(self.test_dir, exist_ok=True)
        self.test_file = os.path.join(self.test_dir, 'test_bush.blk')
    
    def tearDown(self):
        """Clean up test files."""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
    
    def test_baseline_generation(self):
        """Test baseline Bush.blk has correct structure."""
        generate_bush_blk({}, self.test_file)
        
        with open(self.test_file, 'r') as f:
            content = f.read()
        
        lines = content.strip().split('\n')
        
        # Should have 10 lines (one per bolt)
        self.assertEqual(len(lines), 10)
        
        # Each line should start with PBUSH
        for line in lines:
            self.assertTrue(line.startswith('PBUSH'))
        
        # Bolt 1 should have K4=1e8 (driving)
        self.assertIn('1.+8', lines[0])
        
        # Bolts 2-10 should have K4=K5=K6=1e12 (healthy)
        for line in lines[1:]:
            self.assertEqual(line.count('1.+12'), 3)
    
    def test_loosened_bolt_generation(self):
        """Test Bush.blk with loosened bolt."""
        # Loosen bolt 5 to 1e6
        bolt_config = {5: ("1.+6", 1e6)}
        generate_bush_blk(bolt_config, self.test_file)
        
        with open(self.test_file, 'r') as f:
            lines = f.read().strip().split('\n')
        
        # Bolt 5 (line index 4) should have K4=K5=K6=1e6
        bolt5_line = lines[4]
        self.assertIn('PBUSH   5', bolt5_line)
        # K1,K2,K3 are 1.+6, plus K4,K5,K6 should be 1.+6
        self.assertEqual(bolt5_line.count('1.+6'), 6)  # All 6 stiffnesses
        
        # Other bolts should still be healthy
        for i, line in enumerate(lines):
            if i == 0:  # Bolt 1 - driving
                self.assertIn('1.+8', line)
            elif i != 4:  # Not bolt 5
                self.assertEqual(line.count('1.+12'), 3)
    
    def test_multi_bolt_loosening(self):
        """Test Bush.blk with multiple loosened bolts."""
        bolt_config = {
            3: ("1.+5", 1e5),
            7: ("1.+7", 1e7),
        }
        generate_bush_blk(bolt_config, self.test_file)
        
        with open(self.test_file, 'r') as f:
            lines = f.read().strip().split('\n')
        
        # Bolt 3 should have 1e5
        self.assertIn('1.+5', lines[2])
        
        # Bolt 7 should have 1e7
        self.assertIn('1.+7', lines[6])


class TestStiffnessLevels(unittest.TestCase):
    """Test stiffness level encoding."""
    
    def test_all_levels_defined(self):
        """All 9 levels should be defined."""
        self.assertEqual(len(STIFFNESS_LEVELS), 9)
    
    def test_levels_increase(self):
        """Stiffness should increase with level."""
        prev_value = 0
        for level in range(1, 10):
            nastran, value = STIFFNESS_LEVELS[level]
            self.assertGreater(value, prev_value)
            prev_value = value
    
    def test_level_1_is_loosest(self):
        """Level 1 should be 1e4 (loosest)."""
        nastran, value = STIFFNESS_LEVELS[1]
        self.assertEqual(value, 1e4)
    
    def test_level_9_is_baseline(self):
        """Level 9 should be 1e12 (healthy/baseline)."""
        nastran, value = STIFFNESS_LEVELS[9]
        self.assertEqual(value, 1e12)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return len(result.failures) == 0 and len(result.errors) == 0


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
