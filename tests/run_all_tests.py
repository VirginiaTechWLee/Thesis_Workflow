"""
Run All Tests

Master test runner for all thesis workflow tests.

Usage:
    python tests/run_all_tests.py
    python tests/run_all_tests.py --verbose
"""

import os
import sys
import argparse
import unittest
from datetime import datetime


def run_all_tests(verbose=False):
    """Run all tests from both tests/ and heeds/tests/ directories."""
    
    print("=" * 70)
    print("THESIS WORKFLOW - FULL TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Get base directory
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Collect all test directories
    test_dirs = [
        os.path.join(base_dir, 'tests'),
        os.path.join(base_dir, 'heeds', 'tests'),
    ]
    
    # Discover and combine tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            print(f"Discovering tests in: {test_dir}")
            discovered = loader.discover(test_dir, pattern='test_*.py')
            suite.addTests(discovered)
    
    # Run tests
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "=" * 70)
    print("FULL TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run:  {result.testsRun}")
    print(f"Failures:   {len(result.failures)}")
    print(f"Errors:     {len(result.errors)}")
    print(f"Skipped:    {len(result.skipped)}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    
    print("=" * 70)
    if success:
        print("RESULT: ALL TESTS PASSED ✓")
    else:
        print("RESULT: SOME TESTS FAILED ✗")
    print("=" * 70)
    
    return success


def main():
    parser = argparse.ArgumentParser(description="Run all thesis workflow tests")
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    success = run_all_tests(verbose=args.verbose)
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
