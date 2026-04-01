"""
Generate case-specific Bush.blk configuration for parametric studies.

FLEXIBLE CONFIGURATION - Supports:
  - Single bolt loosening
  - Multi-bolt loosening (any combination)
  - Arbitrary stiffness levels per bolt
  - HEEDS case recovery
  - Monte Carlo configurations

Stiffness Level Encoding:
  Level 1 = 1e4  (loosest)
  Level 2 = 1e5
  Level 3 = 1e6
  Level 4 = 1e7
  Level 5 = 1e8  (also driving CBUSH K4)
  Level 6 = 1e9
  Level 7 = 1e10
  Level 8 = 1e11
  Level 9 = 1e12 (healthy/baseline)

Baseline Configuration:
  Bolt 1: K4=1e8 (driving CBUSH), K5=1e12, K6=1e12  (ALWAYS FIXED)
  Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (all healthy)

Usage Examples:
  # Baseline
  python generate_case_bush.py --baseline

  # Single bolt loosening
  python generate_case_bush.py --bolt 5 --level 3

  # Multi-bolt with same level
  python generate_case_bush.py --bolt 2,5,7 --level 3

  # Multi-bolt with different levels
  python generate_case_bush.py --bolt 2,5,7 --level 3,6,4

  # Direct stiffness value (bypass level encoding)
  python generate_case_bush.py --bolt 5 --stiffness 5.5e7

  # Legacy single-bolt sweep case number (for backward compatibility)
  python generate_case_bush.py --sweep-case 47

  # Show what a sweep case maps to
  python generate_case_bush.py --sweep-case 47 --info

  # Custom output file
  python generate_case_bush.py --bolt 5 --level 3 --output my_bush.blk

  # Info only (no file generation)
  python generate_case_bush.py --bolt 2,5 --level 4,6 --info
"""

import argparse
import sys
import re

# Stiffness level mapping (level 1-9 -> actual stiffness)
STIFFNESS_LEVELS = {
    1: ("1.+4", 1e4),    # loosest
    2: ("1.+5", 1e5),
    3: ("1.+6", 1e6),
    4: ("1.+7", 1e7),
    5: ("1.+8", 1e8),    # driving CBUSH K4 level
    6: ("1.+9", 1e9),
    7: ("1.+10", 1e10),
    8: ("1.+11", 1e11),
    9: ("1.+12", 1e12),  # healthy/baseline
}

# Nastran notation for fixed values
K_TRANS = "1.+6"      # Translational stiffness (K1, K2, K3)
K_DRIVING = "1.+8"    # Driving CBUSH K4
K_HEALTHY = "1.+12"   # Healthy bolt rotational stiffness


def float_to_nastran(value):
    """
    Convert a float to Nastran shorthand notation.
    E.g., 1e8 -> "1.+8", 5.5e7 -> "5.5+7", 1e-3 -> "1.-3"
    
    Note: HEEDS expects format with dot before sign for whole numbers (1.+8 not 1+8)
    """
    if value == 0:
        return "0.0"

    # Get exponent
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

    # Format mantissa
    mantissa = value / (10 ** exp)

    # Build Nastran notation with dot before sign (HEEDS compatible)
    if exp >= 0:
        if mantissa == int(mantissa):
            # Whole number: 1.+8 format
            return f"{int(mantissa)}.+{exp}"
        else:
            # Decimal: 5.5+7 format
            return f"{mantissa:.6g}+{exp}"
    else:
        if mantissa == int(mantissa):
            # Whole number: 1.-3 format
            return f"{int(mantissa)}.{exp}"
        else:
            # Decimal: 5.5-3 format
            return f"{mantissa:.6g}{exp}"


def parse_stiffness(value_str):
    """
    Parse stiffness value - can be level (1-9) or direct value (1e8, 5.5e7, etc.)
    Returns (nastran_notation, float_value)
    """
    value_str = str(value_str).strip()

    # Check if it's a level number (1-9)
    if value_str.isdigit() and 1 <= int(value_str) <= 9:
        level = int(value_str)
        return STIFFNESS_LEVELS[level]

    # Try to parse as float (handles 1e8, 5.5e7, 100000000, etc.)
    try:
        float_val = float(value_str)
        nastran_str = float_to_nastran(float_val)
        return (nastran_str, float_val)
    except ValueError:
        raise ValueError(f"Cannot parse stiffness value: {value_str}")


def sweep_case_to_bolt_level(case_number):
    """
    Convert legacy single-bolt sweep case number to bolt and level.
    This is for backward compatibility with the 72-case sweep design.

    Case 0:     Baseline
    Cases 1-8:  Bolt 2, Levels 1-8
    Cases 9-16: Bolt 3, Levels 1-8
    ...
    Cases 65-72: Bolt 10, Levels 1-8
    """
    if case_number == 0:
        return None, None  # Baseline

    if case_number < 1 or case_number > 72:
        raise ValueError(f"Sweep case number must be 0-72, got {case_number}")

    zero_indexed = case_number - 1
    bolt_offset = zero_indexed // 8
    level = (zero_indexed % 8) + 1
    bolt_number = bolt_offset + 2

    return bolt_number, level


def bolt_level_to_sweep_case(bolt_number, level):
    """Convert bolt and level to legacy sweep case number."""
    if bolt_number < 2 or bolt_number > 10:
        raise ValueError(f"Bolt number must be 2-10, got {bolt_number}")
    if level < 1 or level > 8:
        raise ValueError(f"Level must be 1-8, got {level}")

    return (bolt_number - 2) * 8 + level


def generate_bush_blk(bolt_config, output_file="Bush.blk"):
    """
    Generate Bush.blk file for given bolt configuration.

    Args:
        bolt_config: dict mapping bolt_id (2-10) to (nastran_str, float_val)
                     Bolts not in dict are healthy (1e12)
                     Bolt 1 is always driving CBUSH
        output_file: Output filename
    """
    with open(output_file, 'w') as f:
        for bolt_id in range(1, 11):
            if bolt_id == 1:
                # Bolt 1 is ALWAYS the driving CBUSH
                k4, k5, k6 = K_DRIVING, K_HEALTHY, K_HEALTHY
            elif bolt_id in bolt_config:
                # This bolt has custom stiffness
                nastran_str, _ = bolt_config[bolt_id]
                k4, k5, k6 = nastran_str, nastran_str, nastran_str
            else:
                # Healthy bolt
                k4, k5, k6 = K_HEALTHY, K_HEALTHY, K_HEALTHY

            # Write PBUSH card
            f.write(f"PBUSH   {bolt_id}       K       {K_TRANS}    {K_TRANS}    {K_TRANS}    {k4}    {k5}    {k6}\n")

    return True


def print_config_info(bolt_config, label=None):
    """Print human-readable configuration information."""
    print("=" * 70)
    if label:
        print(f"CONFIGURATION: {label}")
    else:
        print("CONFIGURATION")
    print("=" * 70)

    if not bolt_config:
        print("BASELINE - All bolts healthy")
        print("  Bolt 1:    K4=1e8 (driving), K5=1e12, K6=1e12")
        print("  Bolts 2-10: K4=1e12, K5=1e12, K6=1e12 (all healthy)")
    else:
        print("  Bolt 1:    K4=1e8 (driving), K5=1e12, K6=1e12  [FIXED]")

        loosened_bolts = sorted(bolt_config.keys())
        for bolt_id in loosened_bolts:
            nastran_str, float_val = bolt_config[bolt_id]
            print(f"  Bolt {bolt_id}:   K4=K5=K6={float_val:.2e} ({nastran_str})  [LOOSENED]")

        healthy_bolts = [b for b in range(2, 11) if b not in bolt_config]
        if healthy_bolts:
            healthy_str = ", ".join(str(b) for b in healthy_bolts)
            print(f"  Bolts {healthy_str}: K4=1e12, K5=1e12, K6=1e12  [HEALTHY]")

    print("=" * 70)


def print_sweep_mapping():
    """Print the legacy single-bolt sweep case mapping table."""
    print("\n" + "=" * 70)
    print("LEGACY SINGLE-BOLT SWEEP CASE MAPPING (72 cases)")
    print("=" * 70)
    print(f"{'Case':<8} {'Bolt':<8} {'Level':<8} {'Stiffness':<12}")
    print("-" * 70)
    print(f"{'0':<8} {'-':<8} {'-':<8} {'Baseline':<12}")
    print("-" * 70)

    for case in range(1, 73):
        bolt, level = sweep_case_to_bolt_level(case)
        _, float_val = STIFFNESS_LEVELS[level]
        print(f"{case:<8} {bolt:<8} {level:<8} {float_val:.0e}")

        if case % 8 == 0 and case < 72:
            print("-" * 70)

    print("=" * 70)


def print_level_encoding():
    """Print the stiffness level encoding table."""
    print("\n" + "=" * 50)
    print("STIFFNESS LEVEL ENCODING")
    print("=" * 50)
    print(f"{'Level':<8} {'Nastran':<12} {'Value':<15} {'Description'}")
    print("-" * 50)
    for level, (nastran, value) in STIFFNESS_LEVELS.items():
        if level == 1:
            desc = "loosest"
        elif level == 5:
            desc = "driving CBUSH K4"
        elif level == 9:
            desc = "healthy/baseline"
        else:
            desc = ""
        print(f"{level:<8} {nastran:<12} {value:<15.0e} {desc}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="Generate case-specific Bush.blk for parametric studies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Baseline configuration
  python generate_case_bush.py --baseline

  # Single bolt, single level
  python generate_case_bush.py --bolt 5 --level 3

  # Multiple bolts, same level
  python generate_case_bush.py --bolt 2,5,7 --level 3

  # Multiple bolts, different levels
  python generate_case_bush.py --bolt 2,5,7 --level 3,6,4

  # Direct stiffness values (bypass level encoding)
  python generate_case_bush.py --bolt 5 --stiffness 5.5e7
  python generate_case_bush.py --bolt 2,5 --stiffness 1e6,5e8

  # Legacy sweep case number (backward compatibility)
  python generate_case_bush.py --sweep-case 47

  # Info only (no file generation)
  python generate_case_bush.py --bolt 5 --level 3 --info

  # Show mappings
  python generate_case_bush.py --show-levels
  python generate_case_bush.py --show-sweep-mapping

  # Lookup sweep case
  python generate_case_bush.py --lookup 7 3
        """
    )

    # Configuration options (mutually exclusive groups)
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument('--baseline', action='store_true',
                              help='Generate baseline configuration (all healthy)')
    config_group.add_argument('--sweep-case', type=int, metavar='N',
                              help='Legacy sweep case number (0-72)')

    # Bolt specification
    parser.add_argument('--bolt', type=str, metavar='N[,N,...]',
                        help='Bolt number(s) to loosen: 2-10, comma-separated for multiple')

    # Stiffness specification (mutually exclusive)
    stiffness_group = parser.add_mutually_exclusive_group()
    stiffness_group.add_argument('--level', type=str, metavar='L[,L,...]',
                                 help='Stiffness level(s) 1-9, comma-separated to match bolts')
    stiffness_group.add_argument('--stiffness', type=str, metavar='V[,V,...]',
                                 help='Direct stiffness value(s), e.g., 1e8 or 5.5e7')

    # Output options
    parser.add_argument('--output', '-o', default='Bush.blk',
                        help='Output filename (default: Bush.blk)')
    parser.add_argument('--label', type=str,
                        help='Case label for display purposes')
    parser.add_argument('--info', action='store_true',
                        help='Print configuration info only (no file generation)')

    # Display options
    parser.add_argument('--show-levels', action='store_true',
                        help='Show stiffness level encoding table')
    parser.add_argument('--show-sweep-mapping', action='store_true',
                        help='Show legacy 72-case sweep mapping')
    parser.add_argument('--lookup', nargs=2, type=int, metavar=('BOLT', 'LEVEL'),
                        help='Look up sweep case number for given bolt and level')

    args = parser.parse_args()

    # Handle display-only options
    if args.show_levels:
        print_level_encoding()
        return 0

    if args.show_sweep_mapping:
        print_sweep_mapping()
        return 0

    if args.lookup:
        bolt, level = args.lookup
        try:
            case = bolt_level_to_sweep_case(bolt, level)
            print(f"Bolt {bolt}, Level {level} = Sweep Case {case}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        return 0

    # Build bolt configuration
    bolt_config = {}

    if args.baseline:
        # Baseline - empty config means all healthy
        pass

    elif args.sweep_case is not None:
        # Legacy sweep case
        if args.sweep_case == 0:
            pass  # Baseline
        else:
            bolt, level = sweep_case_to_bolt_level(args.sweep_case)
            bolt_config[bolt] = STIFFNESS_LEVELS[level]
            if not args.label:
                args.label = f"Sweep Case {args.sweep_case} (Bolt {bolt}, Level {level})"

    elif args.bolt:
        # Custom bolt configuration
        bolts = [int(b.strip()) for b in args.bolt.split(',')]

        # Validate bolt numbers
        for b in bolts:
            if b < 2 or b > 10:
                print(f"Error: Bolt number must be 2-10, got {b}")
                return 1

        # Get stiffness values
        if args.level:
            levels = [l.strip() for l in args.level.split(',')]
        elif args.stiffness:
            levels = [s.strip() for s in args.stiffness.split(',')]
        else:
            print("Error: Must specify --level or --stiffness with --bolt")
            return 1

        # Expand single value to all bolts
        if len(levels) == 1:
            levels = levels * len(bolts)

        if len(levels) != len(bolts):
            print(f"Error: Number of levels ({len(levels)}) must match number of bolts ({len(bolts)})")
            return 1

        # Build config
        for bolt, level_str in zip(bolts, levels):
            try:
                bolt_config[bolt] = parse_stiffness(level_str)
            except ValueError as e:
                print(f"Error: {e}")
                return 1

    else:
        # No configuration specified - show help
        parser.print_help()
        return 1

    # Print configuration info
    print_config_info(bolt_config, args.label)

    # Generate file unless --info only
    if not args.info:
        generate_bush_blk(bolt_config, args.output)
        print(f"\nGenerated: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
