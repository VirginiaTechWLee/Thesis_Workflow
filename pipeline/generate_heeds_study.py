#!/usr/bin/env python3
"""
Generate HEEDS .heeds project files for Nastran bolt looseness studies.

Parses a Bush.blk file to discover PBUSH bolt definitions, then generates
a HEEDS 2410-compatible .heeds XML project file with the appropriate
variables, design sets, and sweep configurations.

Usage examples:
    # Single bolt sweep with 9 levels (default)
    python generate_heeds_study.py --bush-blk Bush.blk --study-type single_bolt_sweep --output study.heeds

    # Dry run to inspect the design matrix
    python generate_heeds_study.py --bush-blk Bush.blk --study-type single_bolt_sweep --dry-run

    # Custom levels and skip bolts
    python generate_heeds_study.py --bush-blk Bush.blk --study-type single_bolt_sweep --output study.heeds --levels 5 --skip-bolts 1,2
"""

import argparse
import re
import sys
import math
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# ---------------------------------------------------------------------------
# Stiffness level definitions
# ---------------------------------------------------------------------------

# Default 9-level sweep from loose to tight
DEFAULT_LEVELS_9 = [
    (4,  "1.+4"),
    (5,  "1.+5"),
    (6,  "1.+6"),
    (7,  "1.+7"),
    (8,  "1.+8"),
    (9,  "1.+9"),
    (10, "1.+10"),
    (11, "1.+11"),
    (12, "1.+12"),
]

# 5-level sweep matching the original bolt3_sweep template
DEFAULT_LEVELS_5 = [
    (6,  "1.+6"),
    (7,  "1.+7"),
    (8,  "1.+8"),
    (10, "1.+10"),
    (12, "1.+12"),
]


def get_stiffness_levels(num_levels: int) -> List[Tuple[int, str]]:
    """Return a list of (exponent, nastran_notation) tuples for the requested
    number of stiffness levels.

    For 5 levels: matches the original bolt3_sweep template.
    For 9 levels: spans 1e4 to 1e12.
    For other counts: linearly spaces exponents from 4 to 12.
    """
    if num_levels == 5:
        return DEFAULT_LEVELS_5
    if num_levels == 9:
        return DEFAULT_LEVELS_9

    if num_levels < 2:
        raise ValueError("Number of levels must be at least 2")
    if num_levels > 9:
        raise ValueError("Number of levels must be at most 9 (exponents 4-12)")

    # Linearly space exponents from 4 to 12
    exponents = []
    for i in range(num_levels):
        exp = round(4 + i * (12 - 4) / (num_levels - 1))
        if exp not in exponents:
            exponents.append(exp)
    # Deduplicate and ensure we have the right count
    exponents = sorted(set(exponents))
    while len(exponents) < num_levels:
        # Fill gaps
        for e in range(4, 13):
            if e not in exponents:
                exponents.append(e)
                exponents.sort()
                if len(exponents) >= num_levels:
                    break
    exponents = exponents[:num_levels]
    return [(e, f"1.+{e}") for e in exponents]


# ---------------------------------------------------------------------------
# Bush.blk parser
# ---------------------------------------------------------------------------

class BoltInfo:
    """Parsed information about a single PBUSH bolt in Bush.blk."""
    def __init__(self, bolt_num: int, prop_id: int, comment_name: str,
                 row_0based: int, k_values: List[str]):
        self.bolt_num = bolt_num          # 1-based bolt number
        self.prop_id = prop_id            # PBUSH property ID
        self.comment_name = comment_name  # e.g. "Cbush_3"
        self.row_0based = row_0based      # 0-based row of PBUSH data line
        self.k_values = k_values          # [K1, K2, K3, K4, K5, K6] as strings

    @property
    def k4(self) -> str:
        return self.k_values[3]

    @property
    def k5(self) -> str:
        return self.k_values[4]

    @property
    def k6(self) -> str:
        return self.k_values[5]

    def __repr__(self):
        return (f"BoltInfo(bolt={self.bolt_num}, prop_id={self.prop_id}, "
                f"name={self.comment_name}, row={self.row_0based}, "
                f"K4={self.k4}, K5={self.k5}, K6={self.k6})")


def parse_bush_blk(filepath: str) -> List[BoltInfo]:
    """Parse Bush.blk to extract bolt information.

    Expected format:
        $ Femap Property N : <name>
        PBUSH    <id>       K    <K1>    <K2>    <K3>    <K4>    <K5>    <K6>

    Returns a list of BoltInfo sorted by bolt number.
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Bush.blk not found: {filepath}")

    lines = path.read_text().splitlines()
    bolts = []
    bolt_num = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for comment lines: $ Femap Property N : <name>
        comment_match = re.match(
            r'^\$\s*Femap\s+Property\s+(\d+)\s*:\s*(.+)', line.strip()
        )
        if comment_match:
            prop_id_from_comment = int(comment_match.group(1))
            comment_name = comment_match.group(2).strip()

            # Next line should be the PBUSH data
            if i + 1 < len(lines):
                data_line = lines[i + 1]
                if data_line.strip().startswith('PBUSH'):
                    bolt_num += 1
                    data_row = i + 1  # 0-based row of PBUSH line

                    fields = []
                    for c in range(0, len(data_line), 8):
                        fields.append(data_line[c:c+8].strip())

                    prop_id = int(fields[1]) if len(fields) > 1 else prop_id_from_comment

                    k_values = []
                    for k_idx in range(3, 9):
                        if k_idx < len(fields) and fields[k_idx]:
                            k_values.append(fields[k_idx])
                        else:
                            k_values.append("0.0")

                    bolts.append(BoltInfo(
                        bolt_num=bolt_num,
                        prop_id=prop_id,
                        comment_name=comment_name,
                        row_0based=data_row,
                        k_values=k_values
                    ))
                    i += 2
                    continue

        # Also handle bare PBUSH lines (no preceding comment)
        elif line.strip().startswith('PBUSH'):
            bolt_num += 1
            data_row = i

            fields = []
            for c in range(0, len(line), 8):
                fields.append(line[c:c+8].strip())

            prop_id = int(fields[1]) if len(fields) > 1 else bolt_num
            comment_name = f"Bolt_{prop_id}"

            k_values = []
            for k_idx in range(3, 9):
                if k_idx < len(fields) and fields[k_idx]:
                    k_values.append(fields[k_idx])
                else:
                    k_values.append("0.0")

            bolts.append(BoltInfo(
                bolt_num=bolt_num,
                prop_id=prop_id,
                comment_name=comment_name,
                row_0based=data_row,
                k_values=k_values
            ))

        i += 1

    if not bolts:
        raise ValueError(f"No PBUSH bolt entries found in {filepath}")

    return bolts


# ---------------------------------------------------------------------------
# Design matrix generation
# ---------------------------------------------------------------------------

def generate_single_bolt_sweep(
    bolts: List[BoltInfo],
    skip_bolts: List[int],
    levels: List[Tuple[int, str]],
) -> Tuple[List[BoltInfo], List[Dict], List[str]]:
    """Generate design matrix for single-bolt sweep study.

    For each variable bolt, sweep K4=K5=K6 through all levels while all
    other bolts stay at baseline (tight = last level index).

    Returns:
        variable_bolts: list of BoltInfo for swept bolts
        designs: list of dicts with design info
        design_names: list of design name strings
    """
    variable_bolts = [b for b in bolts if b.bolt_num not in skip_bolts]
    num_levels = len(levels)
    # Baseline = tight = last index (1-based)
    baseline_idx = num_levels

    designs = []
    design_names = []

    for bolt in variable_bolts:
        for level_i, (exp, nastran_val) in enumerate(levels):
            set_idx = level_i + 1  # 1-based set index
            design_name = f"bolt{bolt.bolt_num}_1e{exp}"
            design_names.append(design_name)

            # Build row of set indices: all baseline except this bolt
            row = {}
            for vb in variable_bolts:
                if vb.bolt_num == bolt.bolt_num:
                    row[vb.bolt_num] = set_idx
                else:
                    row[vb.bolt_num] = baseline_idx
            designs.append(row)

    return variable_bolts, designs, design_names


def generate_two_bolt_sweep(
    bolts: List[BoltInfo],
    skip_bolts: List[int],
    levels: List[Tuple[int, str]],
) -> Tuple[List[BoltInfo], List[Dict], List[str]]:
    """Generate design matrix for two-bolt simultaneous sweep study.

    For each pair of variable bolts, sweep both K4=K5=K6 through all
    non-baseline levels simultaneously while all other bolts stay at
    baseline (tight = last level index).

    Design count: C(N_bolts, 2) × (N_levels - 1)
    Example: C(9,2) × 8 = 288 designs

    Returns:
        variable_bolts: list of BoltInfo for swept bolts
        designs: list of dicts with design info
        design_names: list of design name strings
    """
    from itertools import combinations

    variable_bolts = [b for b in bolts if b.bolt_num not in skip_bolts]
    num_levels = len(levels)
    baseline_idx = num_levels  # tight = last index (1-based)

    designs = []
    design_names = []

    for bolt_a, bolt_b in combinations(variable_bolts, 2):
        for level_i, (exp, nastran_val) in enumerate(levels):
            set_idx = level_i + 1
            # Skip baseline-level designs (both bolts tight = no damage)
            if set_idx == baseline_idx:
                continue

            design_name = f"bolt{bolt_a.bolt_num}_bolt{bolt_b.bolt_num}_1e{exp}"
            design_names.append(design_name)

            # Both bolts in pair at set_idx, all others at baseline
            row = {}
            for vb in variable_bolts:
                if vb.bolt_num in (bolt_a.bolt_num, bolt_b.bolt_num):
                    row[vb.bolt_num] = set_idx
                else:
                    row[vb.bolt_num] = baseline_idx
            designs.append(row)

    return variable_bolts, designs, design_names


def generate_three_bolt_sweep(
    bolts: List[BoltInfo],
    skip_bolts: List[int],
    levels: List[Tuple[int, str]],
) -> Tuple[List[BoltInfo], List[Dict], List[str]]:
    """Generate design matrix for three-bolt simultaneous sweep study.

    For each triplet of variable bolts, sweep all three K4=K5=K6 through
    all non-baseline levels simultaneously. All other bolts stay at baseline.

    Design count: C(N_bolts, 3) × (N_levels - 1)
    Example: C(9,3) × 8 = 672 designs
    """
    from itertools import combinations

    variable_bolts = [b for b in bolts if b.bolt_num not in skip_bolts]
    num_levels = len(levels)
    baseline_idx = num_levels

    designs = []
    design_names = []

    for bolt_a, bolt_b, bolt_c in combinations(variable_bolts, 3):
        for level_i, (exp, nastran_val) in enumerate(levels):
            set_idx = level_i + 1
            if set_idx == baseline_idx:
                continue

            design_name = f"bolt{bolt_a.bolt_num}_bolt{bolt_b.bolt_num}_bolt{bolt_c.bolt_num}_1e{exp}"
            design_names.append(design_name)

            row = {}
            for vb in variable_bolts:
                if vb.bolt_num in (bolt_a.bolt_num, bolt_b.bolt_num, bolt_c.bolt_num):
                    row[vb.bolt_num] = set_idx
                else:
                    row[vb.bolt_num] = baseline_idx
            designs.append(row)

    return variable_bolts, designs, design_names


def generate_all_bolt_sweep(
    bolts: List[BoltInfo],
    skip_bolts: List[int],
    levels: List[Tuple[int, str]],
) -> Tuple[List[BoltInfo], List[Dict], List[str]]:
    """Generate design matrix for all-bolt simultaneous sweep (Study D).

    All variable bolts loosen together at the same level. Tests the fully
    degraded joint scenario.

    Design count: N_levels - 1 (skip baseline)
    Example: 8 designs (one per non-baseline level)
    """
    variable_bolts = [b for b in bolts if b.bolt_num not in skip_bolts]
    num_levels = len(levels)
    baseline_idx = num_levels

    designs = []
    design_names = []

    for level_i, (exp, nastran_val) in enumerate(levels):
        set_idx = level_i + 1
        if set_idx == baseline_idx:
            continue

        design_name = f"all_bolts_1e{exp}"
        design_names.append(design_name)

        row = {vb.bolt_num: set_idx for vb in variable_bolts}
        designs.append(row)

    return variable_bolts, designs, design_names


def generate_monte_carlo(
    bolts: List[BoltInfo],
    skip_bolts: List[int],
    levels: List[Tuple[int, str]],
    n_samples: int = 500,
    seed: int = 42,
) -> Tuple[List[BoltInfo], List[Dict], List[str]]:
    """Generate design matrix for Monte Carlo random sampling study (Study D).

    Each design independently and randomly assigns one of the discrete
    loosened stiffness levels (all levels except baseline) to each bolt.
    Design 1 is always the baseline (all bolts at tight/baseline).

    Design count: n_samples + 1 (the +1 is the baseline design)

    Args:
        bolts: all parsed bolts from Bush.blk
        skip_bolts: bolt numbers to exclude (e.g. driving bolt)
        levels: list of (exponent, nastran_notation) tuples
        n_samples: number of random designs to generate
        seed: random seed for reproducibility

    Returns:
        variable_bolts: list of BoltInfo for variable bolts
        designs: list of dicts with design info
        design_names: list of design name strings
    """
    import numpy as np

    variable_bolts = [b for b in bolts if b.bolt_num not in skip_bolts]
    num_levels = len(levels)
    baseline_idx = num_levels  # tight = last index (1-based)

    # All level indices (1-based): 1 through num_levels (includes baseline/tight)
    all_indices = list(range(1, num_levels + 1))

    rng = np.random.default_rng(seed)

    designs = []
    design_names = []

    # Design 1: baseline (all bolts at tight)
    design_names.append("monte_carlo_001")
    designs.append({vb.bolt_num: baseline_idx for vb in variable_bolts})

    # Designs 2 through n_samples+1: random sampling from ALL levels including baseline
    for i in range(2, n_samples + 2):
        design_names.append(f"monte_carlo_{i:03d}")
        row = {}
        for vb in variable_bolts:
            row[vb.bolt_num] = int(rng.choice(all_indices))
        designs.append(row)

    return variable_bolts, designs, design_names


# ---------------------------------------------------------------------------
# HEEDS XML generation
# ---------------------------------------------------------------------------

def _xml_escape(s: str) -> str:
    """Escape special XML characters."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


def generate_checksum(study_name: str) -> str:
    """Generate a 4-hex-char checksum for the Agent element."""
    h = hashlib.md5(study_name.encode()).hexdigest()
    return h[:4]


def generate_heeds_xml(
    study_name: str,
    variable_bolts: List[BoltInfo],
    designs: List[Dict],
    design_names: List[str],
    levels: List[Tuple[int, str]],
    all_bolts: List[BoltInfo],
    num_modes: int = 10,
    structural_model: str = None,
    random_response: str = None,
) -> str:
    """Generate the complete HEEDS .heeds XML content.

    Follows the exact structure of the working bolt3_sweep.heeds template
    for HEEDS 2410 compatibility.

    structural_model and random_response are config-driven filenames.
    If not provided, they raise an error.
    """
    if not structural_model:
        raise ValueError("structural_model filename is required (from config.yaml files.structural_model)")
    if not random_response:
        raise ValueError("random_response filename is required (from config.yaml files.random_response)")

    # Derive Nastran output filenames (Nastran lowercases the stem)
    import os as _os
    structural_base = _os.path.splitext(structural_model)[0].lower()
    structural_f06 = f"{structural_base}.f06"
    random_base = _os.path.splitext(random_response)[0].lower()
    random_f06 = f"{random_base}.f06"
    random_pch = f"{random_base}.pch"

    num_designs = len(designs)
    num_var_bolts = len(variable_bolts)
    num_levels = len(levels)
    baseline_idx = num_levels  # 1-based index of tight/baseline value
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    checksum = generate_checksum(study_name)

    # Build level descriptions for comment
    level_desc = ", ".join(f"1e{exp}" for exp, _ in levels)
    bolt_desc = ", ".join(str(b.bolt_num) for b in variable_bolts)

    xml_parts = []

    # --- Header ---
    xml_parts.append(f"""<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE HEEDSProject>
<!--       HEEDS Data Model document
    Copyright (c) 2024 Siemens. All rights reserved.

    {study_name} - {num_levels} stiffness levels, {num_var_bolts} variable bolts
    Generated for thesis bolt-looseness detection pipeline
    Generated on {today} by generate_heeds_study.py

    Variable bolts: {bolt_desc}
    Stiffness levels: {level_desc}
    Total designs: {num_designs}
-->
<Project app="HEEDSMDO" build="241030" version="2410.0">
  <!--Project Data-->
  <Meta name="scriptEngine">Python3</Meta>""")

    # --- Set (shared stiffness levels) ---
    xml_parts.append(f"""
  <!--HEEDS.Attribute.Set-->
  <Set name="set_K_levels" ordered="1">""")
    for _, nastran_val in levels:
        xml_parts.append(f'    <Item value="{nastran_val}"/>')
    xml_parts.append("  </Set>")

    # --- Condition ---
    xml_parts.append("""
  <!--HEEDS.Attribute.Condition-->
  <Condition name="Condition_1">
    <Item type="FileContain" anlRef="HEEDS.Analysis.File.MDO.Analysis_1" findRef="HEEDS.Output.File.{random_f06}" findText="* * * END OF JOB * * *" op="and"/>
  </Condition>""")

    # --- Variables ---
    xml_parts.append("""
  <!--HEEDS.Parameter.Variable-->""")
    for bolt in variable_bolts:
        bn = bolt.bolt_num
        for k in ["K4", "K5", "K6"]:
            xml_parts.append(
                f'  <Variable name="{k}_bolt{bn}" flags="2048" numInTags="1"/>'
            )

    # --- Responses ---
    xml_parts.append("""
  <!--HEEDS.Parameter.Response-->
  <Response name="Response_Array" type="File" acceptMax="" acceptMin="" flags="2048" numOutTags="1"/>""")
    for m in range(1, num_modes + 1):
        xml_parts.append(
            f'  <Response name="Modes{m}" type="Formula" acceptMax="" acceptMin="" '
            f'formula="Response_Array[{m}-1]"/>'
        )

    # --- Process / MDO ---
    # Build Bush.blk Input Tags for all variable bolts
    bush_tags = []
    for bolt in variable_bolts:
        bn = bolt.bolt_num
        row = bolt.row_0based
        bush_tags.append(
            f'            <Tag charCol="48" col="6" format="HEEDS.Static.Format.Fixed 8" '
            f'mode="fixed" ref="HEEDS.Parameter.Variable.K4_bolt{bn}" row="{row}"/>'
        )
        bush_tags.append(
            f'            <Tag charCol="56" col="7" format="HEEDS.Static.Format.Fixed 8" '
            f'mode="fixed" ref="HEEDS.Parameter.Variable.K5_bolt{bn}" row="{row}"/>'
        )
        bush_tags.append(
            f'            <Tag charCol="64" col="8" format="HEEDS.Static.Format.Fixed 8" '
            f'mode="fixed" ref="HEEDS.Parameter.Variable.K6_bolt{bn}" row="{row}"/>'
        )
    bush_tags_str = "\n".join(bush_tags)

    xml_parts.append(f"""
  <!--HEEDS.Process-->
  <Process name="Process_1" current="true" parallel="false">

    <!--HEEDS.Analysis.File.MDO-->
    <MDO name="Analysis_1" active="true" solver="General">
      <Data type="MDO" resource="Local" useMaxTime="true">
        <anlCommand value="FBM_TO_DBALL.bat"/>
        <anlArgs value=""/>
        <anlShell value="cmd.exe"/>
        <anlFolder value="designFolder"/>
        <anlErrorMode value="STOP"/>
        <anlInfeasibleMode value="CONTINUE"/>
        <anlCreateNewDesignOnError value="false"/>
        <anlDontCountAsEvalOnError value="false"/>
        <anlCaptureOutput value="true"/>
        <decimalDelimiter value="fromPortal"/>
        <VisFile type="data" filename="acceleration_results.csv" source="analysisFolder"/>
        <VisFile type="data" filename="acceleration_results_delta.csv" source="analysisFolder"/>
        <VisFile type="data" filename="displacement_results.csv" source="analysisFolder"/>
        <VisFile type="data" filename="displacement_results_delta.csv" source="analysisFolder"/>
        <VisFile type="image" filename="all_acceleration_dof_T1.png" source="analysisFolder"/>
        <VisFile type="image" filename="all_displacement_dof_T1.png" source="analysisFolder"/>
        <VisFile type="data" filename="{random_pch}" source="analysisFolder"/>
        <VisFile type="data" filename="Bush.blk" source="analysisFolder"/>
        <Command command="&quot;C:\\\\HEEDS\MDO\Ver2410\Python3\python.exe&quot; Pch_TO_CSV2.py" event="postAnalysis" folder="designFolder" useRval="0" value="0"/>
        <primaryInput ref="HEEDS.Input.File.{structural_model}"/>
        <Reservation active="false" mode="share"/>
        <FinishCondition ref="HEEDS.Attribute.Condition.Condition_1"/>
        <RunCondition folder="designFolder" ref="" resource="LOCAL"/>
        <SuccessCondition ref=""/>
      </Data>

      <!--Inputs-->
      <Inputs>
        <Input type="file" path="Bush.blk">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">8</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
{bush_tags_str}
          </Data>
        </Input>
        <Input type="file" path="{structural_model}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">8</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
          </Data>
        </Input>
        <Input type="file" path="{random_response}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
          </Data>
        </Input>
        <Input type="file" path="Recoveries.blk">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
          </Data>
        </Input>
        <Input type="file" path="Pch_TO_CSV2.py">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
          </Data>
        </Input>
      </Inputs>

      <!--Outputs-->
      <Outputs>
        <Output type="file" path="{structural_f06}">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">8</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
            <Tag mode="script" ref="HEEDS.Parameter.Response.Response_Array"><![CDATA[SET_PARAMETER_LIST(%names%) $ auto-generated parameter name list
GOTO_STRING('FRACTION', 3)
MOVE_DOWN(2)
GET_COLUMN_FREE(2, -1,',= ')]]></Tag>
          </Data>
        </Output>
        <Output type="file" path="{random_f06}">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="{random_pch}">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="acceleration_results.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="displacement_results.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="acceleration_results_delta.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="displacement_results_delta.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">",",;,"",=,(,),',\t,\s</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
      </Outputs>
    </MDO>

    <!--Execution Order-->
    <AnalysisGroup type="Serial">
      <Analysis ref="HEEDS.Analysis.File.MDO.Analysis_1"/>
    </AnalysisGroup>
  </Process>""")

    # --- Study ---
    xml_parts.append(f"""
  <!--HEEDS.Study-->
  <Study name="Study_1" current="true" id="1" postfolder="POST_0" prefix="HEEDS" randomSeed="0.1" status="NotStarted">
    <Meta name="aviewTimeMode">total</Meta>
    <Meta name="msgsel">study</Meta>
    <RunOptions>
      <CaptureOutput value="true"/>
      <IgnoreBaseline value="false"/>
      <OutputUsingCSH value="false"/>
      <ReEvalError value="false"/>
      <ReEvalRepeat value="false"/>
      <ResponseOut value="true"/>
      <SaveHistory value="true"/>
      <SaveRestart value="true"/>
      <ScriptExecution value="false"/>
      <SharedDesignsFirst value="first"/>
      <SkipFirstEvalCheck value="false"/>
      <UseBaseline value="false"/>
      <VerboseExec value="false"/>
      <VerboseScript value="false"/>
      <VerboseSearch value="false"/>
      <WaitLicense value="false"/>
    </RunOptions>""")

    # --- Agent ---
    xml_parts.append(f"""
    <!--HEEDS.Agent-->
    <Agent name="Sweep_1" type="EVAL" checksum="{checksum}" evalFolder="" id="0" lastUpdate="{now}" method=": DesignSweep" numEvalsTotal="{num_designs}" outputPrecision="16" postfolder="POST_0" prefix="HEEDS" saveErrorMode="saveOnly" saveMode="None">
      <Process ref="HEEDS.Process.Process_1"/>""")

    # Agent Variables
    xml_parts.append("""
      <!--HEEDS.AgentParameter.Variable-->""")
    for bolt in variable_bolts:
        bn = bolt.bolt_num
        for k in ["K4", "K5", "K6"]:
            xml_parts.append(
                f'      <Variable name="{k}_bolt{bn}" type="Discrete" '
                f'baseline="{baseline_idx}" '
                f'ref="HEEDS.Parameter.Variable.{k}_bolt{bn}" '
                f'set_ref="HEEDS.Attribute.Set.set_K_levels" state="Required"/>'
            )

    # Agent Responses
    xml_parts.append("""
      <!--HEEDS.AgentParameter.Response-->
      <Response name="Response_Array" ref="HEEDS.Parameter.Response.Response_Array" state="Required"/>""")
    for m in range(1, num_modes + 1):
        xml_parts.append(
            f'      <Response name="Modes{m}" ref="HEEDS.Parameter.Response.Modes{m}" state="Included"/>'
        )

    # --- UserDesignSet ---
    xml_parts.append(f"""
      <!--HEEDS.UserDesignSet: {num_designs} deterministic designs sweeping bolt stiffness-->
      <UserDesignSet name="{study_name}">""")

    for name in design_names:
        xml_parts.append(f'        <Design name="{name}" map="false" resp="false"/>')

    # Build CDATA header line
    var_names = []
    for bolt in variable_bolts:
        bn = bolt.bolt_num
        for k in ["K4", "K5", "K6"]:
            var_names.append(f"{k}_bolt{bn}")
    resp_names = ["Response_Array"] + [f"Modes{m}" for m in range(1, num_modes + 1)]
    header = " " + ", ".join(var_names + resp_names)

    # Build CDATA data rows
    data_rows = []
    for design in designs:
        row_vals = []
        for bolt in variable_bolts:
            idx = design[bolt.bolt_num]
            # K4, K5, K6 all get the same index for single_bolt_sweep
            row_vals.extend([str(idx)] * 3)
        data_rows.append("    " + ",    ".join(row_vals))

    cdata_content = header + "\n" + "\n".join(data_rows) + "\n"

    xml_parts.append(f"        <Data><![CDATA[\n{cdata_content}]]></Data>")
    xml_parts.append("      </UserDesignSet>")

    # MethodData
    xml_parts.append(f"""
      <MethodData type="OPT">
        <numEvals value="150"/>
        <method value="SHERPA"/>
        <SHERPA numEvals="150"/>
      </MethodData>
      <MethodData type="EVAL" numEvals="{num_designs}"/>

      <Designs>
        <data><![CDATA[
 Cycle #, Eval #, Source, Status
]]></data>
      </Designs>
    </Agent>""")

    # DesignSets
    xml_parts.append(f"""
    <!--HEEDS.DesignSet-->
    <DesignSet name="All Designs" type="5" agent="HEEDS.Agent.Sweep_1" flag="62"/>
    <DesignSet name="Non-Error Designs" type="4" agent="HEEDS.Agent.Sweep_1" flag="46"/>
    <DesignSet name="{study_name}" agent="HEEDS.Agent.Sweep_1" flag="32" source="{study_name}"/>
  </Study>""")

    # Static Equations
    xml_parts.append("""
  <!--HEEDS.Static.Equation-->
  <StaticEquation name="_desMin" active="true"/>
  <StaticEquation name="_desMax" active="true"/>
  <StaticEquation name="_bestVal" active="true"/>
  <StaticEquation name="_desVal" active="true"/>
</Project>
""")

    return "\n".join(xml_parts)


# ---------------------------------------------------------------------------
# Dry-run printer
# ---------------------------------------------------------------------------

def print_dry_run(
    study_name: str,
    variable_bolts: List[BoltInfo],
    designs: List[Dict],
    design_names: List[str],
    levels: List[Tuple[int, str]],
    all_bolts: List[BoltInfo],
    skip_bolts: List[int],
):
    """Print the design matrix and study summary without writing a file."""
    print("=" * 70)
    print(f"HEEDS Study: {study_name}")
    print("=" * 70)
    print()

    print("Bush.blk Bolts Parsed:")
    print(f"  {'Bolt':>6}  {'PropID':>6}  {'Name':<20}  {'Row(0b)':>7}  "
          f"{'K4':>8}  {'K5':>8}  {'K6':>8}  {'Status':<10}")
    print("  " + "-" * 90)
    for b in all_bolts:
        status = "SKIP" if b.bolt_num in skip_bolts else "VARIABLE"
        print(f"  {b.bolt_num:>6}  {b.prop_id:>6}  {b.comment_name:<20}  "
              f"{b.row_0based:>7}  {b.k4:>8}  {b.k5:>8}  {b.k6:>8}  {status:<10}")
    print()

    print(f"Stiffness Levels ({len(levels)}):")
    for i, (exp, nval) in enumerate(levels):
        print(f"  Index {i+1}: {nval}  (1e{exp})")
    print(f"  Baseline index: {len(levels)} (tight)")
    print()

    print(f"Variable Bolts: {len(variable_bolts)}")
    print(f"Designs per bolt: {len(levels)}")
    print(f"Total Designs: {len(designs)}")
    print()

    # Print design matrix header
    var_cols = []
    for bolt in variable_bolts:
        var_cols.append(f"bolt{bolt.bolt_num}")
    header = f"  {'Design':<20}  " + "  ".join(f"{c:>8}" for c in var_cols)
    print("Design Matrix (set indices, baseline={}):"
          .format(len(levels)))
    print(header)
    print("  " + "-" * len(header))

    for name, design in zip(design_names, designs):
        vals = [str(design[b.bolt_num]) for b in variable_bolts]
        print(f"  {name:<20}  " + "  ".join(f"{v:>8}" for v in vals))

    print()
    print(f"HEEDS Variables: {len(variable_bolts) * 3} "
          f"(K4/K5/K6 x {len(variable_bolts)} bolts)")
    print(f"numEvalsTotal: {len(designs)}")


# ---------------------------------------------------------------------------
# Project folder assembly
# ---------------------------------------------------------------------------

# Files required in the HEEDS project folder for Nastran bolt studies.
# Each entry is (filename, description, required).
def _required_project_files(structural_model: str, random_response: str):
    """Return list of (filename, description, required) for project assembly.

    Filenames are config-driven -- no hardcoded beam names.
    """
    return [
        ("Bush.blk",             "PBUSH spring properties",          True),
        (structural_model,       "Nastran fixed-base modal input",   True),
        (random_response,        "Nastran random response input",    True),
        ("Recoveries.blk",      "Recovery set bulk data",            True),
        ("FBM_TO_DBALL.bat",     "Solver launch batch script",       True),
        ("Pch_TO_CSV2.py",      "Post-processing punch-to-CSV",     True),
    ]


def assemble_project_folder(
    output_heeds: Path,
    project_dir: str,
    study_name: str,
    structural_model: str = None,
    random_response: str = None,
) -> Path:
    """Create a ready-to-run HEEDS project folder.

    Searches project_dir (and common fallback locations) for every required
    file, copies them into a new folder named after the study, and places the
    .heeds file alongside them.

    structural_model and random_response must come from config.yaml.
    Returns the assembled folder path.
    """
    if not structural_model:
        raise ValueError("structural_model is required (from config.yaml)")
    if not random_response:
        raise ValueError("random_response is required (from config.yaml)")

    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        raise FileNotFoundError(f"--project-dir not found: {project_dir}")

    # Build the output folder next to the .heeds file
    out_folder = output_heeds.parent / study_name
    out_folder.mkdir(parents=True, exist_ok=True)

    # Move .heeds into the folder
    final_heeds = out_folder / output_heeds.name
    if output_heeds.exists():
        shutil.move(str(output_heeds), str(final_heeds))

    # Search paths: project_dir first, then common Desktop locations
    desktop = Path("C:/Users/waynelee/Desktop")
    search_dirs = [
        project_dir,
        desktop / "templates",
        desktop / "Scripts",
        desktop,
    ]

    copied = []
    missing = []

    for filename, desc, required in _required_project_files(structural_model, random_response):
        # Skip Bush.blk if it's already been specified via --bush-blk
        # (we'll copy it separately below)
        dst = out_folder / filename
        if dst.exists():
            copied.append((filename, dst, "(already present)"))
            continue

        found = False
        for search in search_dirs:
            candidate = search / filename
            if candidate.is_file():
                shutil.copy2(str(candidate), str(dst))
                copied.append((filename, candidate, str(search)))
                found = True
                break

        if not found:
            if required:
                missing.append((filename, desc))
            else:
                print(f"  SKIP (optional): {filename}")

    # Report
    print(f"\nAssembled project folder: {out_folder.resolve()}")
    for fname, src, note in copied:
        print(f"  COPIED: {fname} <- {note}")
    if missing:
        print(f"\n  WARNING — {len(missing)} required file(s) not found:")
        for fname, desc in missing:
            print(f"    MISSING: {fname} ({desc})")
        print("  You will need to manually place these before running in HEEDS.")
    else:
        print("  All required files present. Ready to open in HEEDS.")

    return out_folder


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate HEEDS .heeds project files for Nastran bolt looseness studies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate .heeds file only
  %(prog)s --bush-blk Bush.blk --study-type single_bolt_sweep --output sweep.heeds

  # Dry run — inspect the design matrix
  %(prog)s --bush-blk Bush.blk --study-type single_bolt_sweep --dry-run

  # Assemble a ready-to-run HEEDS project folder (copies all Nastran files in)
  %(prog)s --bush-blk Bush.blk --study-type single_bolt_sweep --output sweep.heeds --project-dir ./baseline
        """
    )
    parser.add_argument(
        "--bush-blk", required=True,
        help="Path to Bush.blk file to parse"
    )
    parser.add_argument(
        "--study-type", required=True,
        choices=["single_bolt_sweep", "two_bolt_sweep", "three_bolt_sweep", "all_bolt_sweep", "full_factorial", "latin_hypercube", "monte_carlo"],
        help="Type of study to generate"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output .heeds file path"
    )
    parser.add_argument(
        "--project-dir", default=None,
        help="Source directory containing Nastran project files (Bush.blk, .dat, .bat, etc.). "
             "When provided, assembles a ready-to-run HEEDS project folder with all files copied in."
    )
    parser.add_argument(
        "--template", default=None,
        help="Optional path to template .heeds to copy Process/MDO structure from (reserved for future use)"
    )
    parser.add_argument(
        "--skip-bolts", default="1",
        help='Comma-separated bolt numbers to skip (default: "1" for the driving bolt)'
    )
    parser.add_argument(
        "--levels", type=int, default=9,
        help="Number of stiffness levels (default: 9)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the design matrix without writing the file"
    )
    parser.add_argument(
        "--study-name", default=None,
        help="Name for the study/sweep (default: auto-generated from study type)"
    )
    parser.add_argument(
        "--num-modes", type=int, default=10,
        help="Number of modal responses to include (default: 10)"
    )
    parser.add_argument(
        "--n-samples", type=int, default=500,
        help="Number of Monte Carlo random samples (default: 500, only used with --study-type monte_carlo)"
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for Monte Carlo reproducibility (default: 42)"
    )
    parser.add_argument(
        "--structural-model", default=None,
        help="Nastran structural model filename (default: from config.yaml files.structural_model)"
    )
    parser.add_argument(
        "--random-response", default=None,
        help="Nastran random response filename (default: from config.yaml files.random_response)"
    )

    args = parser.parse_args()

    # Parse skip bolts
    try:
        skip_bolts = [int(x.strip()) for x in args.skip_bolts.split(",") if x.strip()]
    except ValueError:
        print(f"ERROR: --skip-bolts must be comma-separated integers, got: {args.skip_bolts}",
              file=sys.stderr)
        sys.exit(1)

    # Resolve config-driven filenames (CLI > config.yaml > error)
    _structural_model = args.structural_model
    _random_response = args.random_response
    if not _structural_model or not _random_response:
        try:
            import yaml as _yaml
            _cfg_path = Path(__file__).resolve().parent.parent / "fem_input" / "config.yaml"
            if _cfg_path.exists():
                with open(_cfg_path) as _cf:
                    _cfg = _yaml.safe_load(_cf) or {}
                if not _structural_model:
                    _structural_model = _cfg.get('files', {}).get('structural_model')
                if not _random_response:
                    _random_response = _cfg.get('files', {}).get('random_response')
        except Exception:
            pass
    if not _structural_model:
        print("ERROR: structural_model required via --structural-model or config.yaml", file=sys.stderr)
        sys.exit(1)
    if not _random_response:
        print("ERROR: random_response required via --random-response or config.yaml", file=sys.stderr)
        sys.exit(1)

    # Validate args
    if not args.dry_run and not args.output:
        print("ERROR: --output is required unless --dry-run is specified", file=sys.stderr)
        sys.exit(1)

    if args.study_type not in ("single_bolt_sweep", "two_bolt_sweep", "three_bolt_sweep", "all_bolt_sweep", "monte_carlo"):
        print(f"ERROR: --study-type '{args.study_type}' is not yet implemented.", file=sys.stderr)
        sys.exit(1)

    # Parse Bush.blk
    try:
        all_bolts = parse_bush_blk(args.bush_blk)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(all_bolts)} bolts from {args.bush_blk}")

    # Validate skip bolts
    all_bolt_nums = {b.bolt_num for b in all_bolts}
    invalid_skips = set(skip_bolts) - all_bolt_nums
    if invalid_skips:
        print(f"WARNING: Skip bolt numbers not found in Bush.blk: {sorted(invalid_skips)}",
              file=sys.stderr)

    variable_bolts = [b for b in all_bolts if b.bolt_num not in skip_bolts]
    if not variable_bolts:
        print("ERROR: No variable bolts remaining after applying --skip-bolts", file=sys.stderr)
        sys.exit(1)

    # Get stiffness levels
    try:
        levels = get_stiffness_levels(args.levels)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate study name
    if args.study_name:
        study_name = args.study_name
    else:
        if len(variable_bolts) == 1:
            study_name = f"bolt{variable_bolts[0].bolt_num}_sweep"
        else:
            study_name = f"bolt_sweep_{len(variable_bolts)}bolts_{len(levels)}levels"

    # Generate design matrix
    if args.study_type == "single_bolt_sweep":
        variable_bolts, designs, design_names = generate_single_bolt_sweep(
            all_bolts, skip_bolts, levels
        )
    elif args.study_type == "two_bolt_sweep":
        variable_bolts, designs, design_names = generate_two_bolt_sweep(
            all_bolts, skip_bolts, levels
        )
    elif args.study_type == "three_bolt_sweep":
        variable_bolts, designs, design_names = generate_three_bolt_sweep(
            all_bolts, skip_bolts, levels
        )
    elif args.study_type == "all_bolt_sweep":
        variable_bolts, designs, design_names = generate_all_bolt_sweep(
            all_bolts, skip_bolts, levels
        )
    elif args.study_type == "monte_carlo":
        variable_bolts, designs, design_names = generate_monte_carlo(
            all_bolts, skip_bolts, levels,
            n_samples=args.n_samples,
            seed=args.seed,
        )

    print(f"Study: {study_name}")
    print(f"Variable bolts: {len(variable_bolts)}, Levels: {len(levels)}, "
          f"Designs: {len(designs)}")

    # Dry run
    if args.dry_run:
        print()
        print_dry_run(study_name, variable_bolts, designs, design_names,
                      levels, all_bolts, skip_bolts)
        return

    # Generate XML
    xml_content = generate_heeds_xml(
        study_name=study_name,
        variable_bolts=variable_bolts,
        designs=designs,
        design_names=design_names,
        levels=levels,
        all_bolts=all_bolts,
        num_modes=args.num_modes,
        structural_model=_structural_model,
        random_response=_random_response,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_content, encoding="utf-8")
    print(f"Written: {output_path.resolve()}")
    print(f"  Variables: {len(variable_bolts) * 3}")
    print(f"  Designs: {len(designs)}")
    print(f"  numEvalsTotal: {len(designs)}")

    # Assemble project folder if --project-dir was given
    if args.project_dir:
        out_folder = assemble_project_folder(
            output_heeds=output_path,
            project_dir=args.project_dir,
            study_name=study_name,
            structural_model=_structural_model,
            random_response=_random_response,
        )
        # Also ensure Bush.blk from --bush-blk is in the folder
        bush_dst = out_folder / "Bush.blk"
        bush_src = Path(args.bush_blk)
        if bush_src.resolve() != bush_dst.resolve() and not bush_dst.exists():
            shutil.copy2(str(bush_src), str(bush_dst))
            print(f"  COPIED: Bush.blk <- {bush_src}")


if __name__ == "__main__":
    main()
