"""
Complete Bolt Health Monitoring - Training & Prediction Script
============================================================

This script does everything in one run:
1. Train model using your HEEDS data
2. Save trained model
3. Test prediction on new FEM case
4. Show results and validation

Usage:
    python complete_bolt_prediction.py

Make sure these files are in the same directory:
- heeds_data_processor.py
- bolt_health_classifier.py
- Your HEEDS training data CSV
- Your new FEM test case CSV
"""

import pandas as pd
import numpy as np
import pickle
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Import your existing modules
from heeds_data_processor import HEEDSDataProcessor
from bolt_health_classifier import BoltHealthClassifier

# ================================================================================================
# CONFIGURATION - EDIT THESE PATHS AND SETTINGS
# ================================================================================================

CONFIG = {
    # Training data
    'training_data_file': 'Study_Single72_results.csv',  # Your HEEDS results
    'loose_threshold': 8,  # Threshold that worked well (8 gave you good results)
    'feature_type': 'deltas_only',
    'label_type': 'spatial',
    
    # Test case data
    'test_fem_file': 'test_bolt8_loose.csv',  # New FEM case with bolt 5 loosened
    'baseline_fem_file': 'baseline_all_tight.csv',  # Baseline case (all bolts tight)
    'expected_loose_bolt': 5,  # Which bolt you loosened (for validation)
    
    # Model saving
    'model_save_dir': 'trained_bolt_model',
    'random_state': 42
}

# ================================================================================================
# STEP 1: TRAINING & MODEL SAVING
# ================================================================================================

def train_and_save_model(config):
    """Train bolt health model and save it for deployment"""
    
    print("="*80)
    print("STEP 1: TRAINING BOLT HEALTH MODEL")
    print("="*80)
    
    # Check if training data exists
    if not os.path.exists(config['training_data_file']):
        raise FileNotFoundError(f"Training data not found: {config['training_data_file']}")
    
    print(f"ðŸ“‚ Loading training data: {config['training_data_file']}")
    
    # Initialize processor
    processor = HEEDSDataProcessor(
        file_path=config['training_data_file'],
        loose_threshold=config['loose_threshold']
    )
    
    # Load and process data
    processor.load_data()
    
    # Create ML dataset
    X, y, feature_names, label_info = processor.create_ml_dataset(
        feature_type=config['feature_type'],
        label_type=config['label_type']
    )
    
    print(f"\nðŸ“Š Dataset created:")
    print(f"   Features: {X.shape[1]:,}")
    print(f"   Samples: {X.shape[0]:,}")
    print(f"   Classes: {len(y.unique()):,}")
    
    # Train classifier
    print(f"\nðŸ¤– Training classifier...")
    classifier = BoltHealthClassifier(random_state=config['random_state'])
    
    # Prepare data
    X_scaled, y_encoded, y_series = classifier.prepare_data(X, y)
    
    # Train models
    rf_score, xgb_score = classifier.train_ensemble(X_scaled, y_encoded)
    
    print(f"\nðŸ“ˆ Training Results:")
    print(f"   Random Forest CV: {rf_score:.4f}")
    print(f"   XGBoost CV: {xgb_score:.4f}")
    
    # Save model
    print(f"\nðŸ’¾ Saving trained model...")
    save_model_for_deployment(classifier, config['model_save_dir'])
    
    return classifier, processor, X, y, feature_names

def save_model_for_deployment(classifier, output_dir):
    """Save trained model components for standalone deployment"""
    
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    print(f"   Saving to: {output_dir}")
    
    # Save model components
    components = {
        'rf_model': classifier.rf_model,
        'xgb_model': classifier.xgb_model,
        'scaler': classifier.scaler,
        'label_encoder': classifier.label_encoder,
        'feature_names': classifier.feature_names,
        'model_info': classifier.get_model_summary()
    }
    
    for name, component in components.items():
        if component is not None:
            file_path = os.path.join(output_dir, f"{name}.pkl")
            with open(file_path, 'wb') as f:
                pickle.dump(component, f)
    
    # Save feature names for inspection
    if classifier.feature_names:
        feature_file = os.path.join(output_dir, "feature_names.txt")
        with open(feature_file, 'w') as f:
            for i, name in enumerate(classifier.feature_names):
                f.write(f"{i+1:4d}. {name}\n")
    
    print(f"   âœ… Model saved successfully!")
    return output_dir

# ================================================================================================
# STEP 2: FEM DATA PROCESSING
# ================================================================================================

def convert_fem_to_heeds_format(fem_data):
    """Convert FEM format (measurements x nodes) to HEEDS format (parameter-node x design)"""
    
    print("   ðŸ”„ Converting FEM format to HEEDS format...")
    
    # Check if it's already in HEEDS format
    if 'Parameter' in fem_data.columns:
        print("   âœ… Data already in HEEDS format")
        return fem_data
    
    # Check for FEM format with 'Measurement' column
    if 'Measurement' not in fem_data.columns:
        raise ValueError("Data must have either 'Parameter' or 'Measurement' column")
    
    # Get measurements and node columns
    measurements = fem_data['Measurement'].values
    node_cols = [col for col in fem_data.columns if col.startswith('Node_')]
    
    if len(node_cols) == 0:
        raise ValueError("No 'Node_' columns found in FEM data")
    
    print(f"   Found {len(measurements)} measurements across {len(node_cols)} nodes")
    
    # Create parameter-node combinations
    parameter_rows = []
    values = []
    
    for i, measurement in enumerate(measurements):
        for node_col in node_cols:
            # Create parameter name: ACCE_T1_Area_Node_111
            param_name = f"{measurement}_{node_col}"
            parameter_rows.append(param_name)
            
            # Get the value
            value = fem_data.loc[i, node_col] 
            values.append(value)
    
    # Create HEEDS-style DataFrame
    heeds_df = pd.DataFrame({
        'Parameter': parameter_rows,
        'min': '',
        'max': '',
        'Design 1': values
    })
    
    print(f"   âœ… Converted to {len(parameter_rows)} parameter-node combinations")
    
    return heeds_df

def load_and_format_fem_data(fem_file, baseline_file=None):
    """Load and format FEM data for prediction"""
    
    print("="*80)
    print("STEP 2: PROCESSING NEW FEM DATA")
    print("="*80)
    
    print(f"ðŸ“‚ Loading new FEM case: {fem_file}")
    
    if not os.path.exists(fem_file):
        raise FileNotFoundError(f"FEM file not found: {fem_file}")
    
    # Load FEM data
    fem_data = pd.read_csv(fem_file)
    print(f"   Raw data shape: {fem_data.shape}")
    
    # Convert to HEEDS format if needed
    fem_data_heeds = convert_fem_to_heeds_format(fem_data)
    
    # Now process in HEEDS format
    design_cols = [col for col in fem_data_heeds.columns if col.startswith('Design')]
    if len(design_cols) == 0:
        raise ValueError("No Design columns found after conversion")
    
    design_col = design_cols[0]
    print(f"   Using design column: {design_col}")
    
    # Set Parameter as index and extract response data
    fem_indexed = fem_data_heeds.set_index('Parameter')
    response_rows = [row for row in fem_indexed.index 
                    if not row.startswith(('K4_', 'K5_', 'K6_'))]
    
    print(f"   Found {len(response_rows)} response parameters")
    
    # Get feature data
    feature_data = fem_indexed.loc[response_rows, design_col]
    
    # Calculate deltas if baseline provided
    if baseline_file and os.path.exists(baseline_file):
        print(f"ðŸ“‚ Loading baseline: {baseline_file}")
        baseline_data = pd.read_csv(baseline_file)
        
        # Convert baseline to HEEDS format too
        baseline_heeds = convert_fem_to_heeds_format(baseline_data)
        baseline_indexed = baseline_heeds.set_index('Parameter')
        
        baseline_design_cols = [col for col in baseline_heeds.columns if col.startswith('Design')]
        baseline_col = baseline_design_cols[0] if baseline_design_cols else design_col
        
        baseline_features = baseline_indexed.loc[response_rows, baseline_col]
        
        # Calculate deltas
        print("   ðŸ”„ Calculating deltas from baseline...")
        feature_data = feature_data - baseline_features
        print(f"   âœ… Deltas calculated for {len(feature_data)} features")
    else:
        print("   âš ï¸ No baseline file provided - using raw values (not deltas)")
    
    # Convert to DataFrame
    features_df = pd.DataFrame([feature_data.values], columns=feature_data.index)
    features_df = features_df.apply(pd.to_numeric, errors='coerce').fillna(0)
    
    print(f"   âœ… Final formatted features: {features_df.shape}")
    
    return features_df

# ================================================================================================
# STEP 3: PREDICTION
# ================================================================================================

def load_model_and_predict(features_df, model_dir):
    """Load trained model and make prediction"""
    
    print("="*80)
    print("STEP 3: LOADING MODEL & MAKING PREDICTION")
    print("="*80)
    
    print(f"ðŸ“‚ Loading model from: {model_dir}")
    
    # Load model components
    model_files = {
        'rf_model': os.path.join(model_dir, 'rf_model.pkl'),
        'scaler': os.path.join(model_dir, 'scaler.pkl'),
        'label_encoder': os.path.join(model_dir, 'label_encoder.pkl'),
        'feature_names': os.path.join(model_dir, 'feature_names.pkl')
    }
    
    loaded_components = {}
    for name, file_path in model_files.items():
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                loaded_components[name] = pickle.load(f)
            print(f"   âœ… Loaded {name}")
        else:
            print(f"   âš ï¸ Missing {name}")
    
    # Prepare for prediction
    model = loaded_components['rf_model']
    scaler = loaded_components['scaler'] 
    label_encoder = loaded_components['label_encoder']
    feature_names = loaded_components.get('feature_names', None)
    
    if model is None:
        raise ValueError("Could not load trained model!")
    
    print(f"ðŸ” Making prediction...")
    print(f"   Input features: {features_df.shape[1]}")
    print(f"   Expected features: {len(feature_names) if feature_names else 'Unknown'}")
    
    # Align features with training data
    if feature_names is not None:
        # Reorder and fill missing features
        features_df = features_df.reindex(columns=feature_names, fill_value=0)
        print(f"   âœ… Features aligned with training data")
    
    # Scale features
    features_scaled = scaler.transform(features_df)
    
    # Make prediction
    prediction_encoded = model.predict(features_scaled)[0]
    prediction_proba = model.predict_proba(features_scaled)[0]
    
    # Decode prediction
    prediction_label = label_encoder.inverse_transform([prediction_encoded])[0]
    confidence = float(max(prediction_proba))
    
    # Get all class probabilities
    class_probabilities = {}
    for i, class_name in enumerate(label_encoder.classes_):
        class_probabilities[class_name] = float(prediction_proba[i])
    
    # Sort by probability
    sorted_predictions = sorted(class_probabilities.items(), 
                               key=lambda x: x[1], reverse=True)
    
    results = {
        'prediction': prediction_label,
        'confidence': confidence,
        'all_probabilities': class_probabilities,
        'top_5_predictions': sorted_predictions[:5]
    }
    
    return results

# ================================================================================================
# STEP 4: RESULTS & VALIDATION
# ================================================================================================

def display_results_and_validate(results, expected_bolt=None):
    """Display prediction results and validate against ground truth"""
    
    print("="*80)
    print("STEP 4: RESULTS & VALIDATION")
    print("="*80)
    
    prediction = results['prediction']
    confidence = results['confidence']
    
    print(f"ðŸŽ¯ PREDICTION RESULTS:")
    print(f"   Predicted class: {prediction}")
    print(f"   Confidence: {confidence:.1%}")
    
    # Interpret prediction
    print(f"\nðŸ” INTERPRETATION:")
    if prediction == 'all_tight':
        print(f"   ðŸ“‹ No loose bolts detected")
        print(f"   âœ… All bolts appear properly tightened")
        predicted_bolt = None
    elif 'loose_bolt_' in prediction:
        # Extract bolt number
        bolt_part = prediction.replace('loose_bolt_', '')
        if '_' not in bolt_part and bolt_part.isdigit():
            predicted_bolt = int(bolt_part)
            print(f"   ðŸš¨ LOOSE BOLT DETECTED: Bolt {predicted_bolt}")
            print(f"   ðŸ“ Location identified with {confidence:.1%} confidence")
        else:
            print(f"   ðŸš¨ Multiple bolts may be loose: {prediction}")
            predicted_bolt = None
    else:
        print(f"   â“ Unusual prediction: {prediction}")
        predicted_bolt = None
    
    # Show top predictions
    print(f"\nðŸ“Š TOP 5 POSSIBILITIES:")
    for i, (class_name, prob) in enumerate(results['top_5_predictions']):
        status = "ðŸ‘ˆ WINNER" if i == 0 else ""
        print(f"   {i+1}. {class_name:<20} {prob:>8.1%} {status}")
    
    # Validation against ground truth
    if expected_bolt is not None:
        print(f"\nðŸ§ª VALIDATION:")
        print(f"   Ground truth: Bolt {expected_bolt} was loosened")
        print(f"   Prediction: {prediction}")
        
        if predicted_bolt == expected_bolt:
            print(f"   âœ… CORRECT! Model correctly identified bolt {expected_bolt}")
            print(f"   ðŸŽ¯ Prediction confidence: {confidence:.1%}")
        elif prediction == 'all_tight':
            print(f"   âŒ MISS: Model failed to detect any loose bolt")
            print(f"   ðŸ’¡ Consider adjusting threshold or checking FEM setup")
        elif predicted_bolt is not None:
            print(f"   âŒ WRONG BOLT: Model predicted bolt {predicted_bolt}")
            print(f"   ðŸ’¡ Model detected loosening but wrong location")
        else:
            print(f"   âŒ UNCLEAR: Could not determine predicted bolt from '{prediction}'")
        
        # Confidence assessment
        if confidence < 0.7:
            print(f"   âš ï¸ LOW CONFIDENCE: {confidence:.1%} - results may be unreliable")
        elif confidence > 0.9:
            print(f"   ðŸ’ª HIGH CONFIDENCE: {confidence:.1%} - strong prediction")
    
    return predicted_bolt

# ================================================================================================
# MAIN EXECUTION
# ================================================================================================

def main():
    """Main execution function"""
    
    print("ðŸš€ BOLT HEALTH MONITORING - COMPLETE PIPELINE")
    print("=" * 80)
    print(f"Configuration:")
    for key, value in CONFIG.items():
        print(f"   {key}: {value}")
    print()
    
    try:
        # Step 1: Train and save model
        print("Starting training and model saving...")
        classifier, processor, X, y, feature_names = train_and_save_model(CONFIG)
        
        # Step 2: Load and format new FEM data
        print("\nLoading new FEM test case...")
        features_df = load_and_format_fem_data(
            CONFIG['test_fem_file'], 
            CONFIG.get('baseline_fem_file')
        )
        
        # Step 3: Make prediction
        print("\nMaking prediction...")
        results = load_model_and_predict(features_df, CONFIG['model_save_dir'])
        
        # Step 4: Display results and validate
        print("\nDisplaying results...")
        predicted_bolt = display_results_and_validate(
            results, 
            CONFIG.get('expected_loose_bolt')
        )
        
        # Final summary
        print(f"\n" + "="*80)
        print(f"FINAL SUMMARY")
        print(f"="*80)
        print(f"âœ… Training completed successfully")
        print(f"âœ… Model saved to: {CONFIG['model_save_dir']}")
        print(f"âœ… Prediction completed")
        
        if CONFIG.get('expected_loose_bolt'):
            expected = CONFIG['expected_loose_bolt']
            if predicted_bolt == expected:
                print(f"ðŸŽ¯ VALIDATION SUCCESS: Correctly identified bolt {expected}")
            else:
                print(f"âŒ VALIDATION FAILED: Expected bolt {expected}, got {predicted_bolt}")
        
        print(f"\nðŸ’¡ Next steps:")
        print(f"   - Test with different bolt positions")
        print(f"   - Validate on multiple FEM cases")
        print(f"   - Fine-tune model if needed")
        
    except FileNotFoundError as e:
        print(f"âŒ FILE ERROR: {e}")
        print(f"ðŸ’¡ Make sure all required files are in the current directory:")
        print(f"   - {CONFIG['training_data_file']}")
        print(f"   - {CONFIG['test_fem_file']}")
        if CONFIG.get('baseline_fem_file'):
            print(f"   - {CONFIG['baseline_fem_file']}")
        
    except Exception as e:
        print(f"âŒ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\nðŸ Script completed!")

# ================================================================================================
# QUICK SETUP GUIDE
# ================================================================================================

def print_setup_guide():
    """Print setup instructions"""
    
    print("""
ðŸ“‹ SETUP GUIDE - READ THIS FIRST!
================================

Before running this script, make sure you have:

1. FILES IN CURRENT DIRECTORY:
   âœ… heeds_data_processor.py
   âœ… bolt_health_classifier.py  
   âœ… Your HEEDS training data CSV
   âœ… Your new FEM test case CSV
   âœ… Your baseline FEM case CSV (optional but recommended)

2. EDIT CONFIG SECTION:
   - Set correct file names in CONFIG dictionary
   - Set expected_loose_bolt to match which bolt you loosened
   - Adjust loose_threshold if needed

3. RUN:
   python complete_bolt_prediction.py

The script will:
â†’ Train model on your HEEDS data
â†’ Save the trained model
â†’ Test on your new FEM case
â†’ Tell you which bolt is predicted loose
â†’ Validate against your ground truth

ðŸŽ¯ EXAMPLE TEST:
   - You loosen bolt 5 in FEM
   - Script should predict "loose_bolt_5"
   - Validation will show âœ… CORRECT!
""")

if __name__ == "__main__":
    
    # Check if user wants setup guide
    import sys
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        print_setup_guide()
    else:
        main()