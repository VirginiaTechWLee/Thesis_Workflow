#!/usr/bin/env python3
"""
HEEDS XML Generator for Bolt Stiffness Diagonal Study
Generates complete .heeds file with 9 UserDesignSets (576 evaluations total)
"""

def generate_heeds_xml(output_file='generated_thesis_project.heeds'):
    """
    Generate complete HEEDS XML file for diagonal bolt stiffness study
    
    Parameters:
    -----------
    output_file : str
        Output filename for the generated .heeds file
    """
    
    # Configuration
    NUM_BOLTS = 10
    NUM_DOFS = 3  # K4, K5, K6
    SWEEP_LEVELS = [1, 4, 7, 10]  # Stiffness levels to sweep
    BASELINE_LEVEL = 9  # Baseline for non-swept bolts
    BOLT1_FIXED_LEVEL = 5  # Bolt 1 always fixed at this level
    NODES = [1, 111, 222, 333, 444, 555, 666, 777, 888, 999, 1010, 1111]
    
    # Response types
    ACCE_METRICS = ['Area', 'Frequency_1', 'PSD_1', 'Frequency_2', 'PSD_2', 'Frequency_3', 'PSD_3']
    DISP_METRICS = ['Area', 'Frequency_1', 'DISP_1', 'Frequency_2', 'DISP_2', 'Frequency_3', 'DISP_3']
    ACCE_DOFS = ['T1', 'T2', 'T3']
    DISP_DOFS = ['T1', 'T2', 'T3', 'R1', 'R2', 'R3']
    
    xml_lines = []
    
    # XML Header
    xml_lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    xml_lines.append('<root>')
    xml_lines.append('  <Project>')
    xml_lines.append('')
    
    # ===== VARIABLES SECTION =====
    xml_lines.append('    <Variables>')
    for bolt in range(1, NUM_BOLTS + 1):
        for dof in ['K4', 'K5', 'K6']:
            var_name = f"{dof}_{bolt}"
            xml_lines.append(f'      <Variable name="{var_name}" flags="2048" numInTags="1"/>')
    xml_lines.append('    </Variables>')
    xml_lines.append('')
    
    # ===== PROCESS/MDO SECTION =====
    xml_lines.append('    <Process name="Process_1" current="true" parallel="true">')
    xml_lines.append('      <MDO name="Analysis_1" active="true" solver="General">')
    xml_lines.append('        <Data type="MDO" resource="Local">')
    xml_lines.append('          <anlCommand value="FBM_TO_DBALL.bat"/>')
    xml_lines.append('          <primaryInput ref="HEEDS.Input.File.Fixed_base_beam.dat"/>')
    xml_lines.append('        </Data>')
    xml_lines.append('        <Inputs>')
    xml_lines.append('          <Input type="file" path="Bush.blk">')
    
    # Generate tags for each variable
    for bolt in range(1, NUM_BOLTS + 1):
        row = 2 * bolt - 1  # Row calculation: 1,3,5,7,9,11,13,15,17,19
        xml_lines.append(f'            <Tag variable="K4_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="6" charPos="48"/>')
        xml_lines.append(f'            <Tag variable="K5_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="7" charPos="56"/>')
        xml_lines.append(f'            <Tag variable="K6_{bolt}" type="HEEDS.Static.Format.Fixed 8" row="{row}" col="8" charPos="64"/>')
    
    xml_lines.append('          </Input>')
    xml_lines.append('        </Inputs>')
    xml_lines.append('      </MDO>')
    xml_lines.append('    </Process>')
    xml_lines.append('')
    
    # ===== RESPONSES SECTION =====
    xml_lines.append('    <Responses>')
    
    # Generate all response definitions
    response_names = []
    
    # Acceleration responses
    for node in NODES:
        for dof in ACCE_DOFS:
            for metric in ACCE_METRICS:
                resp_name = f"ACCE_{dof}_{metric}_Node_{node}"
                response_names.append(resp_name)
                xml_lines.append(f'      <Response name="{resp_name}"/>')
    
    # Acceleration Delta responses
    for node in NODES:
        for dof in ACCE_DOFS:
            for metric in ACCE_METRICS:
                resp_name = f"ACCE_{dof}_{metric}_Node_{node}Delta"
                response_names.append(resp_name)
                xml_lines.append(f'      <Response name="{resp_name}"/>')
    
    # Displacement responses
    for node in NODES:
        for dof in DISP_DOFS:
            for metric in DISP_METRICS:
                resp_name = f"DISP_{dof}_{metric}_Node_{node}"
                response_names.append(resp_name)
                xml_lines.append(f'      <Response name="{resp_name}"/>')
    
    # Displacement Delta responses
    for node in NODES:
        for dof in DISP_DOFS:
            for metric in DISP_METRICS:
                resp_name = f"DISP_{dof}_{metric}_Node_{node}_Delta"
                response_names.append(resp_name)
                xml_lines.append(f'      <Response name="{resp_name}"/>')
    
    xml_lines.append('    </Responses>')
    xml_lines.append('')
    
    # ===== STUDY SECTION =====
    xml_lines.append('    <Study name="Study_1" current="true" id="1">')
    xml_lines.append('      <Agent name="Search_1" type="EVAL" method=": DesignSweep" numEvalsTotal="576">')
    
    # Variable choices
    xml_lines.append('        <VariableChoices>')
    for bolt in range(1, NUM_BOLTS + 1):
        for dof in ['K4', 'K5', 'K6']:
            var_name = f"{dof}_{bolt}"
            choices_str = ';'.join([f"1.+{i}" for i in range(4, 15)])  # 1e4 through 1e14
            xml_lines.append(f'          <SnapShot name="choices" variable="{var_name}" list="{choices_str}"/>')
    xml_lines.append('        </VariableChoices>')
    xml_lines.append('')
    
    # RunOptions
    xml_lines.append('        <RunOptions>')
    xml_lines.append('          <CaptureOutput value="true"/>')
    xml_lines.append('          <IgnoreBaseline value="false"/>')
    xml_lines.append('          <ResponseOut value="true"/>')
    xml_lines.append('          <SaveHistory value="true"/>')
    xml_lines.append('          <SaveRestart value="true"/>')
    xml_lines.append('          <UseBaseline value="false"/>')
    xml_lines.append('        </RunOptions>')
    xml_lines.append('')
    
    # ===== METHOD DATA - 9 UserDesignSets =====
    xml_lines.append('        <MethodData>')
    
    # Generate 9 UserDesignSets (one for each bolt 2-10)
    for set_num in range(1, 10):
        bolt_to_sweep = set_num + 1  # Bolt 2-10
        xml_lines.append(f'          <UserDesignSet name="Set_{set_num}" status="pending">')
        
        # 64 Design entries
        for i in range(1, 65):
            xml_lines.append(f'            <Design name="sweep_{i}" map="false" resp="false"/>')
        
        # Generate Data section with header and 64 rows
        xml_lines.append('            <Data><![CDATA[')
        
        # Header row
        header_parts = []
        for bolt in range(1, NUM_BOLTS + 1):
            header_parts.extend([f'K4_{bolt}', f'K5_{bolt}', f'K6_{bolt}'])
        header_parts.extend(['Response_Array', 'X_values', 'Modes1', 'Modes2', 'Modes3', 
                            'Modes4', 'Modes5', 'Modes6', 'Modes7', 'Modes8', 'Modes9', 'Modes10',
                            '_1st_PSDresp', '_2nd_PSDresp', '_3rd_PSDresp', '_4th_PSDresp',
                            '_5th_PSDresp', '_6th_PSDresp', '_7th_PSDresp', '_8th_PSDresp',
                            '_9th_PSDresp', '_10th_PSDresp'])
        header_parts.extend(response_names)
        
        header_line = ' ' + ', '.join(header_parts)
        xml_lines.append(header_line)
        
        # Generate 64 data rows (4x4x4 factorial)
        for k4_level in SWEEP_LEVELS:
            for k5_level in SWEEP_LEVELS:
                for k6_level in SWEEP_LEVELS:
                    row_values = []
                    
                    for bolt in range(1, NUM_BOLTS + 1):
                        if bolt == 1:
                            # Bolt 1 always fixed at level 5
                            row_values.extend([BOLT1_FIXED_LEVEL, BOLT1_FIXED_LEVEL, BOLT1_FIXED_LEVEL])
                        elif bolt == bolt_to_sweep:
                            # This is the bolt we're sweeping
                            row_values.extend([k4_level, k5_level, k6_level])
                        else:
                            # All other bolts at baseline
                            row_values.extend([BASELINE_LEVEL, BASELINE_LEVEL, BASELINE_LEVEL])
                    
                    # Add placeholder for response columns (not populated in template)
                    # Format with proper spacing
                    formatted_values = [f"{v:5d}" for v in row_values[:3]]  # First 3 values
                    for i in range(3, len(row_values), 3):
                        formatted_values.extend([f"{v:5d}" for v in row_values[i:i+3]])
                    
                    row_line = '   ' + ',   '.join(formatted_values)
                    xml_lines.append(row_line)
        
        xml_lines.append(']]></Data>')
        xml_lines.append('          </UserDesignSet>')
        
        if set_num < 9:
            xml_lines.append('')
    
    xml_lines.append('        </MethodData>')
    xml_lines.append('      </Agent>')
    xml_lines.append('    </Study>')
    xml_lines.append('  </Project>')
    xml_lines.append('</root>')
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml_lines))
    
    print(f"✓ Generated HEEDS file: {output_file}")
    print(f"  - {NUM_BOLTS} bolts with {NUM_DOFS} DOFs each ({NUM_BOLTS * NUM_DOFS} variables)")
    print(f"  - {len(response_names)} response definitions")
    print(f"  - 9 UserDesignSets × 64 designs = 576 total evaluations")
    print(f"  - Sweep levels: {SWEEP_LEVELS}")
    print(f"  - Bolt 1 fixed at level {BOLT1_FIXED_LEVEL}, others at baseline {BASELINE_LEVEL}")


if __name__ == '__main__':
    generate_heeds_xml()