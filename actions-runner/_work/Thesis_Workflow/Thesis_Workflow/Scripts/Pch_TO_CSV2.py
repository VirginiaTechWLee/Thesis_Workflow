import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt

# Global variables
data_dict = {}
acce_count = 0
disp_count = 0
total_frequencies = 0
total_psd_columns = 0
node_ids = set()  # Track unique node IDs

# Custom measurement names (directly defined as specified)
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
    current_node = None
    current_dof = None

    while True:
        line = next(iterator, None)
        if line is None:
            break

        if line.startswith('$ACCE'):
            acce_count += 1
            parts = line.split()
            if len(parts) >= 5:
                node_id = parts[2]
                node_ids.add(node_id)  # Add to set of unique nodes
                translation_id = int(parts[3])
                translation_id_name = determine_translation_id(translation_id)
                current_header = f'ACCE-{node_id}-{translation_id_name}'
                current_node = node_id
                current_dof = translation_id_name

                if current_header not in data_dict:
                    data_dict[current_header] = []
                    total_psd_columns += 1

        elif line.startswith('$DISP'):
            disp_count += 1
            parts = line.split()
            if len(parts) >= 5:
                node_id = parts[2]
                node_ids.add(node_id)  # Add to set of unique nodes
                translation_id = int(parts[3])
                translation_id_name = determine_translation_id(translation_id)
                current_header = f'DISP-{node_id}-{translation_id_name}'
                current_node = node_id
                current_dof = translation_id_name

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
                    pass  # Skip lines with invalid data

        elif not line.strip():
            current_header = None
            current_node = None
            current_dof = None


def extract_frequency(lines):
    """Extract frequency data from the input file"""
    global total_frequencies

    if 'Frequency' not in data_dict:
        data_dict['Frequency'] = []

    within_data_block = False
    current_block = None

    for line in lines:
        if line.startswith('$ACCE') or line.startswith('$DISP'):
            within_data_block = True
            current_block = line[:5]
        elif within_data_block:
            if line.strip() == '':
                within_data_block = False
                current_block = None
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
    """Find the top three local maxima in each PSD column with improved robustness."""
    inflection_points = []

    for header in df.columns[1:]:  # Skip 'Frequency'
        psd_values = df[header].values
        frequencies = df['Frequency'].values

        # Add light smoothing to reduce noise
        window_size = min(5, len(psd_values) // 10 + 1)
        if window_size > 1 and len(psd_values) > window_size:
            smooth_psd = np.convolve(psd_values, np.ones(window_size) / window_size, mode='same')
        else:
            smooth_psd = psd_values

        # Identify local maxima
        # A point is a local maximum if it's greater than both its neighbors
        is_local_maxima = np.zeros_like(psd_values, dtype=bool)
        for i in range(1, len(smooth_psd) - 1):
            if smooth_psd[i] > smooth_psd[i - 1] and smooth_psd[i] > smooth_psd[i + 1]:
                is_local_maxima[i] = True

        # If no local maxima are found (flat data), use global maxima
        if not np.any(is_local_maxima):
            # Find indices of top 3 values
            top_indices = np.argsort(psd_values)[-3:]
            is_local_maxima[top_indices] = True

        # Get all local maxima as (frequency, psd) pairs
        local_maximas = [(frequencies[i], psd_values[i]) for i in np.where(is_local_maxima)[0]]

        # If fewer than 3 local maxima, add the highest non-maxima points
        if len(local_maximas) < 3:
            # Get indices of all non-maxima points
            non_maxima_indices = np.where(~is_local_maxima)[0]
            # Sort by PSD value
            sorted_indices = non_maxima_indices[np.argsort(psd_values[non_maxima_indices])]
            # Add highest non-maxima points until we have 3 or run out of points
            for idx in sorted_indices[::-1]:
                if len(local_maximas) >= 3:
                    break
                local_maximas.append((frequencies[idx], psd_values[idx]))

        # Sort by PSD value (highest first) and take top three
        local_maximas_sorted = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]

        # Sort the final selected peaks by frequency for consistency
        local_maximas_sorted = sorted(local_maximas_sorted, key=lambda x: x[0])

        # Create dictionary for the output
        inflection_point_dict = {'Channel': header}

        # Add the peaks to the dictionary
        for rank, (freq, psd) in enumerate(local_maximas_sorted, start=1):
            inflection_point_dict[f'Frequency_{rank}'] = freq
            inflection_point_dict[f'PSD_{rank}'] = psd

        # Ensure all 3 peaks are represented, even if we found fewer
        for missing_rank in range(len(local_maximas_sorted) + 1, 4):
            inflection_point_dict[f'Frequency_{missing_rank}'] = np.nan
            inflection_point_dict[f'PSD_{missing_rank}'] = np.nan

        inflection_points.append(inflection_point_dict)

    return inflection_points


def plot_all_acce_disp_vs_frequency(original_df, node_ids, dof='T1', image_format='png'):
    """
    Plot all accelerations in one figure and all displacements in another figure for a specific DOF.
    Save the plots as image files.

    Args:
        original_df: DataFrame containing the original PSD data
        node_ids: List of node IDs to plot
        dof: Degree of freedom to plot (T1, T2, T3, R1, R2, R3)
        image_format: Format for saving images ('png' or 'jpg')
    """
    frequencies = original_df['Frequency'].values

    # Sort node IDs numerically
    sorted_node_ids = sorted(node_ids, key=lambda x: int(x) if x.isdigit() else float('inf'))

    # Create figure for accelerations
    plt.figure(figsize=(14, 8))
    plt.title(f'Acceleration PSD vs Frequency - DOF: {dof}')

    # Generate a colormap for different nodes
    cmap = plt.cm.get_cmap('tab10', len(sorted_node_ids))

    # Plot acceleration PSD for each node
    for i, node_id in enumerate(sorted_node_ids):
        acce_key = f'ACCE-{node_id}-{dof}'
        if acce_key in original_df.columns:
            acce_values = original_df[acce_key].values
            plt.plot(frequencies, acce_values, label=f'Node {node_id}',
                     color=cmap(i), linewidth=2)

            # Find the top three peaks
            is_local_maxima = np.r_[True, acce_values[1:] > acce_values[:-1]] & np.r_[
                acce_values[:-1] > acce_values[1:], True]
            local_maximas = [(frequencies[j], acce_values[j]) for j in np.where(is_local_maxima)[0]]
            sorted_maximas = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]

            # Mark the peaks
            for peak_idx, (freq, psd) in enumerate(sorted_maximas, 1):
                plt.plot(freq, psd, 'o', color=cmap(i), markersize=6)
                plt.text(freq, psd, f'Node {node_id}: {freq:.2f} Hz',
                         verticalalignment='bottom', color=cmap(i), fontsize=8)

    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Acceleration PSD')
    plt.grid(True)
    plt.legend(loc='upper right')
    plt.tight_layout()

    # Save acceleration plot to file
    ext = f".{image_format}"
    acce_filename = f'all_acceleration_dof_{dof}{ext}'

    # Set quality for JPEG
    kwargs = {}
    if image_format.lower() in ['jpg', 'jpeg']:
        kwargs['quality'] = 90
        kwargs['format'] = 'jpg'

    plt.savefig(acce_filename, dpi=300, bbox_inches='tight', **kwargs)
    print(f"Saved acceleration plot to {acce_filename}")
    plt.close()

    # Create figure for displacements
    plt.figure(figsize=(14, 8))
    plt.title(f'Displacement PSD vs Frequency - DOF: {dof}')

    # Plot displacement PSD for each node
    for i, node_id in enumerate(sorted_node_ids):
        disp_key = f'DISP-{node_id}-{dof}'
        if disp_key in original_df.columns:
            disp_values = original_df[disp_key].values
            plt.plot(frequencies, disp_values, label=f'Node {node_id}',
                     color=cmap(i), linewidth=2)

            # Find the top three peaks
            is_local_maxima = np.r_[True, disp_values[1:] > disp_values[:-1]] & np.r_[
                disp_values[:-1] > disp_values[1:], True]
            local_maximas = [(frequencies[j], disp_values[j]) for j in np.where(is_local_maxima)[0]]
            sorted_maximas = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]

            # Mark the peaks
            for peak_idx, (freq, psd) in enumerate(sorted_maximas, 1):
                plt.plot(freq, psd, 'o', color=cmap(i), markersize=6)
                plt.text(freq, psd, f'Node {node_id}: {freq:.2f} Hz',
                         verticalalignment='bottom', color=cmap(i), fontsize=8)

    plt.xlabel('Frequency (Hz)')
    plt.ylabel('Displacement PSD')
    plt.grid(True)
    plt.legend(loc='upper right')
    plt.tight_layout()

    # Save displacement plot to file
    disp_filename = f'all_displacement_dof_{dof}{ext}'
    plt.savefig(disp_filename, dpi=300, bbox_inches='tight', **kwargs)
    print(f"Saved displacement plot to {disp_filename}")
    plt.close()


def plot_acce_disp_vs_frequency(original_df, node_id, dof='T1', image_format='png'):
    """
    Plot acceleration and displacement PSD vs frequency for a specific node and DOF.
    Save the plot as an image file.

    Args:
        original_df: DataFrame containing the original PSD data
        node_id: Node ID to plot
        dof: Degree of freedom to plot (T1, T2, T3, R1, R2, R3)
        image_format: Format for saving images ('png' or 'jpg')
    """
    acce_key = f'ACCE-{node_id}-{dof}'
    disp_key = f'DISP-{node_id}-{dof}'
    frequencies = original_df['Frequency'].values

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

    # Plot acceleration PSD vs frequency
    if acce_key in original_df.columns:
        acce_values = original_df[acce_key].values
        ax1.plot(frequencies, acce_values, 'b-', linewidth=2)
        ax1.set_ylabel('Acceleration PSD')
        ax1.set_title(f'Node {node_id} - {dof} - Acceleration PSD vs Frequency')
        ax1.grid(True)

        # Find and mark the peak frequencies for acceleration
        is_local_maxima = np.r_[True, acce_values[1:] > acce_values[:-1]] & np.r_[
            acce_values[:-1] > acce_values[1:], True]
        local_maximas = [(frequencies[i], acce_values[i]) for i in np.where(is_local_maxima)[0]]
        sorted_maximas = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]
        for i, (freq, psd) in enumerate(sorted_maximas, 1):
            ax1.plot(freq, psd, 'ro', markersize=8)
            ax1.text(freq, psd, f'Peak {i}: {freq:.2f} Hz', verticalalignment='bottom')
    else:
        ax1.text(0.5, 0.5, f'No acceleration data for Node {node_id} - {dof}',
                 horizontalalignment='center', verticalalignment='center', transform=ax1.transAxes)

    # Plot displacement PSD vs frequency
    if disp_key in original_df.columns:
        disp_values = original_df[disp_key].values
        ax2.plot(frequencies, disp_values, 'g-', linewidth=2)
        ax2.set_xlabel('Frequency (Hz)')
        ax2.set_ylabel('Displacement PSD')
        ax2.set_title(f'Node {node_id} - {dof} - Displacement PSD vs Frequency')
        ax2.grid(True)

        # Find and mark the peak frequencies for displacement
        is_local_maxima = np.r_[True, disp_values[1:] > disp_values[:-1]] & np.r_[
            disp_values[:-1] > disp_values[1:], True]
        local_maximas = [(frequencies[i], disp_values[i]) for i in np.where(is_local_maxima)[0]]
        sorted_maximas = sorted(local_maximas, key=lambda x: x[1], reverse=True)[:3]
        for i, (freq, psd) in enumerate(sorted_maximas, 1):
            ax2.plot(freq, psd, 'ro', markersize=8)
            ax2.text(freq, psd, f'Peak {i}: {freq:.2f} Hz', verticalalignment='bottom')
    else:
        ax2.text(0.5, 0.5, f'No displacement data for Node {node_id} - {dof}',
                 horizontalalignment='center', verticalalignment='center', transform=ax2.transAxes)

    plt.tight_layout()

    # Save the plot to file
    ext = f".{image_format}"
    comparison_filename = f'node_{node_id}_dof_{dof}_comparison{ext}'

    # Set quality for JPEG
    kwargs = {}
    if image_format.lower() in ['jpg', 'jpeg']:
        kwargs['quality'] = 90
        kwargs['format'] = 'jpg'

    plt.savefig(comparison_filename, dpi=300, bbox_inches='tight', **kwargs)
    print(f"Saved comparison plot to {comparison_filename}")
    plt.close()

    return fig


def create_combined_data(input_filename='randombeamx.pch', acce_output_filename='acceleration_results.csv',
                         disp_output_filename='displacement_results.csv', plot_node=None, plot_dof='T1',
                         plot_all=False, image_format='png'):
    """Function to create combined accelerations and displacements data"""
    global data_dict, acce_count, disp_count, total_frequencies, total_psd_columns, node_ids

    # Reset global variables
    data_dict = {}
    acce_count = 0
    disp_count = 0
    total_frequencies = 0
    total_psd_columns = 0
    node_ids = set()

    try:
        with open(input_filename, 'r') as file:
            lines = file.readlines()
            process_data_blocks(lines)

        with open(input_filename, 'r') as file:
            lines = file.readlines()
            extract_frequency(lines)

        # Sort frequencies to ensure consistent data organization
        if 'Frequency' in data_dict:
            data_dict['Frequency'] = sorted(data_dict['Frequency'])

        # Create DataFrame from the data dictionary
        original_df = pd.DataFrame(data_dict)

        # If DataFrame is empty, warn and exit
        if original_df.empty:
            print(f"WARNING: No data was extracted from {input_filename}")
            return False

        # Plot acceleration and displacement PSD vs frequency if requested for a specific node
        if plot_node is not None and str(plot_node) in node_ids:
            plot_acce_disp_vs_frequency(original_df, str(plot_node), plot_dof, image_format)

        # Plot all accelerations and all displacements if requested
        if plot_all:
            plot_all_acce_disp_vs_frequency(original_df, node_ids, plot_dof, image_format)

        # Create DataFrames to store reorganized data
        acce_data = []
        disp_data = []

        # Define the DOF types
        dof_types = ['T1', 'T2', 'T3', 'R1', 'R2', 'R3']

        # Process data for each node ID
        for node_id in sorted(node_ids, key=lambda x: int(x) if x.isdigit() else float('inf')):
            # Create dictionaries to store acceleration and displacement data for this node
            acce_node_data = {}
            disp_node_data = {}

            # Process each DOF type
            for dof in dof_types:
                acce_key = f'ACCE-{node_id}-{dof}'
                disp_key = f'DISP-{node_id}-{dof}'

                # Process acceleration data
                if acce_key in original_df.columns:
                    # Calculate area using trapezoidal rule
                    acce_values = original_df[acce_key].values
                    frequencies = original_df['Frequency'].values
                    area = np.trapz(acce_values, x=frequencies)

                    # Find peak frequencies using improved function
                    temp_df = pd.DataFrame({'Frequency': original_df['Frequency'], acce_key: original_df[acce_key]})
                    maxima_data = find_top_three_local_maxima(temp_df)[0]

                    # Add data to node data dictionary
                    acce_node_data[f'{dof}_Area'] = area
                    for i in range(1, 4):
                        freq_key = f'Frequency_{i}'
                        psd_key = f'PSD_{i}'
                        acce_node_data[f'{dof}_Frequency_{i}'] = maxima_data.get(freq_key, np.nan)
                        acce_node_data[f'{dof}_PSD_{i}'] = maxima_data.get(psd_key, np.nan)
                else:
                    # Set appropriate default values based on DOF type
                    if dof in ['R1', 'R2', 'R3']:
                        # Use zero for rotational DOFs that aren't present
                        acce_node_data[f'{dof}_Area'] = 0
                        for i in range(1, 4):
                            acce_node_data[f'{dof}_Frequency_{i}'] = 0
                            acce_node_data[f'{dof}_PSD_{i}'] = 0
                    else:
                        # Use NaN for non-rotational DOFs
                        acce_node_data[f'{dof}_Area'] = np.nan
                        for i in range(1, 4):
                            acce_node_data[f'{dof}_Frequency_{i}'] = np.nan
                            acce_node_data[f'{dof}_PSD_{i}'] = np.nan

                # Process displacement data
                if disp_key in original_df.columns:
                    # Calculate area using trapezoidal rule
                    disp_values = original_df[disp_key].values
                    frequencies = original_df['Frequency'].values
                    area = np.trapz(disp_values, x=frequencies)

                    # Find peak frequencies using improved function
                    temp_df = pd.DataFrame({'Frequency': original_df['Frequency'], disp_key: original_df[disp_key]})
                    maxima_data = find_top_three_local_maxima(temp_df)[0]

                    # Add data to node data dictionary
                    disp_node_data[f'{dof}_Area'] = area
                    for i in range(1, 4):
                        freq_key = f'Frequency_{i}'
                        psd_key = f'PSD_{i}'
                        disp_node_data[f'{dof}_Frequency_{i}'] = maxima_data.get(freq_key, np.nan)
                        disp_node_data[f'{dof}_PSD_{i}'] = maxima_data.get(psd_key, np.nan)
                else:
                    # Use NaN for missing data
                    disp_node_data[f'{dof}_Area'] = np.nan
                    for i in range(1, 4):
                        disp_node_data[f'{dof}_Frequency_{i}'] = np.nan
                        disp_node_data[f'{dof}_PSD_{i}'] = np.nan

            # Add node data to the respective lists
            acce_data.append({'Node': node_id, 'Measurement': 'Acceleration', **acce_node_data})
            disp_data.append({'Node': node_id, 'Measurement': 'Displacement', **disp_node_data})

        # Create DataFrames from collected data
        acce_df = pd.DataFrame(acce_data)
        disp_df = pd.DataFrame(disp_data)

        # Use the predefined custom measurement names
        acce_measurements = ACCE_MEASUREMENTS
        disp_measurements = DISP_MEASUREMENTS

        # Create transposed DataFrames with Measurement column
        acce_df_transposed = pd.DataFrame(columns=['Measurement'])
        disp_df_transposed = pd.DataFrame(columns=['Measurement'])

        # Set the measurement column with custom names
        acce_df_transposed['Measurement'] = acce_measurements
        disp_df_transposed['Measurement'] = disp_measurements

        # Define mapping between old measurement names and the custom ones
        # For acceleration, maintain the pattern but add ACCE_ prefix
        acce_name_mapping = {}
        for dof in dof_types:
            acce_name_mapping[f'{dof}_Area'] = f'ACCE_{dof}_Area'
            for i in range(1, 4):
                acce_name_mapping[f'{dof}_Frequency_{i}'] = f'ACCE_{dof}_Frequency_{i}'
                acce_name_mapping[f'{dof}_PSD_{i}'] = f'ACCE_{dof}_PSD_{i}'

        # For displacement, change PSD to DISP in column names
        disp_name_mapping = {}
        for dof in dof_types:
            disp_name_mapping[f'{dof}_Area'] = f'DISP_{dof}_Area'
            for i in range(1, 4):
                disp_name_mapping[f'{dof}_Frequency_{i}'] = f'DISP_{dof}_Frequency_{i}'
                disp_name_mapping[f'{dof}_PSD_{i}'] = f'DISP_{dof}_DISP_{i}'  # Change PSD to DISP

        # Add data for each node as a column
        for node_id in sorted(node_ids, key=lambda x: int(x) if x.isdigit() else float('inf')):
            # For accelerations
            col_name = f'Node_{node_id}'
            node_data = acce_df[acce_df['Node'] == node_id].iloc[0] if not acce_df[
                acce_df['Node'] == node_id].empty else None

            # Add data using standard measurement keys, but match output order to custom names
            acce_values = []
            for meas_name in acce_measurements:
                # Find the corresponding standard name
                std_name = None
                for old_name, new_name in acce_name_mapping.items():
                    if new_name == meas_name:
                        std_name = old_name
                        break

                # Get value from node data if available
                if node_data is not None and std_name is not None and std_name in node_data:
                    acce_values.append(node_data[std_name])
                else:
                    acce_values.append(np.nan)

            acce_df_transposed[col_name] = acce_values

            # For displacements
            node_data = disp_df[disp_df['Node'] == node_id].iloc[0] if not disp_df[
                disp_df['Node'] == node_id].empty else None

            # Add data using standard measurement keys, but match output order to custom names
            disp_values = []
            for meas_name in disp_measurements:
                # Find the corresponding standard name
                std_name = None
                for old_name, new_name in disp_name_mapping.items():
                    if new_name == meas_name:
                        std_name = old_name
                        break

                # Get value from node data if available
                if node_data is not None and std_name is not None and std_name in node_data:
                    disp_values.append(node_data[std_name])
                else:
                    disp_values.append(np.nan)

            disp_df_transposed[col_name] = disp_values

        # Save the CSV files using pandas to_csv with appropriate formatting
        acce_df_transposed.to_csv(acce_output_filename, index=False, na_rep='', float_format='%.10g')
        disp_df_transposed.to_csv(disp_output_filename, index=False, na_rep='', float_format='%.10g')

        print(f"Acceleration results have been exported to {acce_output_filename}.")
        print(f"Displacement results have been exported to {disp_output_filename}.")
        print(f"Used custom header names for both files.")
        print(f"Processed {len(node_ids)} unique nodes.")
        return True

    except Exception as e:
        print(f"An error occurred in create_combined_data: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        print(f"Number of $ACCE instances found: {acce_count}.")
        print(f"Number of $DISP instances found: {disp_count}.")
        print(f"Total frequencies identified: {total_frequencies}.")
        print(f"Total PSD columns recorded: {total_psd_columns}.")


def create_delta_files(current_acce_file='acceleration_results.csv',
                       current_disp_file='displacement_results.csv',
                       baseline_acce_file='acceleration_results_baseline.csv',
                       baseline_disp_file='displacement_results_baseline.csv',
                       delta_acce_file='acceleration_results_delta.csv',
                       delta_disp_file='displacement_results_delta.csv',
                       output_current_acce_file='acceleration_results_processed.csv',
                       output_current_disp_file='displacement_results_processed.csv'):
    """
    Create delta files by calculating: baseline_values - current_results
    This shows how much baseline values differ from the current results.
    Also outputs copies of the current results for convenience.

    Args:
        current_acce_file: Path to current acceleration results CSV
        current_disp_file: Path to current displacement results CSV
        baseline_acce_file: Path to baseline acceleration results CSV
        baseline_disp_file: Path to baseline displacement results CSV
        delta_acce_file: Output path for acceleration delta CSV
        delta_disp_file: Output path for displacement delta CSV
        output_current_acce_file: Output path for processed current acceleration CSV
        output_current_disp_file: Output path for processed current displacement CSV
    """
    try:
        # Read the current and baseline files
        print(f"Reading current and baseline files...")
        current_acce_df = pd.read_csv(current_acce_file)
        current_disp_df = pd.read_csv(current_disp_file)
        baseline_acce_df = pd.read_csv(baseline_acce_file)
        baseline_disp_df = pd.read_csv(baseline_disp_file)

        # Verify that the measurement columns match
        if not current_acce_df['Measurement'].equals(baseline_acce_df['Measurement']):
            print("WARNING: Measurement columns in acceleration files don't match. Results may be incorrect.")

        if not current_disp_df['Measurement'].equals(baseline_disp_df['Measurement']):
            print("WARNING: Measurement columns in displacement files don't match. Results may be incorrect.")

        # Create copies for the delta dataframes
        delta_acce_df = current_acce_df.copy()
        delta_disp_df = current_disp_df.copy()

        # Get the node columns (all columns except 'Measurement')
        acce_node_cols = [col for col in current_acce_df.columns if col != 'Measurement']
        disp_node_cols = [col for col in current_disp_df.columns if col != 'Measurement']

        # Calculate deltas for acceleration data
        for col in acce_node_cols:
            if col in baseline_acce_df.columns:
                # Calculate delta as: baseline - current
                delta_acce_df[col] = baseline_acce_df[col].subtract(current_acce_df[col], fill_value=0)

                # Set values smaller than 1e-6 (in absolute value) to zero
                delta_acce_df[col] = delta_acce_df[col].apply(
                    lambda x: 0 if abs(x) < 1e-6 else x
                )

                print(f"Calculated acceleration delta for {col} (baseline - current)")
            else:
                print(f"WARNING: Column {col} not found in baseline acceleration file. Using baseline values or zeros.")

        # Calculate deltas for displacement data
        for col in disp_node_cols:
            if col in baseline_disp_df.columns:
                # Calculate delta as: baseline - current
                delta_disp_df[col] = baseline_disp_df[col].subtract(current_disp_df[col], fill_value=0)

                # Set values smaller than 1e-6 (in absolute value) to zero
                delta_disp_df[col] = delta_disp_df[col].apply(
                    lambda x: 0 if abs(x) < 1e-6 else x
                )

                print(f"Calculated displacement delta for {col} (baseline - current)")
            else:
                print(f"WARNING: Column {col} not found in baseline displacement file. Using baseline values or zeros.")

        # Save the delta files
        delta_acce_df.to_csv(delta_acce_file, index=False, float_format='%.10g')
        delta_disp_df.to_csv(delta_disp_file, index=False, float_format='%.10g')

        # Save copies of the current files (with consistent formatting)
        current_acce_df.to_csv(output_current_acce_file, index=False, float_format='%.10g')
        current_disp_df.to_csv(output_current_disp_file, index=False, float_format='%.10g')

        print(f"Successfully created delta files:")
        print(f" - Acceleration delta: {delta_acce_file}")
        print(f" - Displacement delta: {delta_disp_file}")
        print(f" - Values less than 1e-6 have been set to zero")
        print(f" - Delta calculated as: baseline - current")

        print(f"\nAlso created copies of current results:")
        print(f" - Acceleration current: {output_current_acce_file}")
        print(f" - Displacement current: {output_current_disp_file}")

        # Print some statistics
        for col in acce_node_cols:
            if col in baseline_acce_df.columns:
                non_zero_deltas = (delta_acce_df[col] != 0).sum()
                if non_zero_deltas > 0:
                    print(f"Column {col} has {non_zero_deltas} non-zero deltas in acceleration data.")

        for col in disp_node_cols:
            if col in baseline_disp_df.columns:
                non_zero_deltas = (delta_disp_df[col] != 0).sum()
                if non_zero_deltas > 0:
                    print(f"Column {col} has {non_zero_deltas} non-zero deltas in displacement data.")

        return True

    except Exception as e:
        print(f"Error creating delta files: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """
    Main function to run the complete process:
    1. Process PCH file to extract acceleration and displacement data
    2. Generate plots and CSV results
    3. Compare with baseline to create delta files
    """
    # Input and output files
    input_filename = 'randombeamx.pch'
    acce_output_filename = 'acceleration_results.csv'
    disp_output_filename = 'displacement_results.csv'
    baseline_acce_file = 'acceleration_results_baseline.csv'
    baseline_disp_file = 'displacement_results_baseline.csv'
    delta_acce_file = 'acceleration_results_delta.csv'
    delta_disp_file = 'displacement_results_delta.csv'
    processed_acce_file = 'acceleration_results_processed.csv'
    processed_disp_file = 'displacement_results_processed.csv'

    # Image format for plots (png or jpg)
    image_format = 'png'  # Change to 'jpg' for smaller file sizes

    # Step 1: Process PCH file and create result files
    print("\n=== STEP 1: Processing PCH file and generating results ===")
    pch_success = create_combined_data(
        input_filename,
        acce_output_filename,
        disp_output_filename,
        plot_node=222,  # Plot individual node (set to None to skip)
        plot_dof='T1',  # Degree of freedom to plot
        plot_all=True,  # Plot all nodes together
        image_format=image_format
    )

    if not pch_success:
        print("Failed to process PCH file. Exiting.")
        return

    # Step 2: Create delta files (if baseline files exist)
    print("\n=== STEP 2: Creating delta files by comparing with baseline ===")

    # Check if baseline files exist
    baseline_files_exist = os.path.exists(baseline_acce_file) and os.path.exists(baseline_disp_file)

    if baseline_files_exist:
        delta_success = create_delta_files(
            acce_output_filename,
            disp_output_filename,
            baseline_acce_file,
            baseline_disp_file,
            delta_acce_file,
            delta_disp_file,
            processed_acce_file,
            processed_disp_file
        )

        if delta_success:
            print("\nAll processing completed successfully.")
        else:
            print("\nFailed to create delta files.")
    else:
        print(f"Baseline files not found ({baseline_acce_file} and/or {baseline_disp_file}).")
        print("Skipping delta file creation. To create delta files, ensure baseline files exist.")
        print("\nProcessing of PCH file completed successfully.")


if __name__ == "__main__":
    main()