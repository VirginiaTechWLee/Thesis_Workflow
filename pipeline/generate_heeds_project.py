"""
Generate HEEDS .heeds project file from config.yaml.

Produces XML that exactly matches the structure of the working
bolt3_sweep.heeds (HEEDS 2410 compatible). All model-specific values
come from config.yaml — no hardcoded beam parameters.

Usage:
    python pipeline/generate_heeds_project.py
    python pipeline/generate_heeds_project.py --output heeds/projects/my_study.heeds
"""

import sys
import os
import argparse
import math
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config, nastran_shorthand


def generate_heeds_project(config_path=None, output_path=None):
    """Generate a .heeds project file from config.yaml."""
    config = load_config(config_path)
    study = config['study']

    # Allow workflow to override study type via env var
    study_type_override = os.environ.get('STUDY_TYPE_OVERRIDE', '').strip()
    if study_type_override:
        study_type_map = {
            'study_A': ('single_bolt_sweep', 'study_A_single_bolt_sweep'),
            'study_B': ('two_bolt_sweep', 'study_B_two_bolt_sweep'),
            'study_C': ('three_bolt_sweep', 'study_C_three_bolt_sweep'),
            'study_D': ('monte_carlo', 'study_D_monte_carlo'),
            'study_E': ('all_bolt_sweep', 'study_E_all_bolt_sweep'),
        }
        if study_type_override in study_type_map:
            stype, sname = study_type_map[study_type_override]
            study['type'] = stype
            study['name'] = sname
    files = config['files']
    bolts = config['bolts']
    paths = config['paths']

    study_name = study['name']
    sweep_bolts = study.get('sweep_bolts', [3])
    sweep_levels = study.get('sweep_levels', [1e6, 1e7, 1e8, 1e10, 1e12])

    # Compute expected designs dynamically based on study type
    from math import comb as _comb
    study_type = study.get('type', 'sweep')
    n_bolts = len(sweep_bolts)
    n_non_baseline = len(sweep_levels) - 1
    if study_type == 'single_bolt_sweep':
        expected_designs = n_bolts * n_non_baseline + 1  # +1 shared baseline design
    elif study_type == 'two_bolt_sweep':
        expected_designs = _comb(n_bolts, 2) * n_non_baseline
    elif study_type == 'three_bolt_sweep':
        expected_designs = _comb(n_bolts, 3) * n_non_baseline
    elif study_type == 'all_bolt_sweep':
        expected_designs = n_non_baseline
    elif study_type == 'monte_carlo':
        n_samples = config.get('monte_carlo', {}).get('n_samples', 500)
        expected_designs = n_samples + 1  # +1 for baseline design
    else:
        expected_designs = study.get('expected_designs', len(sweep_levels))

    # Pass monte_carlo config through to _build_xml via the study dict
    if study_type == 'monte_carlo':
        study['_monte_carlo_config'] = config.get('monte_carlo', {})

    if output_path is None:
        output_path = f"{study_name}.heeds"

    xml = _build_xml(
        study_name=study_name,
        sweep_bolts=sweep_bolts,
        sweep_levels=sweep_levels,
        expected_designs=expected_designs,
        files=files,
        paths=paths,
        bolts=bolts,
        study=study,
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml)

    print(f"Generated: {output_path}")
    print(f"  Study: {study_name}")
    print(f"  Sweep bolts: {sweep_bolts}")
    print(f"  Levels: {len(sweep_levels)} ({[f'{l:.0e}' for l in sweep_levels]})")
    print(f"  Expected designs: {expected_designs}")
    return output_path


def _build_xml(study_name, sweep_bolts, sweep_levels, expected_designs,
               files, paths, bolts, study=None):
    """Build the complete HEEDS XML string."""

    structural_model = files['structural_model']
    random_response = files.get('random_response', 'RandomBeamX.dat')
    bush_template = files.get('bush_template', 'Bush.blk')
    recoveries = files.get('recoveries', 'Recoveries.blk')
    postprocessor = files.get('postprocessor', 'Pch_TO_CSV2.py')
    heeds_python = paths['heeds_python']

    # --- Stiffness Set items in Nastran notation ---
    set_items = [nastran_shorthand(lv) for lv in sweep_levels]

    # --- Variable names: K4, K5, K6 per swept bolt ---
    variables = []
    for bolt in sweep_bolts:
        for dof in ['K4', 'K5', 'K6']:
            variables.append(f"{dof}_bolt{bolt}")

    # --- Set XML ---
    set_xml = '\n'.join(f'    <Item value="{item}"/>' for item in set_items)

    # --- Variable declarations ---
    var_xml = '\n'.join(
        f'  <Variable name="{v}" flags="2048" numInTags="1"/>'
        for v in variables
    )

    # --- Response declarations (mode frequencies from f06) ---
    resp_lines = ['  <Response name="Response_Array" type="File" acceptMax="" acceptMin="" flags="2048" numOutTags="1"/>']
    for i in range(1, 11):
        resp_lines.append(f'  <Response name="Modes{i}" type="Formula" acceptMax="" acceptMin="" formula="Response_Array[{i}-1]"/>')
    resp_xml = '\n'.join(resp_lines)

    # --- Bush.blk input tags ---
    # In Femap format (comment + PBUSH per bolt), bolt N PBUSH is at row 2*N-1 (0-based)
    tag_lines = []
    for bolt in sweep_bolts:
        row = 2 * bolt - 1
        for dof, col, char_col in [('K4', 6, 48), ('K5', 7, 56), ('K6', 8, 64)]:
            var_name = f"{dof}_bolt{bolt}"
            tag_lines.append(
                f'            <Tag charCol="{char_col}" col="{col}" '
                f'format="HEEDS.Static.Format.Fixed 8" mode="fixed" '
                f'ref="HEEDS.Parameter.Variable.{var_name}" row="{row}"/>'
            )
    tags_xml = '\n'.join(tag_lines)

    # --- Agent variable declarations (Discrete, referencing Set) ---
    agent_var_lines = []
    for v in variables:
        agent_var_lines.append(
            f'      <Variable name="{v}" type="Discrete" baseline="1" '
            f'ref="HEEDS.Parameter.Variable.{v}" '
            f'set_ref="HEEDS.Attribute.Set.set_{study_name}_K" state="Required"/>'
        )
    agent_vars_xml = '\n'.join(agent_var_lines)

    # --- Agent response declarations ---
    agent_resp_lines = ['      <Response name="Response_Array" ref="HEEDS.Parameter.Response.Response_Array" state="Required"/>']
    for i in range(1, 11):
        agent_resp_lines.append(f'      <Response name="Modes{i}" ref="HEEDS.Parameter.Response.Modes{i}" state="Included"/>')
    agent_resp_xml = '\n'.join(agent_resp_lines)

    # --- UserDesignSet: design names and CDATA rows ---
    study_type = study.get('type', 'sweep') if study else 'sweep'
    num_levels = len(sweep_levels)
    baseline_idx = num_levels  # 1-based index of tight/baseline value

    design_name_lines = []
    data_rows = []

    if study_type == 'single_bolt_sweep':
        # Single-bolt sweep: loosen ONE bolt at a time, rest at baseline
        for bolt in sweep_bolts:
            for level_i, level in enumerate(sweep_levels):
                set_idx = level_i + 1
                exp_str = f"{level:.0e}"
                e_part = exp_str.split('e+')[1] if 'e+' in exp_str else exp_str.split('e')[1]
                name = f"bolt{bolt}_1e{int(e_part)}"
                design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')

                # Build row: this bolt at set_idx, all others at baseline_idx
                row_vals = []
                for var in variables:
                    # var is like "K4_bolt2" — extract bolt number
                    var_bolt = int(var.split('bolt')[1])
                    if var_bolt == bolt:
                        row_vals.append(f'    {set_idx}')
                    else:
                        row_vals.append(f'    {baseline_idx}')
                data_rows.append(','.join(row_vals))
    elif study_type == 'two_bolt_sweep':
        # Two-bolt sweep: loosen TWO bolts simultaneously, rest at baseline
        from itertools import combinations
        for bolt_a, bolt_b in combinations(sweep_bolts, 2):
            for level_i, level in enumerate(sweep_levels):
                set_idx = level_i + 1
                # Skip baseline-level designs (both bolts tight = no damage)
                if set_idx == baseline_idx:
                    continue
                exp_str = f"{level:.0e}"
                e_part = exp_str.split('e+')[1] if 'e+' in exp_str else exp_str.split('e')[1]
                name = f"bolt{bolt_a}_bolt{bolt_b}_1e{int(e_part)}"
                design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')

                # Build row: both bolts in pair at set_idx, all others at baseline_idx
                row_vals = []
                for var in variables:
                    var_bolt = int(var.split('bolt')[1])
                    if var_bolt in (bolt_a, bolt_b):
                        row_vals.append(f'    {set_idx}')
                    else:
                        row_vals.append(f'    {baseline_idx}')
                data_rows.append(','.join(row_vals))
    elif study_type == 'three_bolt_sweep':
        # Three-bolt sweep: loosen THREE bolts simultaneously, rest at baseline
        from itertools import combinations
        for bolt_a, bolt_b, bolt_c in combinations(sweep_bolts, 3):
            for level_i, level in enumerate(sweep_levels):
                set_idx = level_i + 1
                if set_idx == baseline_idx:
                    continue
                exp_str = f"{level:.0e}"
                e_part = exp_str.split('e+')[1] if 'e+' in exp_str else exp_str.split('e')[1]
                name = f"bolt{bolt_a}_bolt{bolt_b}_bolt{bolt_c}_1e{int(e_part)}"
                design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')

                row_vals = []
                for var in variables:
                    var_bolt = int(var.split('bolt')[1])
                    if var_bolt in (bolt_a, bolt_b, bolt_c):
                        row_vals.append(f'    {set_idx}')
                    else:
                        row_vals.append(f'    {baseline_idx}')
                data_rows.append(','.join(row_vals))
    elif study_type == 'all_bolt_sweep':
        # All-bolt sweep: all bolts loosen together (Study E — fully degraded)
        for level_i, level in enumerate(sweep_levels):
            set_idx = level_i + 1
            if set_idx == baseline_idx:
                continue
            exp_str = f"{level:.0e}"
            e_part = exp_str.split('e+')[1] if 'e+' in exp_str else exp_str.split('e')[1]
            name = f"all_bolts_1e{int(e_part)}"
            design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')
            data_rows.append(','.join([f'    {set_idx}'] * len(variables)))
    elif study_type == 'monte_carlo':
        # Monte Carlo: random independent sampling of discrete stiffness levels
        import numpy as np
        mc_config = study.get('_monte_carlo_config', {})
        n_samples = mc_config.get('n_samples', 500)
        seed = mc_config.get('seed', 42)
        rng = np.random.default_rng(seed)

        # All level indices (1-based): includes baseline — Monte Carlo can randomly assign tight bolts
        all_indices = list(range(1, num_levels + 1))

        # Design 1: baseline (all bolts at baseline)
        design_name_lines.append(f'        <Design name="monte_carlo_001" map="false" resp="false"/>')
        data_rows.append(','.join([f'    {baseline_idx}'] * len(variables)))

        # Designs 2 through n_samples+1: random sampling from ALL levels
        for i in range(2, n_samples + 2):
            name = f"monte_carlo_{i:03d}"
            design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')
            # Assign one random level per bolt, then K4/K5/K6 all get same index
            bolt_levels = {}
            for var in variables:
                var_bolt = int(var.split('bolt')[1])
                if var_bolt not in bolt_levels:
                    bolt_levels[var_bolt] = int(rng.choice(all_indices))
            row_vals = []
            for var in variables:
                var_bolt = int(var.split('bolt')[1])
                row_vals.append(f'    {bolt_levels[var_bolt]}')
            data_rows.append(','.join(row_vals))
    else:
        # Default sweep: all bolts get the same level simultaneously
        for level_i, level in enumerate(sweep_levels):
            set_idx = level_i + 1
            exp_str = f"{level:.0e}"
            e_part = exp_str.split('e+')[1] if 'e+' in exp_str else exp_str.split('e')[1]
            bolt_str = '_'.join(str(b) for b in sweep_bolts)
            name = f"bolt{bolt_str}_1e{int(e_part)}"
            design_name_lines.append(f'        <Design name="{name}" map="false" resp="false"/>')
            data_rows.append(','.join([f'    {set_idx}'] * len(variables)))

    design_names_xml = '\n'.join(design_name_lines)

    header_parts = variables + ['Response_Array'] + [f'Modes{i}' for i in range(1, 11)]
    data_header = ', '.join(header_parts)
    data_block = '\n'.join(data_rows)

    # --- f06 filename (lowercase of structural model with .f06 extension) ---
    f06_name = structural_model.rsplit('.', 1)[0].lower() + '.f06'

    # --- Timestamp ---
    now_iso = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    # --- Delimiters string (verbatim from working .heeds) ---
    delim = '&quot;,&quot;,;,&quot;&quot;,=,(,),\',\\t,\\s'

    # --- Build the full XML ---
    xml = f'''<?xml version='1.0' encoding='UTF-8'?>
<!DOCTYPE HEEDSProject>
<!--       HEEDS Data Model document
    Copyright (c) 2024 Siemens. All rights reserved.

    {study_name} - Auto-generated from fem_input/config.yaml
    Generated: {now_iso}
    Sweep bolts: {sweep_bolts}
    Levels: {len(sweep_levels)} designs
-->
<Project app="HEEDSMDO" build="241030" version="2410.0">
  <!--Project Data-->
  <Meta name="scriptEngine">Python3</Meta>

  <!--HEEDS.Attribute.Set-->
  <Set name="set_{study_name}_K" ordered="1">
{set_xml}
  </Set>

  <!--HEEDS.Attribute.Condition-->
  <Condition name="Condition_1">
    <Item type="FileContain" anlRef="HEEDS.Analysis.File.MDO.Analysis_1" findRef="HEEDS.Output.File.randombeamx.f06" findText="* * * END OF JOB * * *" op="and"/>
  </Condition>

  <!--HEEDS.Parameter.Variable-->
{var_xml}

  <!--HEEDS.Parameter.Response-->
{resp_xml}

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
        <VisFile type="data" filename="randombeamx.pch" source="analysisFolder"/>
        <VisFile type="data" filename="{bush_template}" source="analysisFolder"/>
<primaryInput ref="HEEDS.Input.File.{structural_model}"/>
        <Reservation active="false" mode="share"/>
        <FinishCondition ref="HEEDS.Attribute.Condition.Condition_1"/>
        <RunCondition folder="designFolder" ref="" resource="LOCAL"/>
        <SuccessCondition ref=""/>
      </Data>

      <!--Inputs-->
      <Inputs>
        <Input type="file" path="{bush_template}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">8</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
{tags_xml}
          </Data>
        </Input>
        <Input type="file" path="{structural_model}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
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
        <Input type="file" path="{recoveries}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
          </Data>
        </Input>
        <Input type="file" path="{postprocessor}">
          <Data>
            <source value="projectFolder"/>
            <target value="analysisFolder"/>
          </Data>
        </Input>
      </Inputs>

      <!--Outputs-->
      <Outputs>
        <Output type="file" path="{f06_name}">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">8</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
            <Tag mode="script" ref="HEEDS.Parameter.Response.Response_Array"><![CDATA[SET_PARAMETER_LIST(%names%) $ auto-generated parameter name list
GOTO_STRING('FRACTION', 3)
MOVE_DOWN(2)
GET_COLUMN_FREE(2, -1,',= ')]]></Tag>
          </Data>
        </Output>
        <Output type="file" path="randombeamx.f06">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">10</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="randombeamx.pch">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">10</widths>
            <Meta name="ForceReparse" value="true"/>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="acceleration_results.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="displacement_results.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="acceleration_results_delta.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
            <widths list="int">10</widths>
            <Meta name="hidden" value=""/>
          </Data>
        </Output>
        <Output type="file" path="displacement_results_delta.csv">
          <Data>
            <source value="analysisFolder"/>
            <delimiters delim="," list="string">{delim}</delimiters>
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
  </Process>

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
    </RunOptions>

    <!--HEEDS.Agent-->
    <Agent name="Sweep_1" type="EVAL" checksum="5a98" evalFolder="" id="0" lastUpdate="{now_iso}" method=": DesignSweep" numEvalsTotal="{expected_designs}" outputPrecision="16" postfolder="POST_0" prefix="HEEDS" saveErrorMode="saveOnly" saveMode="None">
      <Process ref="HEEDS.Process.Process_1"/>

      <!--HEEDS.AgentParameter.Variable-->
{agent_vars_xml}

      <!--HEEDS.AgentParameter.Response-->
{agent_resp_xml}

      <!--HEEDS.UserDesignSet — {expected_designs} deterministic designs-->
      <UserDesignSet name="{study_name}">
{design_names_xml}
        <Data><![CDATA[
 {data_header}
{data_block}
]]></Data>
      </UserDesignSet>

      <MethodData type="OPT">
        <numEvals value="150"/>
        <method value="SHERPA"/>
        <SHERPA numEvals="150"/>
      </MethodData>
      <MethodData type="EVAL" numEvals="{expected_designs}"/>

      <Designs>
        <data><![CDATA[
 Cycle #, Eval #, Source, Status
]]></data>
      </Designs>
    </Agent>

    <!--HEEDS.DesignSet-->
    <DesignSet name="All Designs" type="5" agent="HEEDS.Agent.Sweep_1" flag="62"/>
    <DesignSet name="Non-Error Designs" type="4" agent="HEEDS.Agent.Sweep_1" flag="46"/>
    <DesignSet name="{study_name}" agent="HEEDS.Agent.Sweep_1" flag="32" source="{study_name}"/>
  </Study>

  <!--HEEDS.Static.Equation-->
  <StaticEquation name="_desMin" active="true"/>
  <StaticEquation name="_desMax" active="true"/>
  <StaticEquation name="_bestVal" active="true"/>
  <StaticEquation name="_desVal" active="true"/>
</Project>
'''
    return xml


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate HEEDS .heeds project from config")
    parser.add_argument('--config', help='Path to config.yaml')
    parser.add_argument('--output', '-o', help='Output .heeds file path')
    args = parser.parse_args()
    generate_heeds_project(args.config, args.output)
