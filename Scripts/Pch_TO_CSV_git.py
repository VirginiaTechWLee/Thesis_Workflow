import pandas as pd
import numpy as np
import os
import argparse

# Global variables
data_dict = {}
acce_count = 0
disp_count = 0
total_frequencies = 0
total_psd_columns = 0
node_ids = set()

# Custom measurement names
ACCE_MEASUREMENTS = [
    "ACCE_T1_Area", "ACCE_T1_Frequency_1", "ACCE_T1_PSD_1", "ACCE_T1_Frequency_2", "ACCE_T1_PSD_2",
    "ACCE_T1_Frequency_3", "ACCE_T1_PSD_3",
    "ACCE_T2_Area", "ACCE_T2_Frequency_1", "ACCE_T2_PSD_1", "ACCE_T2_Frequency_2", "ACCE_T2_PSD_2",
    "ACCE_T2_Frequency_3", "ACCE_T2_PSD_3",
    "ACCE_T3_Area", "ACCE_T3_Frequency_1", "ACCE_T3_PSD_1", "ACCE_T3_Frequency_2", "ACCE_T3_PSD_2",
    "ACCE_T3_Frequency_3", "ACCE_T3_PSD_3",
    "ACCE_R1_Area", "ACCE_R1_Frequency_1", "ACCE_R1_PSD_1", "ACCE_R1_Frequency_2", "ACCE_R1_PSD_2",
    "ACCE_R1_Frequency_3", "ACCE_R1_PSD_3",
    "ACCE_R2_Area", "ACCE_R2_Frequency_1", "ACCE_R2_PSD_1", "ACCE_R2_Frequency_2", "ACCE_R2_PSD_2",
    "ACCE_R2_Frequency_3", "ACCE_R2_PSD_3",
    "ACCE_R3_Area", "ACCE_R3_Frequency_1", "ACCE_R3_PSD_1", "ACCE_R3_Frequency_2", "ACCE_R3_PSD_2",
    "ACCE_R3_Frequency_3", "ACCE_R3_PSD_3"
]

DISP_MEASUREMENTS = [
    "DISP_T1_Area", "DISP_T1_Frequency_1", "DISP_T1_DISP_1", "DISP_T1_Frequency_2", "DISP_T1_DISP_2",
    "DISP_T1_Frequency_3", "DISP_T1_DISP_3",
    "DISP_T2_Area", "DISP_T2_Frequency_1", "DISP_T2_DISP_1", "DISP_T2_Frequency_2", "DISP_T2_DISP_2",
    "DISP_T2_Frequency_3", "DISP_T2_DISP_3",
    "DISP_T3_Area", "DISP_T3_Frequency_1", "DISP_T3_DISP_1", "DISP_T3_Frequency_2", "DISP_T3_DISP_2",
    "DISP_T3_Frequency_3", "DISP_T3_DISP_3",
    "DISP_R1_Area", "DISP_R1_Frequency_1", "DISP_R1_DISP_1", "DISP_R1_Frequency_2", "DISP_R1_DISP_2",
    "DISP_R1_Frequency_3", "DISP_R1_DISP_3",
    "DISP_R2_Area", "DISP_R2_Frequency_1", "DISP_R2_DISP_1", "DISP_R2_Frequency_2", "DISP_R2_DISP_2",
    "DISP_R2_Frequency_3", "DISP_R2_DISP_3",
    "DISP_R3_Area", "DISP_R3_Frequency_1", "DISP_R3_DISP_1", "DISP_R3_Frequency_2", "DISP_R3_DISP_2",
    "DISP_R3_Frequency_3", "DISP_R3_DISP_3"
]


def determine_translation_id(translation_id):
    """Convert numeric translation ID to named degree of freedom"""
    translation_mapping = {
        3: "T1",
        4: "T2",
        5: "T3",
        6: "R1",
        7: "R2",
        8: "R3"
    }
    return translation_mapping.get(translation_id, f"UNKNOWN-{translation_id}")


def process_data_blocks(lines):
    """Process ACCE and DISP data blocks from the input file"""
    global total_psd_columns, acce_count, disp_count, node_ids
    iterator = iter(lines)
    current_header = None

    while True:
        line = next(iterator, None)
        if line is None:
            break

        if line.startswith('$ACCE'):
            acce_count += 1
            parts = line.split()
            if len(parts) >= 5:
                node_id = parts[2]
                node_ids.add(node_id)
                translation_id = int(parts[3])
                translation_id_name = determine_translation_id(translation_id)
                current_header = f'ACCE-{node_id}-{translation_id_name}'

                if current_header not in data_dict:
                    data_dict[current_header] = []
                    total_psd_columns += 1

        elif line.startswith('$DISP'):
            disp_count += 1
            parts = line.split()
            if len(parts) >= 5:
                node_id = parts[2]
                node_ids.add(node_id)
                translation_id = int(parts[3])
                translation_id_name = determine_translation_id(translation_id)
                current_header = f'DISP-{node_id}-{translation_id_name}'

                if current_header not in data_dict:
                    data_dict[current_header] = []
                    total_psd_columns += 1

        elif line.strip() and current_header is not None:
            psd_parts = line.split()
            if len(psd_parts) >= 4:
                try:
                    psd = float(psd_parts[2])
                    data_dict[current_header].append(psd)
                except (ValueError, IndexError):
                    pass

        elif not line.strip():
            current_header = None


def extract_frequency(lines):
    """Extract frequency data from the input file"""
    global total_frequencies

    if 'Frequency' not in data_dict:
        data_dict['Frequency'] = []

    within_data_block = False

    for line in lines:
        if line.startswith('$ACCE') or line.startswith('$DISP'):
            within_data_block = True
        elif within_data_block:
            if line.strip() == '':
                within_data_block = False
            else:
                frequency_parts = line.split()
                if len(frequency_parts) >= 4:
                    try:
                        frequency = float(frequency_parts[1])
                        if frequency not in data_dict['Frequency']:
                            data_dict['Frequency'].append(frequency)
                            total_frequencies += 1
                    except (ValueError, IndexError):
                        continue


def find_top_three_local_maxima(df):
    """Find the top three local maxima in each PSD column."""
    inflection_points = []

    for header in df.columns[1:]:
        psd_values = df[header].values
        frequencies = df['Frequency'].values

        window_size = min(5, len(psd_values) // 10 + 1)
        if window_size > 1 and len(psd_values) > window_size:
            smooth_psd = np.convolve(psd_values, np.ones(window_size) / window_size, mode='same')
        else:
            smooth_psd = psd_values

        is_local_maxima = np.zeros_like(psd_values, dtype=bool)
        for i in range(1, len(smooth_psd) - 1):
            if smooth_psd[i] > smooth_psd[i - 1] and smooth_psd[i] > smooth_psd[i + 1]:
                is_local_maxima[i] = True

        if not np.any(is_local_maxima):
            top_indices = np.argsort(psd_values)[-3:]
            is_local_maxima[top_indices] = True

        local_maximas = [(frequencies[i], psd_values[i]) for i in np.where(is_local_maxima)[0]]

        if len(local_maximas) < 3:
            non_maxima_indices = np.where(~is_local_maxima)[0]
            sorted_indices = non_maxima_indices[np.argsort(psd_values[non_maxima_indices])]
            for idx in sorted_indices[::-1]:
                if len(local_maximas) >= 3:
                    break
                local_maximas.append((frequencies[idx], psd_values[idx]))

        local_maximas_sorted = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]
        local_maximas_sorted = sorted(local_maximas_sorted, key=lambda x: x[0])

        inflection_point_dict = {'Channel': header}

        for rank, (freq, psd) in enumerate(local_maximas_sorted, start=1):
            inflection_point_dict[f'Frequency_{rank}'] = freq
            inflection_point_dict[f'PSD_{rank}'] = psd

        for missing_rank in range(len(local_maximas_sorted) + 1, 4):
            inflection_point_dict[f'Frequency_{missing_rank}'] = np.nan
            inflection_point_dict[f'PSD_{missing_rank}'] = np.nan

        inflection_points.append(inflection_point_dict)

    return inflection_points


def process_pch_to_csv(input_file, output_dir=None, acce_filename='acceleration_results.csv', 
                       disp_filename='displacement_results.csv'):
    """
    Process PCH file and create acceleration and displacement CSV files.
    
    Args:
        input_file: Path to the input PCH file
        output_dir: Directory for output files (default: same as input file)
        acce_filename: Name for acceleration output file
        disp_filename: Name for displacement output file
    
    Returns:
        Tuple of (acce_output_path, disp_output_path) or (None, None) on failure
    """
    global data_dict, acce_count, disp_count, total_frequencies, total_psd_columns, node_ids

    # Reset global variables
    data_dict = {}
    acce_count = 0
    disp_count = 0
    total_frequencies = 0
    total_psd_columns = 0
    node_ids = set()

    # Determine output directory
    if output_dir is None:
        output_dir = os.path.dirname(input_file)
        if not output_dir:
            output_dir = '.'
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    acce_output_path = os.path.join(output_dir, acce_filename)
    disp_output_path = os.path.join(output_dir, disp_filename)

    try:
        print(f"Processing PCH file: {input_file}")
        
        with open(input_file, 'r') as file:
            lines = file.readlines()
            process_data_blocks(lines)

        with open(input_file, 'r') as file:
            lines = file.readlines()
            extract_frequency(lines)

        if 'Frequency' in data_dict:
            data_dict['Frequency'] = sorted(data_dict['Frequency'])

        original_df = pd.DataFrame(data_dict)

        if original_df.empty:
            print(f"WARNING: No data was extracted from {input_file}")
            return None, None

        # Process data for each node
        acce_data = []
        disp_data = []
        dof_types = ['T1', 'T2', 'T3', 'R1', 'R2', 'R3']

        for node_id in sorted(node_ids, key=lambda x: int(x) if x.isdigit() else float('inf')):
            acce_node_data = {}
            disp_node_data = {}

            for dof in dof_types:
                acce_key = f'ACCE-{node_id}-{dof}'
                disp_key = f'DISP-{node_id}-{dof}'

                # Process acceleration data
                if acce_key in original_df.columns:
                    acce_values = original_df[acce_key].values
                    frequencies = original_df['Frequency'].values
                    area = np.trapz(acce_values, x=frequencies)

                    temp_df = pd.DataFrame({'Frequency': original_df['Frequency'], acce_key: original_df[acce_key]})
                    maxima_data = find_top_three_local_maxima(temp_df)[0]

                    acce_node_data[f'{dof}_Area'] = area
                    for i in range(1, 4):
                        acce_node_data[f'{dof}_Frequency_{i}'] = maxima_data.get(f'Frequency_{i}', np.nan)
                        acce_node_data[f'{dof}_PSD_{i}'] = maxima_data.get(f'PSD_{i}', np.nan)
                else:
                    if dof in ['R1', 'R2', 'R3']:
                        acce_node_data[f'{dof}_Area'] = 0
                        for i in range(1, 4):
                            acce_node_data[f'{dof}_Frequency_{i}'] = 0
                            acce_node_data[f'{dof}_PSD_{i}'] = 0
                    else:
                        acce_node_data[f'{dof}_Area'] = np.nan
                        for i in range(1, 4):
                            acce_node_data[f'{dof}_Frequency_{i}'] = np.nan
                            acce_node_data[f'{dof}_PSD_{i}'] = np.nan

                # Process displacement data
                if disp_key in original_df.columns:
                    disp_values = original_df[disp_key].values
                    frequencies = original_df['Frequency'].values
                    area = np.trapz(disp_values, x=frequencies)

                    temp_df = pd.DataFrame({'Frequency': original_df['Frequency'], disp_key: original_df[disp_key]})
                    maxima_data = find_top_three_local_maxima(temp_df)[0]

                    disp_node_data[f'{dof}_Area'] = area
                    for i in range(1, 4):
                        disp_node_data[f'{dof}_Frequency_{i}'] = maxima_data.get(f'Frequency_{i}', np.nan)
                        disp_node_data[f'{dof}_PSD_{i}'] = maxima_data.get(f'PSD_{i}', np.nan)
                else:
                    disp_node_data[f'{dof}_Area'] = np.nan
                    for i in range(1, 4):
                        disp_node_data[f'{dof}_Frequency_{i}'] = np.nan
                        disp_node_data[f'{dof}_PSD_{i}'] = np.nan

            acce_data.append({'Node': node_id, 'Measurement': 'Acceleration', **acce_node_data})
            disp_data.append({'Node': node_id, 'Measurement': 'Displacement', **disp_node_data})

        acce_df = pd.DataFrame(acce_data)
        disp_df = pd.DataFrame(disp_data)

        # Create transposed DataFrames
        acce_df_transposed = pd.DataFrame(columns=['Measurement'])
        disp_df_transposed = pd.DataFrame(columns=['Measurement'])

        acce_df_transposed['Measurement'] = ACCE_MEASUREMENTS
        disp_df_transposed['Measurement'] = DISP_MEASUREMENTS

        # Define mappings
        acce_name_mapping = {}
        for dof in dof_types:
            acce_name_mapping[f'{dof}_Area'] = f'ACCE_{dof}_Area'
            for i in range(1, 4):
                acce_name_mapping[f'{dof}_Frequency_{i}'] = f'ACCE_{dof}_Frequency_{i}'
                acce_name_mapping[f'{dof}_PSD_{i}'] = f'ACCE_{dof}_PSD_{i}'

        disp_name_mapping = {}
        for dof in dof_types:
            disp_name_mapping[f'{dof}_Area'] = f'DISP_{dof}_Area'
            for i in range(1, 4):
                disp_name_mapping[f'{dof}_Frequency_{i}'] = f'DISP_{dof}_Frequency_{i}'
                disp_name_mapping[f'{dof}_PSD_{i}'] = f'DISP_{dof}_DISP_{i}'

        # Add data for each node as a column
        for node_id in sorted(node_ids, key=lambda x: int(x) if x.isdigit() else float('inf')):
            col_name = f'Node_{node_id}'
            node_data = acce_df[acce_df['Node'] == node_id].iloc[0] if not acce_df[acce_df['Node'] == node_id].empty else None

            acce_values = []
            for meas_name in ACCE_MEASUREMENTS:
                std_name = None
                for old_name, new_name in acce_name_mapping.items():
                    if new_name == meas_name:
                        std_name = old_name
                        break
                if node_data is not None and std_name is not None and std_name in node_data:
                    acce_values.append(node_data[std_name])
                else:
                    acce_values.append(np.nan)
            acce_df_transposed[col_name] = acce_values

            node_data = disp_df[disp_df['Node'] == node_id].iloc[0] if not disp_df[disp_df['Node'] == node_id].empty else None

            disp_values = []
            for meas_name in DISP_MEASUREMENTS:
                std_name = None
                for old_name, new_name in disp_name_mapping.items():
                    if new_name == meas_name:
                        std_name = old_name
                        break
                if node_data is not None and std_name is not None and std_name in node_data:
                    disp_values.append(node_data[std_name])
                else:
                    disp_values.append(np.nan)
            disp_df_transposed[col_name] = disp_values

        # Save CSV files
        acce_df_transposed.to_csv(acce_output_path, index=False, na_rep='', float_format='%.10g')
        disp_df_transposed.to_csv(disp_output_path, index=False, na_rep='', float_format='%.10g')

        print(f"Acceleration results saved to: {acce_output_path}")
        print(f"Displacement results saved to: {disp_output_path}")
        print(f"Processed {len(node_ids)} unique nodes.")
        print(f"Number of $ACCE instances found: {acce_count}")
        print(f"Number of $DISP instances found: {disp_count}")
        print(f"Total frequencies identified: {total_frequencies}")
        
        return acce_output_path, disp_output_path

    except Exception as e:
        print(f"Error processing PCH file: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def main():
    parser = argparse.ArgumentParser(description='Convert Nastran PCH file to CSV files')
    parser.add_argument('--input', '-i', required=True, help='Input PCH file path')
    parser.add_argument('--output_dir', '-o', default=None, help='Output directory (default: same as input)')
    parser.add_argument('--acce_file', default='acceleration_results.csv', help='Acceleration output filename')
    parser.add_argument('--disp_file', default='displacement_results.csv', help='Displacement output filename')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"ERROR: Input file not found: {args.input}")
        exit(1)
    
    acce_path, disp_path = process_pch_to_csv(
        input_file=args.input,
        output_dir=args.output_dir,
        acce_filename=args.acce_file,
        disp_filename=args.disp_file
    )
    
    if acce_path is None:
        print("ERROR: Failed to process PCH file")
        exit(1)
    
    print("Processing completed successfully!")


if __name__ == "__main__":
    main()