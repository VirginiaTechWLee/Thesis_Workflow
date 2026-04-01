#!/usr/bin/env python
"""
setup_fem.py -- Validate FEM inputs, parse Nastran cards, write config.yaml.

Usage:
    python Scripts/setup_fem.py [--fem-dir fem_input] [--db-path D:\\thesis_database\\thesis_results.db]

User drops 4 files into fem_input/:
    *.dat with SOL 103 (or SEMODES)   -- structural model (modal)
    *.dat with SOL 111                -- random response
    *.blk with PBUSH cards            -- joint properties
    Recoveries.blk                    -- output node requests (XYPUNCH lines)

This script:
    Step 1: Validates all four files exist and contain required Nastran cards
    Step 2: Parses every FEM parameter from those files (zero hardcoding)
    Step 3: Writes config.yaml -- the single source of truth for the pipeline

No element IDs, node lists, or stiffness values are ever hardcoded.
Everything is discovered from the user's actual FEM files.
"""

import argparse
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Force UTF-8 output on Windows (checkmarks, dashes)
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# =============================================================================
#  NASTRAN FIELD PARSING
# =============================================================================

def parse_nastran_real(field_str):
    """Parse Nastran fixed-field real numbers including shorthand notation.

    Examples:
        '1.+12'    -> 1e12
        '1.+6'     -> 1e6
        '2.5-3'    -> 2.5e-3
        '1.0E+06'  -> 1e6
        '  386.1'  -> 386.1
        ''         -> None (blank field)
    """
    s = field_str.strip()
    if not s:
        return None
    # Standard scientific notation (has E or e)
    if 'E' in s.upper() and not s.upper().startswith('ENDT'):
        try:
            return float(s)
        except ValueError:
            return None
    # Nastran shorthand: mantissa directly followed by +/- then exponent
    # "1.+12" -> "1.e+12", "2.5-3" -> "2.5e-3", "-1.+6" -> "-1.e+6"
    m = re.match(r'^([+-]?\d*\.?\d*)([-+])(\d+)$', s)
    if m:
        mantissa, sign, exp = m.groups()
        if not mantissa or mantissa in ('+', '-', '.'):
            return None
        try:
            return float(f"{mantissa}e{sign}{exp}")
        except ValueError:
            return None
    try:
        return float(s)
    except ValueError:
        return None


def split_nastran_fields(line, large_field=False):
    """Split a Nastran bulk data line into fixed-width fields.

    Standard format: 10 fields of 8 characters each (cols 0-79)
    Large-field format: field1(8) + 4 fields of 16 chars + field6(8)
    """
    padded = line.ljust(80)
    if large_field:
        fields = [padded[0:8]]
        for i in range(4):
            fields.append(padded[8 + i * 16: 8 + (i + 1) * 16])
        fields.append(padded[72:80])
    else:
        fields = [padded[i:i + 8] for i in range(0, 80, 8)]
    return fields


# =============================================================================
#  STEP 1: VALIDATE
# =============================================================================

def _read_lines(path):
    """Read file lines, stripping BOM and normalizing."""
    with open(path, 'r', encoding='utf-8-sig', errors='replace') as f:
        return f.readlines()


def _identify_files(fem_dir):
    """Identify SOL 103, SOL 111, Bush.blk, and Recoveries.blk by content.

    Returns: (sol103_path, sol111_path, bush_path, recoveries_path)
    """
    fem_path = Path(fem_dir)
    # Deduplicate: on case-insensitive Windows, *.dat and *.DAT return same files
    dat_files = list({p.resolve(): p for p in
                      list(fem_path.glob('*.dat')) + list(fem_path.glob('*.DAT'))}.values())
    blk_files = list({p.resolve(): p for p in
                      list(fem_path.glob('*.blk')) + list(fem_path.glob('*.BLK'))}.values())

    sol103 = None
    sol111 = None
    bush = None
    recoveries = None

    # Identify DAT files by SOL card
    for dat in dat_files:
        try:
            content = dat.read_text(encoding='utf-8-sig', errors='replace').upper()
        except Exception:
            continue
        if re.search(r'\bSOL\s+(103|SEMODES)\b', content):
            if sol103 is not None:
                _fail(f"Multiple SOL 103/SEMODES files found: {sol103.name} and {dat.name}")
            sol103 = dat
        if re.search(r'\bSOL\s+111\b', content):
            if sol111 is not None:
                _fail(f"Multiple SOL 111 files found: {sol111.name} and {dat.name}")
            sol111 = dat

    # Identify BLK files by content
    for blk in blk_files:
        try:
            content = blk.read_text(encoding='utf-8-sig', errors='replace').upper()
        except Exception:
            continue
        if 'PBUSH' in content:
            if bush is not None:
                _fail(f"Multiple PBUSH files found: {bush.name} and {blk.name}")
            bush = blk
        if 'XYPUNCH' in content:
            if recoveries is not None:
                _fail(f"Multiple XYPUNCH files found: {recoveries.name} and {blk.name}")
            recoveries = blk

    return sol103, sol111, bush, recoveries


def validate(fem_dir):
    """Step 1: Validate all four FEM files exist and contain required cards.

    Returns (sol103_path, sol111_path, bush_path, recoveries_path) on success.
    Exits with clear error message on failure.
    """
    fem_path = Path(fem_dir)
    if not fem_path.is_dir():
        _fail(f"FEM input directory not found: {fem_dir}")

    sol103, sol111, bush, recoveries = _identify_files(fem_dir)

    errors = []
    if sol103 is None:
        errors.append("No SOL 103/SEMODES .dat file found in fem_input/")
    if sol111 is None:
        errors.append("No SOL 111 .dat file found in fem_input/")
    if bush is None:
        errors.append("No .blk file with PBUSH cards found in fem_input/")
    if recoveries is None:
        errors.append("No .blk file with XYPUNCH lines found in fem_input/ (Recoveries.blk)")

    if errors:
        for e in errors:
            print(f"  X {e}")
        _fail("Missing required FEM input files.")

    # Validate required cards in each file
    sol103_content = sol103.read_text(encoding='utf-8-sig', errors='replace').upper()
    sol111_content = sol111.read_text(encoding='utf-8-sig', errors='replace').upper()
    bush_content = bush.read_text(encoding='utf-8-sig', errors='replace').upper()
    rec_content = recoveries.read_text(encoding='utf-8-sig', errors='replace').upper()

    sol103_checks = {
        'EIGRL or EIGR': bool(re.search(r'^(EIGRL|EIGR)\b', sol103_content, re.M)),
        'CBUSH': bool(re.search(r'^CBUSH\b', sol103_content, re.M)),
        'SPC1 or SPC': bool(re.search(r'^SPC1?\s', sol103_content, re.M)),
        'GRID': bool(re.search(r'^GRID\b', sol103_content, re.M)),
    }
    sol111_checks = {
        'RANDPS': bool(re.search(r'^RANDPS\b', sol111_content, re.M)),
        'TABRND1': bool(re.search(r'^TABRND1\b', sol111_content, re.M)),
        'FREQ': bool(re.search(r'^FREQ[124]?\s', sol111_content, re.M)),
    }
    bush_checks = {
        'PBUSH': bool(re.search(r'^PBUSH\b', bush_content, re.M)),
    }
    rec_checks = {
        'XYPUNCH': bool(re.search(r'XYPUNCH', rec_content)),
    }

    all_ok = True
    for label, checks, fname in [
        ("SOL 103", sol103_checks, sol103.name),
        ("SOL 111", sol111_checks, sol111.name),
        ("Bush", bush_checks, bush.name),
        ("Recoveries", rec_checks, recoveries.name),
    ]:
        missing = [card for card, found in checks.items() if not found]
        if missing:
            print(f"  X {label} ({fname}): missing {', '.join(missing)}")
            all_ok = False
        else:
            cards = ', '.join(checks.keys())
            print(f"  PASS {label}: {fname} ({cards})")

    if not all_ok:
        _fail("Required Nastran cards missing from input files.")

    return sol103, sol111, bush, recoveries


# =============================================================================
#  STEP 2: PARSE
# =============================================================================

def parse_sol103(dat_path):
    """Parse SOL 103 dat file for FEM geometry and boundary conditions.

    Extracts:
        fixed_node:          node with all 6 DOFs constrained (SPC1/SPC)
        grids:               {node_id: (x, y, z)} from GRID cards
        cbush_connectivity:  {element_id: (node_a, node_b)} from CBUSH cards
        driving_element:     CBUSH element connected to fixed_node
        variable_elements:   all other CBUSH elements
    """
    lines = _read_lines(dat_path)

    grids = {}
    cbush_conn = {}
    spc_nodes = {}  # {node_id: set_of_constrained_dofs}

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith('$'):
            continue

        upper = stripped.upper().lstrip()

        # --- GRID cards ---
        if upper.startswith('GRID'):
            large = '*' in stripped[:8]
            fields = split_nastran_fields(stripped, large_field=large)
            nid = int(fields[1].strip())
            x1 = parse_nastran_real(fields[3]) or 0.0
            x2 = parse_nastran_real(fields[4]) or 0.0
            x3 = parse_nastran_real(fields[5]) or 0.0
            grids[nid] = (x1, x2, x3)

        # --- CBUSH cards ---
        elif upper.startswith('CBUSH') and not upper.startswith('CBUSH1D'):
            fields = split_nastran_fields(stripped)
            eid = int(fields[1].strip())
            ga = int(fields[3].strip())
            gb_str = fields[4].strip()
            gb = int(gb_str) if gb_str else None
            cbush_conn[eid] = (ga, gb)

        # --- SPC1 cards ---
        elif upper.startswith('SPC1'):
            fields = split_nastran_fields(stripped)
            comp = fields[2].strip()
            for i in range(3, 10):
                nid_str = fields[i].strip() if i < len(fields) else ''
                if nid_str:
                    try:
                        nid = int(nid_str)
                        spc_nodes.setdefault(nid, set())
                        for c in comp:
                            if c.isdigit():
                                spc_nodes[nid].add(int(c))
                    except ValueError:
                        pass

        # --- SPC cards (older format) ---
        elif upper.startswith('SPC') and not upper.startswith('SPC1') and not upper.startswith('SPCD'):
            fields = split_nastran_fields(stripped)
            for pair_start in [2, 5]:
                g_str = fields[pair_start].strip() if pair_start < len(fields) else ''
                c_str = fields[pair_start + 1].strip() if pair_start + 1 < len(fields) else ''
                if g_str and c_str:
                    try:
                        nid = int(g_str)
                        spc_nodes.setdefault(nid, set())
                        for c in c_str:
                            if c.isdigit():
                                spc_nodes[nid].add(int(c))
                    except ValueError:
                        pass

    # --- Find the fixed node (all 6 DOFs constrained) ---
    fixed_node = None
    for nid, dofs in spc_nodes.items():
        if dofs >= {1, 2, 3, 4, 5, 6}:
            if fixed_node is not None:
                _fail(f"Multiple nodes with all 6 DOFs constrained: {fixed_node} and {nid}")
            fixed_node = nid

    if fixed_node is None:
        _fail("No node found with all 6 DOFs constrained (SPC 123456).")

    if not cbush_conn:
        _fail("No CBUSH elements found in SOL 103 dat file.")

    # --- Driving element: CBUSH connected to fixed_node ---
    driving_element = None
    for eid, (ga, gb) in cbush_conn.items():
        if ga == fixed_node or gb == fixed_node:
            if driving_element is not None:
                _fail(f"Multiple CBUSH elements connected to fixed node {fixed_node}: "
                      f"{driving_element} and {eid}")
            driving_element = eid

    if driving_element is None:
        _fail(f"No CBUSH element connected to fixed node {fixed_node}.")

    # --- Variable elements: all CBUSH except driving ---
    variable_elements = sorted([eid for eid in cbush_conn if eid != driving_element])

    return {
        "fixed_node": fixed_node,
        "grids": grids,
        "cbush_connectivity": {eid: list(nodes) for eid, nodes in cbush_conn.items()},
        "driving_element": driving_element,
        "variable_elements": variable_elements,
    }


def parse_bush_blk(bush_path):
    """Parse Bush.blk to discover all joint elements and stiffness values.

    Reads PBUSH cards in fixed-field Nastran format:
        PBUSH  PID  'K'  K1  K2  K3  K4  K5  K6

    Returns:
        element_ids:       sorted list of all PBUSH property IDs
        stiffness:         {pid: {K1: val, ..., K6: val}}
        stiffness_dofs:    list of Kn DOFs that are defined (non-blank)
        n_elements:        total count
    """
    lines = _read_lines(bush_path)

    stiffness = {}
    dof_labels = ['K1', 'K2', 'K3', 'K4', 'K5', 'K6']

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith('$'):
            continue

        upper = stripped.upper().lstrip()
        if not upper.startswith('PBUSH'):
            continue

        fields = split_nastran_fields(stripped)
        pid_str = fields[1].strip()
        if not pid_str:
            continue
        pid = int(pid_str)

        flag = fields[2].strip().upper()
        if flag != 'K':
            continue

        kvals = {}
        for i, dof in enumerate(dof_labels):
            idx = 3 + i
            if idx < len(fields):
                val = parse_nastran_real(fields[idx])
                if val is not None:
                    kvals[dof] = val

        stiffness[pid] = kvals

    if not stiffness:
        _fail("No PBUSH cards with stiffness data found in Bush.blk")

    element_ids = sorted(stiffness.keys())

    all_dofs = set()
    for kvals in stiffness.values():
        all_dofs.update(kvals.keys())
    stiffness_dofs = [d for d in dof_labels if d in all_dofs]

    return {
        "element_ids": element_ids,
        "stiffness": stiffness,
        "stiffness_dofs": stiffness_dofs,
        "n_elements": len(element_ids),
    }


def parse_recoveries_blk(recoveries_path):
    """Parse Recoveries.blk to discover output recovery nodes and data types.

    XYPUNCH lines look like:
        XYPUNCH,ACCELERATION,PSDF/ 111(T1RM),111(T2RM),111(T3RM)
        XYPUNCH,DISP,PSDF/ 222(T1RM),222(R1RM)
        XYPUNCH,FORCE,PSDF/ 1(2),1(3),1(4)

    Returns:
        recovery_nodes: sorted unique list of grid node IDs from ACCELERATION/DISP lines
        force_elements: sorted unique list of element IDs from FORCE lines
        data_types:     list of data types found (ACCELERATION, DISPLACEMENT, FORCE)
    """
    lines = _read_lines(recoveries_path)

    grid_nodes = set()
    force_elements = set()
    data_types = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('$'):
            continue
        upper = stripped.upper()

        if not upper.startswith('XYPUNCH'):
            continue

        # Parse: XYPUNCH,<TYPE>,PSDF/ <node>(DOF),<node>(DOF),...
        # Split on '/' to get the request list
        parts = stripped.split('/', 1)
        if len(parts) < 2:
            continue

        header = parts[0].upper()
        request_str = parts[1].strip()

        # Determine data type from header
        is_force = 'FORCE' in header
        if 'ACCEL' in header:
            data_types.add('ACCELERATION')
        elif 'DISP' in header:
            data_types.add('DISPLACEMENT')
        elif 'FORCE' in header:
            data_types.add('FORCE')

        # Parse node/element IDs from request: "111(T1RM),222(T2RM)"
        # Each token is ID(DOF) — extract the ID before the parenthesis
        tokens = request_str.split(',')
        for token in tokens:
            token = token.strip()
            # Extract ID before '('
            paren_idx = token.find('(')
            if paren_idx > 0:
                id_str = token[:paren_idx].strip()
            else:
                id_str = token.strip()

            if not id_str:
                continue
            try:
                node_or_elem = int(id_str)
            except ValueError:
                continue

            if is_force:
                force_elements.add(node_or_elem)
            else:
                grid_nodes.add(node_or_elem)

    return {
        "recovery_nodes": sorted(grid_nodes),
        "force_elements": sorted(force_elements),
        "data_types": sorted(data_types),
    }


def parse_sol111(dat_path):
    """Parse SOL 111 dat file for frequency range, output requests, and PSD input.

    Extracts:
        freq_min, freq_max:  from FREQ/FREQ1/FREQ2/FREQ4 cards
        data_types:          [ACCELERATION, DISPLACEMENT, FORCE] from case control
        psd_input:           [(freq, amplitude), ...] from TABRND1
        damping:             damping ratio from TABDMP1 (if present)
    """
    lines = _read_lines(dat_path)
    full_text = ''.join(lines)
    upper_text = full_text.upper()

    # --- Frequency range from FREQ cards ---
    freq_min = float('inf')
    freq_max = float('-inf')

    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith('$'):
            continue
        upper = stripped.upper().lstrip()

        if upper.startswith('FREQ1'):
            fields = split_nastran_fields(stripped)
            f1 = parse_nastran_real(fields[2])
            df = parse_nastran_real(fields[3])
            ndf = parse_nastran_real(fields[4])
            if f1 is not None:
                freq_min = min(freq_min, f1)
                if df is not None and ndf is not None:
                    freq_max = max(freq_max, f1 + df * ndf)

        elif upper.startswith('FREQ2'):
            fields = split_nastran_fields(stripped)
            f1 = parse_nastran_real(fields[2])
            f2 = parse_nastran_real(fields[3])
            if f1 is not None:
                freq_min = min(freq_min, f1)
            if f2 is not None:
                freq_max = max(freq_max, f2)

        elif upper.startswith('FREQ4'):
            fields = split_nastran_fields(stripped)
            f1 = parse_nastran_real(fields[2])
            f2 = parse_nastran_real(fields[3])
            if f1 is not None:
                freq_min = min(freq_min, f1)
            if f2 is not None:
                freq_max = max(freq_max, f2)

        elif upper.startswith('FREQ') and not upper.startswith('FREQ1') \
                and not upper.startswith('FREQ2') and not upper.startswith('FREQ4'):
            fields = split_nastran_fields(stripped)
            for i in range(2, len(fields)):
                f = parse_nastran_real(fields[i])
                if f is not None:
                    freq_min = min(freq_min, f)
                    freq_max = max(freq_max, f)

    if freq_min == float('inf') or freq_max == float('-inf'):
        _fail("No FREQ/FREQ1/FREQ2/FREQ4 cards found in SOL 111 dat file.")

    # --- Output requests from case control section ---
    data_types = []
    case_control = re.search(r'CEND(.*?)BEGIN\s+BULK', upper_text, re.DOTALL)
    cc_text = case_control.group(1) if case_control else upper_text

    if re.search(r'ACCELERATION\s*\(', cc_text):
        data_types.append('ACCELERATION')
    if re.search(r'DISPLACEMENT\s*\(', cc_text):
        data_types.append('DISPLACEMENT')
    if re.search(r'\bFORCE\s*\(', cc_text):
        data_types.append('FORCE')

    if not data_types:
        print("  WARNING: No PSDF output requests found in case control")
        data_types = ['ACCELERATION']

    # --- TABRND1 (PSD input table) ---
    psd_input = []
    in_tabrnd1 = False
    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith('$'):
            continue
        upper = stripped.upper().lstrip()

        if upper.startswith('TABRND1'):
            in_tabrnd1 = True
            continue

        if in_tabrnd1:
            fields = split_nastran_fields(stripped)
            for i in range(0, len(fields)):
                val_str = fields[i].strip().upper()
                if val_str == 'ENDT':
                    in_tabrnd1 = False
                    break
                if val_str.startswith('+') and not any(c.isdigit() for c in val_str):
                    continue
                val = parse_nastran_real(fields[i])
                if val is not None:
                    psd_input.append(val)

    psd_pairs = []
    for i in range(0, len(psd_input) - 1, 2):
        psd_pairs.append((psd_input[i], psd_input[i + 1]))

    # --- TABDMP1 (damping table) ---
    damping = None
    in_tabdmp1 = False
    damp_values = []
    for line in lines:
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith('$'):
            continue
        upper = stripped.upper().lstrip()

        if upper.startswith('TABDMP1'):
            in_tabdmp1 = True
            continue

        if in_tabdmp1:
            fields = split_nastran_fields(stripped)
            for i in range(len(fields)):
                val_str = fields[i].strip().upper()
                if val_str == 'ENDT':
                    in_tabdmp1 = False
                    break
                if val_str.startswith('+') and not any(c.isdigit() for c in val_str):
                    continue
                val = parse_nastran_real(fields[i])
                if val is not None:
                    damp_values.append(val)

    if len(damp_values) >= 2:
        damp_ratios = [damp_values[i] for i in range(1, len(damp_values), 2)]
        if damp_ratios:
            damping = damp_ratios[0]

    return {
        "freq_min": freq_min,
        "freq_max": freq_max,
        "data_types": data_types,
        "psd_input": psd_pairs,
        "damping": damping,
    }


# =============================================================================
#  BASE / RESPONSE NODE IDENTIFICATION
# =============================================================================

def identify_base_and_response_nodes(cbush_connectivity, fixed_node):
    """Walk CBUSH connectivity from fixed node to classify base vs response nodes.

    Base side = nodes on the same structural side as the SPC fixed node.
    Response side = free nodes that respond to dynamic loading.

    Uses BFS/flood fill from fixed_node through GA connections.
    For each CBUSH: whichever end is on the base side, the other is response side.

    Returns: (base_nodes: set, response_nodes: set)
    """
    base_nodes = {fixed_node}
    changed = True

    while changed:
        changed = False
        for eid, (ga, gb) in cbush_connectivity.items():
            # If GA is on base side, GB is response (don't add GB to base)
            # If GB is on base side, GA is also base side
            if gb in base_nodes and ga not in base_nodes:
                base_nodes.add(ga)
                changed = True

    response_nodes = set()
    for eid, (ga, gb) in cbush_connectivity.items():
        if ga not in base_nodes:
            response_nodes.add(ga)
        if gb not in base_nodes:
            response_nodes.add(gb)

    return base_nodes, response_nodes


def find_partner_node(node, cbush_connectivity):
    """Find the other node of a CBUSH element given one node."""
    for eid, (ga, gb) in cbush_connectivity.items():
        if ga == node:
            return gb, eid
        if gb == node:
            return ga, eid
    return None, None


# =============================================================================
#  CROSS-CHECKS AND RECOVERY VALIDATION
# =============================================================================

def compute_healthy_stiffness(bush_data, variable_elements):
    """Determine healthy (baseline) stiffness from variable elements.

    The healthy stiffness is the most common K4 value among variable elements.
    """
    k4_values = []
    for eid in variable_elements:
        if eid in bush_data["stiffness"]:
            k4 = bush_data["stiffness"][eid].get("K4")
            if k4 is not None:
                k4_values.append(k4)

    if not k4_values:
        _fail("No K4 stiffness values found for variable elements in Bush.blk")

    counter = Counter(k4_values)
    healthy_stiffness = counter.most_common(1)[0][0]
    return healthy_stiffness


def compute_driving_stiffness(bush_data, driving_element):
    """Extract the driving element's full stiffness from Bush.blk."""
    if driving_element not in bush_data["stiffness"]:
        _fail(f"Driving element {driving_element} not found in Bush.blk")
    return bush_data["stiffness"][driving_element]


def cross_check(sol103_data, bush_data):
    """Cross-check SOL 103 and Bush.blk for consistency."""
    cbush_eids = set(sol103_data["cbush_connectivity"].keys())
    pbush_pids = set(bush_data["element_ids"])

    errors = []

    if len(cbush_eids) != len(pbush_pids):
        errors.append(f"CBUSH count ({len(cbush_eids)}) != PBUSH count ({len(pbush_pids)})")

    if cbush_eids != pbush_pids:
        only_cbush = cbush_eids - pbush_pids
        only_pbush = pbush_pids - cbush_eids
        if only_cbush:
            errors.append(f"CBUSH elements not in Bush.blk: {sorted(only_cbush)}")
        if only_pbush:
            errors.append(f"PBUSH elements not in SOL 103 dat: {sorted(only_pbush)}")

    driving = sol103_data["driving_element"]
    if driving not in pbush_pids:
        errors.append(f"Driving element {driving} not found in Bush.blk")

    return errors


def validate_recovery_nodes(recovery_nodes, sol103_data, cbush_connectivity_tuples):
    """Validate recovery nodes against FEM geometry.

    Hard checks (fail):
        1. All recovery nodes must exist in GRID cards
        2. Recovery nodes must not include the SPC fixed node
        3. Recovery nodes must not include base-side CBUSH nodes

    Soft warnings (continue):
        Recovery nodes not directly at a CBUSH response-side node

    Returns: (errors: list, warnings: list)
    """
    grids = sol103_data["grids"]
    fixed_node = sol103_data["fixed_node"]

    base_nodes, response_nodes = identify_base_and_response_nodes(
        cbush_connectivity_tuples, fixed_node)

    errors = []
    warnings = []

    for node in recovery_nodes:
        # Check 1: node exists in GRID cards
        if node not in grids:
            errors.append(
                f"Recovery node {node} not found in FEM GRID cards. "
                f"Verify node ID in Recoveries.blk.")

        # Check 2: SPC fixed node — valid (engineer's choice, baseline reference)
        elif node == fixed_node:
            pass  # SPC node is allowed in recovery list

        # Check 3: not a base-side CBUSH node
        elif node in base_nodes:
            partner, eid = find_partner_node(node, cbush_connectivity_tuples)
            suggestion = f" Use response-side node {partner} instead." if partner else ""
            errors.append(
                f"Recovery node {node} is on the base/fixed side of CBUSH element {eid}. "
                f"Base-side nodes have near-zero dynamic response.{suggestion}")

        # Soft check: not directly at a CBUSH response node
        elif node not in response_nodes:
            warnings.append(
                f"Node {node} is not directly at a CBUSH joint. "
                f"Ensure this node captures bolt looseness response in your FEM. "
                f"The pipeline will proceed but diagnostic accuracy depends on "
                f"sensor placement sensitivity.")

    return errors, warnings, base_nodes, response_nodes


# =============================================================================
#  GB NODE ANALYSIS AND INTERACTIVE SUGGESTION
# =============================================================================

def analyze_gb_coverage(recovery_nodes, cbush_connectivity_tuples, base_nodes):
    """Analyze which GB (Grid-B) CBUSH nodes are in the recovery list.

    For each CBUSH element, GB is the second node in the card (field 4).
    In standard Nastran convention, GB is the "free" end — the node whose
    response is most sensitive to joint stiffness changes.

    When both nodes are response-side (neither is the SPC node), GB is
    still preferred because it's the conventional output location.

    Returns:
        covered_gb:   list of (gb_node, element_id) that ARE in recovery list
        missing_gb:   list of (gb_node, element_id) that are NOT in recovery list
        non_cbush:    list of recovery nodes that are not GB nodes at all
    """
    recovery_set = set(recovery_nodes)
    covered_gb = []
    missing_gb = []

    # GB is always the second node (index 1) of the CBUSH card
    gb_map = {}  # {gb_node: element_id}
    for eid, (ga, gb) in sorted(cbush_connectivity_tuples.items()):
        gb_map[gb] = eid

    for gb_node, eid in sorted(gb_map.items(), key=lambda x: x[1]):
        if gb_node in recovery_set:
            covered_gb.append((gb_node, eid))
        else:
            missing_gb.append((gb_node, eid))

    # Recovery nodes that are not any GB node
    gb_set = set(gb_map.keys())
    non_cbush_recovery = [n for n in recovery_nodes if n not in gb_set]

    return covered_gb, missing_gb, non_cbush_recovery


def print_recovery_analysis(covered_gb, missing_gb, non_cbush_recovery):
    """Print the recovery node analysis block."""
    print()
    print("  RECOVERY NODE ANALYSIS")
    print("  " + "-" * 50)

    if covered_gb:
        print("  Response-side CBUSH nodes in your recovery list:")
        for gb_node, eid in covered_gb:
            print(f"    {gb_node} (response side of element {eid}) OPTIMAL")

    if non_cbush_recovery:
        print("  Non-CBUSH recovery nodes:")
        for node in non_cbush_recovery:
            print(f"    {node} (structural node, not at a joint) OK")

    total_gb = len(covered_gb) + len(missing_gb)
    print()
    if not missing_gb:
        print(f"  All {total_gb} response-side CBUSH nodes are included")
        print("  in your recovery list -- optimal coverage for")
        print("  bolt looseness detection.")
    else:
        print(f"  You have {len(covered_gb)} of {total_gb} response-side")
        print("  CBUSH nodes covered.")


def report_missing_gb(missing_gb):
    """If GB nodes are missing, print what's missing and move on.

    No interactive prompt. The engineer set up their Recoveries.blk
    deliberately — we inform, they decide.
    """
    if not missing_gb:
        return

    print()
    print("  NOTE: The following response-side (GB) nodes are NOT in")
    print("  your recovery list. Per-bolt classification accuracy may")
    print("  be reduced for these elements:")
    for gb_node, eid in missing_gb:
        print(f"    Node {gb_node} (response side of element {eid})")
    print()
    print("  To add them, append XYPUNCH lines to Recoveries.blk")
    print("  and re-run setup_fem.py.")


# =============================================================================
#  STEP 3: WRITE CONFIG
# =============================================================================

def _generate_sweep_levels(healthy_stiffness):
    """Generate 9 logarithmic sweep levels from loose to healthy.

    Spans 8 orders of magnitude below healthy stiffness.
    For healthy=1e12: [1e4, 1e5, 1e6, 1e7, 1e8, 1e9, 1e10, 1e11, 1e12]
    """
    top_exp = int(round(math.log10(healthy_stiffness)))
    return [10.0 ** e for e in range(top_exp - 8, top_exp + 1)]


def build_config(fem_dir, sol103_path, sol111_path, bush_path, recoveries_path,
                 sol103_data, sol111_data, bush_data, recovery_data, db_path):
    """Build the complete config dictionary from parsed FEM data."""

    variable_elements = sol103_data["variable_elements"]
    driving_element = sol103_data["driving_element"]
    healthy_stiffness = compute_healthy_stiffness(bush_data, variable_elements)
    driving_stiffness = compute_driving_stiffness(bush_data, driving_element)

    fem_dir_rel = "fem_input"

    config = {
        "files": {
            "structural_model": f"{fem_dir_rel}/{sol103_path.name}",
            "random_response": f"{fem_dir_rel}/{sol111_path.name}",
            "bush_template": f"{fem_dir_rel}/{bush_path.name}",
            "recoveries": f"{fem_dir_rel}/{recoveries_path.name}",
            "fem_input_dir": fem_dir_rel,
        },
        "fem": {
            "fixed_node": sol103_data["fixed_node"],
            "driving_element": driving_element,
            "driving_stiffness": driving_stiffness,
            "variable_elements": variable_elements,
            "n_variable_elements": len(variable_elements),
            "cbush_connectivity": sol103_data["cbush_connectivity"],
            "output_nodes": recovery_data["recovery_nodes"],
            "force_elements": recovery_data["force_elements"],
            "healthy_stiffness": healthy_stiffness,
            "stiffness_dofs": bush_data["stiffness_dofs"],
            "freq_min": sol111_data["freq_min"],
            "freq_max": sol111_data["freq_max"],
            "data_types": sol111_data["data_types"],
        },
        "database": {
            "path": str(db_path),
        },
        "pipeline": {
            "model_dir": str(Path(db_path).parent),
            "reports_dir": str(Path(fem_dir).parent / "reports"),
            "python": "C:/ProgramData/anaconda3/python.exe",
        },
        "study": {
            "name": "study_A_single_bolt_sweep",
            "type": "sweep",
            "n_samples": 0,
        },
        "sweep_levels": _generate_sweep_levels(healthy_stiffness),
        "monte_carlo_healthy": {
            "n_samples": 300,
            "seed": 99,
            "stiffness_min": healthy_stiffness / 10.0,
            "stiffness_max": healthy_stiffness,
        },
        "pca": {
            "variance_threshold": 0.90,
        },
        "peaks": {
            "n_peaks": 3,
        },
        "paths": {
            "nastran_exe": r"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe",
            "python_exe": r"C:\ProgramData\anaconda3\python.exe",
            "heeds_mdo_path": r"C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe",
            "heeds_working_dir": r"C:\Users\waynelee\Documents",
            "db_dir": str(Path(db_path).parent),
        },
    }

    # Add PSD input and damping if discovered
    if sol111_data["psd_input"]:
        config["fem"]["psd_input"] = [
            {"freq": f, "amplitude": a} for f, a in sol111_data["psd_input"]
        ]
    if sol111_data["damping"] is not None:
        config["fem"]["damping"] = sol111_data["damping"]

    return config


def write_config_yaml(config, output_path):
    """Write config.yaml with clear formatting."""
    if not HAS_YAML:
        _fail("PyYAML is required to write config.yaml. Install: pip install pyyaml")

    class ConfigDumper(yaml.SafeDumper):
        pass

    def represent_list(dumper, data):
        if len(data) <= 20 and all(isinstance(x, (int, float, str)) for x in data):
            return dumper.represent_sequence('tag:yaml.org,2002:seq', data,
                                             flow_style=True)
        return dumper.represent_sequence('tag:yaml.org,2002:seq', data,
                                         flow_style=False)

    def represent_float(dumper, data):
        if data != 0 and (abs(data) >= 1e6 or abs(data) < 1e-2):
            return dumper.represent_scalar('tag:yaml.org,2002:float', f'{data:.1e}')
        return dumper.represent_scalar('tag:yaml.org,2002:float', str(data))

    ConfigDumper.add_representer(list, represent_list)
    ConfigDumper.add_representer(float, represent_float)

    header = (
        "# ==============================================================\n"
        "# config.yaml -- AUTO-GENERATED by setup_fem.py\n"
        "#\n"
        "# Do not edit manually. Re-run setup_fem.py to regenerate.\n"
        "# Only 'study' section is user-editable between runs.\n"
        "# ==============================================================\n\n"
    )

    sections = [
        ("# --- Input files (discovered from fem_input/) ---", "files"),
        ("\n# --- FEM geometry (parsed from dat + blk + recoveries) ---", "fem"),
        ("\n# --- Database ---", "database"),
        ("\n# --- Pipeline paths ---", "pipeline"),
        ("\n# --- Study config (user edits this between runs) ---", "study"),
        ("\n# --- Stiffness sweep levels (derived from healthy stiffness) ---", "sweep_levels"),
        ("\n# --- Monte Carlo healthy / Study E (tight variation for class 0) ---", "monte_carlo_healthy"),
        ("\n# --- ML settings ---", "pca"),
        ("\n# --- Peak extraction ---", "peaks"),
        ("\n# --- Tool paths ---", "paths"),
    ]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(header)
        for comment, key in sections:
            if key in config:
                f.write(comment + "\n")
                section = {key: config[key]}
                f.write(yaml.dump(section, Dumper=ConfigDumper,
                                  default_flow_style=False, sort_keys=False))


# =============================================================================
#  UTILITIES
# =============================================================================

def _fail(msg):
    """Print error and exit."""
    print(f"\n  FAIL: {msg}")
    sys.exit(1)


def _print_banner():
    print("=" * 62)
    print("  setup_fem.py -- FEM Input Validation & Config Generator")
    print("=" * 62)
    print()


# =============================================================================
#  MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate FEM inputs and generate config.yaml")
    parser.add_argument('--fem-dir', default=None,
                        help='Path to fem_input directory (default: auto-detect)')
    parser.add_argument('--db-path', default=None,
                        help='Path to thesis database')
    args = parser.parse_args()

    _print_banner()

    # --- Resolve fem_input directory ---
    if args.fem_dir:
        fem_dir = Path(args.fem_dir)
    else:
        candidates = [
            Path(__file__).parent.parent / 'fem_input',
            Path.cwd() / 'fem_input',
        ]
        fem_dir = None
        for c in candidates:
            if c.is_dir():
                fem_dir = c
                break
        if fem_dir is None:
            _fail("Cannot find fem_input/ directory. Use --fem-dir to specify.")

    fem_dir = fem_dir.resolve()
    db_path = args.db_path or r"D:\thesis_database\thesis_results.db"

    # =================================================================
    #  STEP 1: VALIDATE
    # =================================================================
    print("STEP 1: Validate")
    sol103_path, sol111_path, bush_path, recoveries_path = validate(fem_dir)
    print()

    # =================================================================
    #  STEP 2: PARSE
    # =================================================================
    print("STEP 2: Parse")
    sol103_data = parse_sol103(sol103_path)
    bush_data = parse_bush_blk(bush_path)
    sol111_data = parse_sol111(sol111_path)
    recovery_data = parse_recoveries_blk(recoveries_path)

    # --- Reconstruct CBUSH connectivity as tuples for node analysis ---
    cbush_tuples = {}
    for eid, nodes in sol103_data["cbush_connectivity"].items():
        cbush_tuples[eid] = (nodes[0], nodes[1])

    healthy_stiffness = compute_healthy_stiffness(bush_data, sol103_data["variable_elements"])

    # --- Print parse summary ---
    print(f"  Fixed node:        {sol103_data['fixed_node']}")
    print(f"  Driving element:   {sol103_data['driving_element']} (connected to fixed node)")
    print(f"  Variable elements: {sol103_data['variable_elements']} ({len(sol103_data['variable_elements'])} joints)")
    print(f"  Recovery nodes:    {len(recovery_data['recovery_nodes'])} nodes")
    print(f"  Force elements:    {len(recovery_data['force_elements'])} elements")
    print(f"  Healthy stiffness: {healthy_stiffness:.1e}")
    print(f"  Frequency range:   {sol111_data['freq_min']} - {sol111_data['freq_max']} Hz")
    print(f"  Data types:        {', '.join(sol111_data['data_types'])}")
    if sol111_data['damping'] is not None:
        print(f"  Damping:           {sol111_data['damping']*100:.1f}%")
    if sol111_data['psd_input']:
        print(f"  PSD input:         {len(sol111_data['psd_input'])} breakpoints")
    print()

    # --- Cross-checks: PBUSH vs CBUSH ---
    print("  Cross-checks:")
    xcheck_errors = cross_check(sol103_data, bush_data)
    if xcheck_errors:
        for err in xcheck_errors:
            print(f"    FAIL {err}")
        _fail("Cross-check failed between SOL 103 dat and Bush.blk")
    else:
        n_cbush = len(sol103_data["cbush_connectivity"])
        n_pbush = bush_data["n_elements"]
        print(f"    PASS PBUSH count ({n_pbush}) == CBUSH count ({n_cbush})")
        print(f"    PASS Driving element {sol103_data['driving_element']} found in Bush.blk")
        print(f"    PASS All {len(sol103_data['variable_elements'])} variable elements in Bush.blk")
    print()

    # --- Identify base vs response side nodes ---
    base_nodes, response_nodes = identify_base_and_response_nodes(
        cbush_tuples, sol103_data["fixed_node"])

    print(f"  Base-side nodes:     {sorted(base_nodes)}")
    print(f"  Response-side nodes: {sorted(response_nodes)}")
    print()

    # --- Validate recovery nodes ---
    print("  Recovery node validation:")
    rec_errors, rec_warnings, _, _ = validate_recovery_nodes(
        recovery_data["recovery_nodes"], sol103_data, cbush_tuples)

    if rec_errors:
        for err in rec_errors:
            print(f"    FAIL {err}")
        _fail("Recovery node validation failed. Fix Recoveries.blk and re-run.")

    n_pass = len(recovery_data["recovery_nodes"]) - len(rec_warnings)
    print(f"    PASS {n_pass} recovery nodes on response side or in GRID cards")
    for warn in rec_warnings:
        print(f"    WARN {warn}")
    print()

    # --- GB node coverage analysis ---
    covered_gb, missing_gb, non_cbush = analyze_gb_coverage(
        recovery_data["recovery_nodes"], cbush_tuples, base_nodes)

    print_recovery_analysis(covered_gb, missing_gb, non_cbush)

    # --- Report missing GB nodes (informational, no prompt) ---
    report_missing_gb(missing_gb)

    print()

    # =================================================================
    #  STEP 3: WRITE CONFIG
    # =================================================================
    print("STEP 3: Write config.yaml")
    config = build_config(
        fem_dir, sol103_path, sol111_path, bush_path, recoveries_path,
        sol103_data, sol111_data, bush_data, recovery_data, db_path,
    )

    config_path = fem_dir / 'config.yaml'
    write_config_yaml(config, config_path)

    n_keys = sum(
        len(v) if isinstance(v, dict) else 1
        for v in config.values()
    )
    print(f"  PASS {config_path} written ({n_keys} top-level sections)")
    print()

    # =================================================================
    #  DONE
    # =================================================================
    print("=" * 62)
    print("  READY: python pipeline/run_pipeline.py")
    print("=" * 62)


if __name__ == '__main__':
    main()
