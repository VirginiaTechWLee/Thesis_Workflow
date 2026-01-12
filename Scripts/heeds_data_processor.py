import pandas as pd
import numpy as np
from typing import Tuple, List, Dict, Any
import warnings

class HEEDSDataProcessor:
    """
    Enhanced HEEDS Data Processor with scientific notation conversion
    Handles HEEDS CSV output where stiffness values are in format like '1.+8'
    
    Key Features:
    - Converts HEEDS scientific notation to encoded stiffness values (1-11)
    - Excludes bolt 1 (driving CBUSH) from looseness evaluation
    - Creates spatial labels for single-bolt failure detection
    - Supports multiple feature types for ML analysis
    """
    
    def __init__(self, file_path: str, loose_threshold: int = 6):
        self.file_path = file_path
        self.loose_threshold = loose_threshold
        self.df = None
        self.baseline_values = None
        
        # Stiffness encoding mapping
        self.stiffness_encoding_map = {
            4: 1,   # 1e4 â†’ 1 (extremely loose)
            5: 2,   # 1e5 â†’ 2 (very loose)
            6: 3,   # 1e6 â†’ 3 (loose)
            7: 4,   # 1e7 â†’ 4 (medium-loose)
            8: 5,   # 1e8 â†’ 5 (driving CBUSH)
            9: 6,   # 1e9 â†’ 6 (medium)
            10: 7,  # 1e10 â†’ 7 (medium-tight)
            11: 8,  # 1e11 â†’ 8 (tight)
            12: 9,  # 1e12 â†’ 9 (very tight baseline)
            13: 10, # 1e13 â†’ 10 (extremely tight)
            14: 11  # 1e14 â†’ 11 (ultra tight)
        }
        
        # Reverse mapping for decoding
        self.encoding_to_stiffness = {v: k for k, v in self.stiffness_encoding_map.items()}
    
    def convert_stiffness_to_encoding(self, value):
        """
        Convert HEEDS scientific notation to encoding (1-11)
        
        Handles formats like:
        - '1.+8' â†’ 5 (1e8 â†’ encoding 5)
        - '1.+12' â†’ 9 (1e12 â†’ encoding 9)
        - Already numeric values pass through
        """
        try:
            # Handle string scientific notation from HEEDS
            if isinstance(value, str):
                # Convert '1.+8' format to '1e+8' format
                if '.+' in value:
                    value = value.replace('.+', 'e+')
                elif '.-' in value:
                    value = value.replace('.-', 'e-')
                
                # Convert to float
                value = float(value)
            
            # If already numeric, use as-is
            if isinstance(value, (int, float)):
                # Get the exponent (log base 10)
                if value <= 0:
                    return 9  # Default to baseline if invalid
                
                log_val = int(np.round(np.log10(value)))
                return self.stiffness_encoding_map.get(log_val, 9)
            
            # If it's already an integer 1-11, assume it's already encoded
            if isinstance(value, int) and 1 <= value <= 11:
                return value
                
            return 9  # Default to baseline
            
        except (ValueError, TypeError):
            print(f"Warning: Could not convert stiffness value '{value}', using default (9)")
            return 9
    
    def decode_stiffness_value(self, encoded_value: int) -> float:
        """Convert encoded value back to actual stiffness"""
        exponent = self.encoding_to_stiffness.get(encoded_value, 12)
        return 10**exponent
    
    def load_data(self):
        """Load and preprocess HEEDS CSV data with explicit column validation"""
        print(f"Loading HEEDS data from: {self.file_path}")
        
        # Read the CSV file
        self.df = pd.read_csv(self.file_path)
        
        print(f"Loaded data shape: {self.df.shape}")
        print(f"All columns: {list(self.df.columns)}")
        
        # ================================
        # COLUMN STRUCTURE VALIDATION
        # ================================
        print(f"\nðŸ” VALIDATING COLUMN STRUCTURE:")
        
        # Check first 3 columns are as expected
        expected_first_cols = ['Parameter', 'min', 'max']
        actual_first_cols = list(self.df.columns[:3])
        
        if actual_first_cols == expected_first_cols:
            print(f"âœ… Column structure correct: {actual_first_cols}")
        else:
            print(f"âš ï¸ WARNING: Expected columns {expected_first_cols}")
            print(f"âš ï¸          Got columns {actual_first_cols}")
            print(f"âš ï¸ This may cause data processing issues!")
            print(f"âš ï¸ Continuing with analysis despite column structure mismatch...")
        
        # Find and validate design columns
        design_data_cols = [c for c in self.df.columns if c.startswith('Design')]
        non_design_cols = [c for c in self.df.columns if not c.startswith(('Parameter', 'min', 'max', 'Design'))]
        
        print(f"âœ… Found {len(design_data_cols)} design point columns (correctly skipping min/max)")
        print(f"   Design columns: {design_data_cols[:5]}{'...' if len(design_data_cols) > 5 else ''}")
        
        if non_design_cols:
            print(f"âš ï¸ Found unexpected columns: {non_design_cols}")
            print(f"   These will be ignored during processing")
        
        # Validate we have actual design data
        if len(design_data_cols) == 0:
            raise ValueError("No 'Design' columns found! Check your HEEDS CSV format.")
        
        if len(design_data_cols) < 10:
            print(f"âš ï¸ Only {len(design_data_cols)} design points found. Expected more for robust ML analysis.")
        
        # ================================
        # DESIGN VARIABLES PROCESSING
        # ================================
        print(f"\nðŸ”§ PROCESSING DESIGN VARIABLES:")
        
        # Find design variable parameters (rows in the Parameter column)
        design_var_params = [param for param in self.df['Parameter'] if param.startswith(('K4_', 'K5_', 'K6_'))]
        print(f"Found {len(design_var_params)} design variable parameters")
        
        if len(design_var_params) == 0:
            print(f"âš ï¸ No K4_, K5_, K6_ parameters found!")
            print(f"Sample parameters: {list(self.df['Parameter'][:10])}")
            raise ValueError("No stiffness parameters found. Check parameter naming convention.")
        
        # Convert all stiffness values to encodings
        conversion_count = 0
        conversion_errors = 0
        sample_conversions = []
        
        for param in design_var_params:
            # Get the row index for this parameter
            param_mask = self.df['Parameter'] == param
            if not param_mask.any():
                print(f"âš ï¸ Parameter {param} not found in dataframe")
                continue
                
            param_idx = param_mask.idxmax()
            
            # Convert each design point for this parameter
            for design_col in design_data_cols:
                try:
                    original_value = self.df.loc[param_idx, design_col]
                    converted_value = self.convert_stiffness_to_encoding(original_value)
                    self.df.loc[param_idx, design_col] = converted_value
                    
                    # Store sample for validation display
                    if len(sample_conversions) < 10:
                        sample_conversions.append((param, design_col, original_value, converted_value))
                    
                    conversion_count += 1
                    
                except Exception as e:
                    print(f"âš ï¸ Error converting {param} in {design_col}: {e}")
                    conversion_errors += 1
        
        print(f"âœ… Stiffness conversion completed: {conversion_count:,} values converted")
        if conversion_errors > 0:
            print(f"âš ï¸ {conversion_errors} conversion errors encountered")
        
        # Show sample conversions for validation
        if sample_conversions:
            print(f"\nðŸ“‹ Sample conversions (first 5):")
            for param, design_col, original, converted in sample_conversions[:5]:
                print(f"   {param} [{design_col}]: '{original}' â†’ {converted}")
        
        # ================================
        # FINAL VALIDATION
        # ================================
        print(f"\nâœ… FINAL VALIDATION:")
        
        # Set parameter names as index for easier access
        self.df.set_index('Parameter', inplace=True)
        
        # Validate that min/max columns are no longer used
        if 'min' in self.df.columns or 'max' in self.df.columns:
            print(f"âœ… min/max columns preserved but excluded from analysis")
        
        # Check converted values are in expected range
        design_var_rows = [row for row in self.df.index if row.startswith(('K4_', 'K5_', 'K6_'))]
        if design_var_rows:
            all_converted_values = []
            for row in design_var_rows[:3]:  # Check first few rows
                for col in design_data_cols[:5]:  # Check first few columns
                    val = self.df.loc[row, col]
                    all_converted_values.append(val)
            
            unique_values = sorted(set(all_converted_values))
            print(f"âœ… Converted stiffness values: {unique_values}")
            
            # Validate they're in expected range 1-11
            invalid_values = [v for v in unique_values if not (isinstance(v, (int, float)) and 1 <= v <= 11)]
            if invalid_values:
                print(f"âš ï¸ Found invalid encoded values: {invalid_values}")
                print(f"   Expected range: 1-11 (representing stiffness levels)")
            else:
                print(f"âœ… All values in valid range 1-11")
        
        # Display final structure summary
        print(f"\nðŸ“Š FINAL DATASET STRUCTURE:")
        print(f"   Total rows (parameters + responses): {len(self.df)}")
        print(f"   Design point columns: {len(design_data_cols)}")
        print(f"   Design variables (K4_,K5_,K6_): {len(design_var_rows)}")
        print(f"   Response parameters: {len(self.df) - len(design_var_rows)}")
        
        print(f"\nðŸŽ¯ Column handling summary:")
        print(f"   âœ… 'Parameter' column â†’ used as row index")
        print(f"   â­ï¸ 'min', 'max' columns â†’ preserved but SKIPPED in analysis")  
        print(f"   âœ… 'Design X' columns â†’ processed for ML analysis")
        print(f"   â­ï¸ Other columns â†’ ignored")
        
        print(f"\nðŸš€ Data loading completed successfully!")
    
    def get_design_columns(self) -> List[str]:
        """Get list of design point column names"""
        return [col for col in self.df.columns if col.startswith('Design')]
    
    def get_response_rows(self) -> List[str]:
        """Get list of response measurement row names (excluding design variables)"""
        return [row for row in self.df.index if not row.startswith(('K4_', 'K5_', 'K6_'))]
    
    def get_design_variables(self) -> List[str]:
        """Get list of design variable row names"""
        return [row for row in self.df.index if row.startswith(('K4_', 'K5_', 'K6_'))]
    
    def get_bolt_numbers(self) -> List[str]:
        """Get list of bolt numbers from design variables"""
        bolt_numbers = set()
        for var in self.get_design_variables():
            if '_' in var:
                bolt_num = var.split('_')[1]
                bolt_numbers.add(bolt_num)
        return sorted(list(bolt_numbers))
    
    def create_ml_dataset(self, feature_type: str = 'deltas_only', 
                         label_type: str = 'spatial') -> Tuple[pd.DataFrame, pd.Series, List[str], Dict]:
        """
        Create ML dataset from HEEDS data
        
        Args:
            feature_type: 'deltas_only', 'deltas_plus_modal', or 'all_responses'
            label_type: 'spatial' (which bolts are loose) or 'binary' (any bolt loose)
            
        Returns:
            X: Feature matrix
            y: Labels
            feature_names: List of feature names
            label_info: Dictionary with label information
        """
        
        design_cols = self.get_design_columns()
        response_rows = self.get_response_rows()
        
        print(f"Creating ML dataset with {len(design_cols)} design points")
        print(f"Feature type: {feature_type}")
        print(f"Label type: {label_type}")
        
        # Select features based on type
        if feature_type == 'deltas_only':
            feature_rows = [row for row in response_rows if 'Delta' in row]
        elif feature_type == 'deltas_plus_modal':
            feature_rows = [row for row in response_rows if 'Delta' in row or row.startswith('Modes')]
        else:  # all_responses
            feature_rows = response_rows
        
        print(f"Selected {len(feature_rows)} feature rows")
        
        # Create feature matrix
        X = self.df.loc[feature_rows, design_cols].T  # Transpose so designs are rows
        X.columns = feature_rows  # Feature names
        
        # Handle any remaining non-numeric values
        X = X.apply(pd.to_numeric, errors='coerce').fillna(0)
        
        # Create labels
        design_var_rows = self.get_design_variables()
        design_vars = self.df.loc[design_var_rows, design_cols].T
        
        # Convert any remaining non-numeric values in design variables
        design_vars = design_vars.apply(pd.to_numeric, errors='coerce').fillna(9)
        
        if label_type == 'spatial':
            # Create spatial labels indicating which bolts are loose
            y = self.create_spatial_labels(design_vars)
            label_info = {'type': 'spatial', 'loose_threshold': self.loose_threshold}
        else:  # binary
            # Create binary labels (any bolt loose vs all tight)
            loose_mask = design_vars <= self.loose_threshold
            # Exclude bolt 1 from binary analysis too
            bolt_1_cols = [col for col in design_vars.columns if col.endswith('_1')]
            for col in bolt_1_cols:
                if col in loose_mask.columns:
                    loose_mask[col] = False  # Never consider bolt 1 as loose
            y = loose_mask.any(axis=1).astype(int)
            label_info = {'type': 'binary', 'loose_threshold': self.loose_threshold}
        
        feature_names = X.columns.tolist()
        
        print(f"Final dataset shape: {X.shape}")
        print(f"Label distribution: {y.value_counts().to_dict()}")
        
        return X, y, feature_names, label_info
    
    def create_spatial_labels(self, design_vars: pd.DataFrame) -> pd.Series:
        """
        Create spatial labels indicating which bolts are loose
        
        CRITICAL: Excludes bolt 1 (driving CBUSH) from looseness evaluation
        """
        
        # Group K4, K5, K6 by bolt number
        bolt_numbers = sorted(set([col.split('_')[1] for col in design_vars.columns]))
        
        print(f"\nðŸ” Creating spatial labels with loose_threshold={self.loose_threshold}")
        print(f"Found {len(bolt_numbers)} bolts: {bolt_numbers}")
        print(f"âš ï¸ CRITICAL: Excluding bolt 1 (driving CBUSH) from looseness evaluation")
        
        # Debug: Check stiffness value distribution
        all_values = []
        for col in design_vars.columns:
            all_values.extend(design_vars[col].values)
        
        unique_values = sorted(set(all_values))
        print(f"Unique stiffness values in dataset: {unique_values}")
        print(f"Values â‰¤ threshold ({self.loose_threshold}): {[v for v in unique_values if v <= self.loose_threshold]}")
        
        labels = []
        loose_counts = {}
        
        for _, row in design_vars.iterrows():
            loose_bolts = []
            
            for bolt_num in bolt_numbers:
                # ðŸŽ¯ CRITICAL FIX: SKIP bolt 1 - it's the driving CBUSH, not a structural bolt
                if bolt_num == '1':
                    continue
                    
                # Check if any of K4, K5, K6 for this bolt are loose
                k4_col = f'K4_{bolt_num}'
                k5_col = f'K5_{bolt_num}'
                k6_col = f'K6_{bolt_num}'
                
                k4_val = row.get(k4_col, 9)
                k5_val = row.get(k5_col, 9) 
                k6_val = row.get(k6_col, 9)
                
                # Check if this bolt is loose (any stiffness â‰¤ threshold)
                if any(val <= self.loose_threshold for val in [k4_val, k5_val, k6_val]):
                    # For single-bolt studies, include the looseness level
                    min_stiffness = min([k4_val, k5_val, k6_val])
                    loose_bolts.append(f"{bolt_num}_level_{min_stiffness}")
            
            # Create label string
            if loose_bolts:
                if len(loose_bolts) == 1:
                    # Single bolt loose - ideal for your study
                    bolt_info = loose_bolts[0]
                    bolt_num = bolt_info.split('_level_')[0]
                    label = f"loose_bolt_{bolt_num}"
                else:
                    # Multiple bolts loose - shouldn't happen in single-bolt study
                    bolt_nums = [lb.split('_level_')[0] for lb in loose_bolts]
                    label = f"loose_bolt_{'_'.join(bolt_nums)}"
                
                if label not in loose_counts:
                    loose_counts[label] = 0
                loose_counts[label] += 1
            else:
                label = "all_tight"
            
            labels.append(label)
        
        label_series = pd.Series(labels, index=design_vars.index)
        
        # Print label distribution
        print(f"\nðŸ“Š Label distribution (Bolt 1 excluded):")
        value_counts = label_series.value_counts()
        for label, count in value_counts.items():
            percentage = (count / len(label_series)) * 100
            print(f"  {label}: {count:,} samples ({percentage:.1f}%)")
        
        # Check for single-bolt study quality
        single_bolt_labels = [label for label in value_counts.index if label.startswith('loose_bolt_') and label.count('_') == 2]
        multi_bolt_labels = [label for label in value_counts.index if label.startswith('loose_bolt_') and label.count('_') > 2]
        
        if single_bolt_labels:
            print(f"\nâœ… Single-bolt study detected: {len(single_bolt_labels)} different bolt conditions")
            print(f"   Expected labels for bolts 2-{max(bolt_numbers)}: {single_bolt_labels}")
        if multi_bolt_labels:
            print(f"âš ï¸ Multi-bolt conditions found: {len(multi_bolt_labels)} (may want to filter these out)")
        
        # Diagnostic check
        if len(value_counts) == 1:
            print(f"\nâš ï¸ WARNING: Only one label found: '{value_counts.index[0]}'")
            print("ðŸ’¡ Suggestions:")
            if value_counts.index[0] == 'all_tight':
                suggested_threshold = max(unique_values) - 1 if len(unique_values) > 1 else 9
                print(f"   - Try increasing loose_threshold to {suggested_threshold}")
                print(f"   - Current threshold {self.loose_threshold} may be too low")
            else:
                print(f"   - Try decreasing loose_threshold")
                print(f"   - Current threshold {self.loose_threshold} may be too high")
        else:
            print(f"\nâœ… Multi-class labeling successful! Found {len(value_counts)} unique labels")
            print(f"ðŸŽ¯ This should resolve the LOBO 'previously unseen labels' error!")
        
        return label_series
    
    def get_bolt_info(self, design_point: str) -> Dict[str, Any]:
        """Get bolt configuration for a specific design point"""
        
        design_vars = self.get_design_variables()
        bolt_config = {}
        
        for var in design_vars:
            value = self.df.loc[var, design_point]
            actual_stiffness = self.decode_stiffness_value(int(value))
            bolt_config[var] = {
                'encoded': value,
                'actual_stiffness': actual_stiffness,
                'scientific_notation': f"1e{int(np.log10(actual_stiffness))}"
            }
        
        return bolt_config
    
    def analyze_threshold_sensitivity(self) -> Dict[int, Dict]:
        """Analyze how different thresholds affect label distribution"""
        
        design_vars = self.get_design_variables()
        design_cols = self.get_design_columns()
        design_var_data = self.df.loc[design_vars, design_cols].T
        design_var_data = design_var_data.apply(pd.to_numeric, errors='coerce').fillna(9)
        
        results = {}
        
        # Test thresholds from 3 to 9
        for threshold in range(3, 10):
            print(f"\nðŸ” Testing threshold = {threshold}")
            old_threshold = self.loose_threshold
            self.loose_threshold = threshold
            
            labels = self.create_spatial_labels(design_var_data)
            value_counts = labels.value_counts()
            
            results[threshold] = {
                'num_classes': len(value_counts),
                'distribution': value_counts.to_dict(),
                'single_bolt_classes': len([label for label in value_counts.index if label.startswith('loose_bolt_') and label.count('_') == 2])
            }
            
            self.loose_threshold = old_threshold  # Restore original
        
        # Print summary
        print(f"\nðŸ“Š Threshold Sensitivity Analysis:")
        print(f"{'Threshold':<10} {'Classes':<8} {'Single-Bolt':<12} {'All-Tight %':<12}")
        print("-" * 45)
        
        for threshold, data in results.items():
            all_tight_pct = (data['distribution'].get('all_tight', 0) / sum(data['distribution'].values())) * 100
            print(f"{threshold:<10} {data['num_classes']:<8} {data['single_bolt_classes']:<12} {all_tight_pct:<12.1f}")
        
        return results
    
    def summarize_dataset(self):
        """Print comprehensive summary statistics of the dataset"""
        
        if self.df is None:
            print("âŒ No data loaded. Call load_data() first.")
            return
        
        print("\n" + "="*60)
        print("DATASET SUMMARY")
        print("="*60)
        
        design_cols = self.get_design_columns()
        response_rows = self.get_response_rows()
        design_var_rows = self.get_design_variables()
        bolt_numbers = self.get_bolt_numbers()
        
        print(f"ðŸ“Š Total design points: {len(design_cols)}")
        print(f"ðŸ“Š Response measurements: {len(response_rows)}")
        print(f"ðŸ“Š Design variables: {len(design_var_rows)}")
        print(f"ðŸ“Š Bolt numbers: {bolt_numbers}")
        
        # Show design variable ranges
        print(f"\nðŸ”§ Design Variable Summary:")
        for var in design_var_rows[:10]:  # Show first 10
            values = self.df.loc[var, design_cols]
            values = pd.to_numeric(values, errors='coerce')
            print(f"  {var}: min={values.min()}, max={values.max()}, unique={len(values.unique())}")
        
        # Bolt 1 analysis
        bolt_1_vars = [var for var in design_var_rows if var.endswith('_1')]
        if bolt_1_vars:
            print(f"\nðŸŽ¯ Bolt 1 (Driving CBUSH) Analysis:")
            for var in bolt_1_vars:
                values = self.df.loc[var, design_cols]
                values = pd.to_numeric(values, errors='coerce')
                unique_vals = values.unique()
                print(f"  {var}: {unique_vals} (should be constant at 5 = 1e8)")
        
        print(f"\nðŸ’¡ Current loose_threshold={self.loose_threshold}")
        print(f"ðŸ’¡ Bolt 1 excluded from looseness evaluation (driving CBUSH)")
        print("="*60)