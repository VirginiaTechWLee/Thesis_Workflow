"""
Run All HEEDS Tests

Master test runner for all HEEDS-related tests.

Usage:
    python heeds/tests/run_heeds_tests.py
    python heeds/tests/run_heeds_tests.py --verbose
    python heeds/tests/run_heeds_tests.py --quick  (skip HEEDS integration tests)
"""

import os
import sys
import argparse
import unittest
from datetime import datetime


def discover_tests(test_dir, pattern='test_*.py'):
    """Discover all test files in directory."""
    loader = unittest.TestLoader()
    suite = loader.discover(test_dir, pattern=pattern)
    return suite


def run_tests(verbose=False, quick=False):
    """
    Run all HEEDS tests.
    
    Args:
        verbose: Show detailed output
        quick: Skip HEEDS integration tests (faster)
    """
    print("=" * 70)
    print("HEEDS TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Get test directory
    test_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Discover tests
    suite = discover_tests(test_dir)
    
    # Configure runner
    verbosity = 2 if verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    
    # Run tests
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run:  {result.testsRun}")
    print(f"Failures:   {len(result.failures)}")
    print(f"Errors:     {len(result.errors)}")
    print(f"Skipped:    {len(result.skipped)}")
    print("-" * 70)
    
    if result.failures:
        print("\nFAILED TESTS:")
        for test, traceback in result.failures:
            print(f"  - {test}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"  - {test}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    
    print("=" * 70)
    if success:
        print("RESULT: ALL TESTS PASSED ✓")
    else:
        print("RESULT: SOME TESTS FAILED ✗")
    print("=" * 70)
    
    return success


def main():
    parser = argparse.ArgumentParser(description="Run HEEDS test suite")
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    parser.add_argument('--quick', '-q', action='store_true',
                        help='Skip HEEDS integration tests')
    
    args = parser.parse_args()
    
    success = run_tests(verbose=args.verbose, quick=args.quick)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
