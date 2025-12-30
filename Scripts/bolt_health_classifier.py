import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb
from typing import Dict, List, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

class BoltHealthClassifier:
    """
    Enhanced ML classifier for bolt health monitoring with multi-class support
    Handles both binary and spatial (multi-class) classification
    """
    
    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.label_encoder = LabelEncoder()
        
        # Initialize models (will be configured based on problem type)
        self.rf_model = None
        self.xgb_model = None
        
        # Store model info
        self.feature_names = None
        self.is_multiclass = False
        self.n_classes = 0
        self.class_names = None
        
    def prepare_data(self, X: pd.DataFrame, y: pd.Series) -> Tuple[np.ndarray, np.ndarray, pd.Series]:
        """
        Prepare and encode data for ML training
        
        Returns:
            X_scaled: Scaled features
            y_encoded: Encoded labels  
            y_series: Original labels for reference
        """
        print(f"Preparing data: {X.shape[0]} samples, {X.shape[1]} features")
        
        # Store feature names
        self.feature_names = X.columns.tolist()
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        print(f"âœ… Features scaled")
        
        # Encode labels
        y_encoded = self.label_encoder.fit_transform(y)
        self.class_names = self.label_encoder.classes_
        self.n_classes = len(self.class_names)
        self.is_multiclass = self.n_classes > 2
        
        print(f"âœ… Labels encoded: {self.n_classes} classes")
        print(f"   Classes: {list(self.class_names[:5])}{'...' if len(self.class_names) > 5 else ''}")
        print(f"   Multi-class problem: {self.is_multiclass}")
        
        return X_scaled, y_encoded, y
    
    def _configure_models(self):
        """Configure models based on problem type (binary vs multi-class)"""
        
        if self.is_multiclass:
            print(f"Configuring for multi-class classification ({self.n_classes} classes)")
            
            # Random Forest - works naturally with multi-class
            self.rf_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=self.random_state,
                n_jobs=-1
            )
            
            # XGBoost - configured for multi-class
            self.xgb_model = xgb.XGBClassifier(
                objective='multi:softprob',  # Multi-class classification
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                n_jobs=-1,
                eval_metric='mlogloss'  # Multi-class log loss
            )
            
        else:
            print(f"Configuring for binary classification")
            
            # Random Forest - same config works for binary
            self.rf_model = RandomForestClassifier(
                n_estimators=100,
                max_depth=15,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=self.random_state,
                n_jobs=-1
            )
            
            # XGBoost - configured for binary classification
            self.xgb_model = xgb.XGBClassifier(
                objective='binary:logistic',  # Binary classification
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                subsample=0.8,
                colsample_bytree=0.8,
                random_state=self.random_state,
                n_jobs=-1,
                eval_metric='logloss'  # Binary log loss
            )
    
    def train_ensemble(self, X_scaled: np.ndarray, y_encoded: np.ndarray) -> Tuple[float, float]:
        """
        Train ensemble of Random Forest and XGBoost models
        
        Returns:
            rf_score: Random Forest cross-validation score
            xgb_score: XGBoost cross-validation score
        """
        
        # Check if we have enough classes for meaningful ML
        unique_classes = np.unique(y_encoded)
        n_unique = len(unique_classes)
        
        if n_unique == 1:
            print(f"âš  Cannot train models: Only 1 unique class found")
            print(f"   All samples have the same label. This is not a classification problem.")
            print(f"   Please adjust your loose_threshold or check your data.")
            return 0.0, 0.0
        
        # Configure models based on problem type
        self._configure_models()
        
        # Set up cross-validation
        cv_folds = min(5, n_unique, 10)  # Ensure at least 2 folds and reasonable max
        if cv_folds < 2:
            cv_folds = 2
            
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=self.random_state)
        
        print(f"Training ensemble with {cv_folds}-fold cross-validation...")
        print(f"Number of unique classes: {n_unique}")
        
        # Train Random Forest
        print("ðŸŒ³ Training Random Forest...")
        try:
            rf_scores = cross_val_score(self.rf_model, X_scaled, y_encoded, cv=cv, scoring='accuracy')
            rf_score = rf_scores.mean()
            
            # Fit RF for feature importance later
            self.rf_model.fit(X_scaled, y_encoded)
            print(f"   Random Forest CV accuracy: {rf_score:.4f} (Â±{rf_scores.std()*2:.4f})")
            
        except Exception as e:
            print(f"   âš ï¸ Random Forest training failed: {e}")
            rf_score = 0.0
        
        # Train XGBoost
        print("ðŸš€ Training XGBoost...")
        try:
            xgb_scores = cross_val_score(self.xgb_model, X_scaled, y_encoded, cv=cv, scoring='accuracy')
            xgb_score = xgb_scores.mean()
            
            # Fit XGB for feature importance later
            self.xgb_model.fit(X_scaled, y_encoded)
            print(f"   XGBoost CV accuracy: {xgb_score:.4f} (Â±{xgb_scores.std()*2:.4f})")
            
        except Exception as e:
            print(f"   âš ï¸ XGBoost training failed: {e}")
            print(f"   Continuing with Random Forest only...")
            xgb_score = 0.0
        
        return rf_score, xgb_score
    
    def leave_one_bolt_out_validation(self, processor, X_scaled: np.ndarray, 
                                    y_series: pd.Series) -> Tuple[Dict, float]:
        """
        Perform leave-one-bolt-out cross-validation with BINARY classification
        
        For LOBO, we test spatial generalization using binary labels:
        - Can we detect that SOME bolt is loose at a new position?
        - This is more realistic than predicting the exact bolt identity
        """
        print("\nðŸ” Running leave-one-bolt-out validation...")
        print("ðŸŽ¯ Converting to BINARY classification for LOBO test")
        print("   'all_tight' â†’ 0 (no loose bolts)")
        print("   'loose_bolt_X' â†’ 1 (some bolt is loose)")
        
        # Convert spatial labels to binary for LOBO testing
        binary_labels = pd.Series([0 if label == 'all_tight' else 1 for label in y_series], 
                                 index=y_series.index)
        
        print(f"\nBinary label distribution:")
        binary_counts = binary_labels.value_counts()
        for label, count in binary_counts.items():
            label_name = 'all_tight' if label == 0 else 'some_bolt_loose'
            percentage = (count / len(binary_labels)) * 100
            print(f"  {label} ({label_name}): {count:,} samples ({percentage:.1f}%)")
        
        # Group by original bolt configuration for proper LOBO splits
        bolt_groups = self._group_by_bolt_configuration(processor, 
                                                       processor.get_design_columns(), 
                                                       y_series)
        
        results = {}
        all_predictions = []
        all_true = []
        successful_tests = 0
        
        print(f"\nTesting {len(bolt_groups)} different bolt configurations:")
        
        for bolt_label, indices in bolt_groups.items():
            if len(indices) < 2:  # Skip if too few samples
                print(f"  Skipping {bolt_label}: only {len(indices)} samples")
                continue
            
            print(f"\n  Testing: {bolt_label} ({len(indices)} samples)")
            
            # Create train/test split
            test_mask = np.isin(range(len(X_scaled)), indices)
            train_mask = ~test_mask
            
            X_train, X_test = X_scaled[train_mask], X_scaled[test_mask]
            y_train_binary = binary_labels.iloc[train_mask]
            y_test_binary = binary_labels.iloc[test_mask]
            
            # Check if we have both classes in training set
            unique_train_labels = y_train_binary.unique()
            if len(unique_train_labels) < 2:
                print(f"    âš ï¸ Skipping: training set only has {len(unique_train_labels)} unique labels")
                print(f"       Training labels: {unique_train_labels}")
                results[bolt_label] = {
                    'accuracy': 0.0,
                    'num_test_samples': len(y_test_binary),
                    'error': 'Insufficient training diversity'
                }
                continue
            
            try:
                # Train binary classifier
                temp_model = RandomForestClassifier(
                    n_estimators=100, 
                    random_state=self.random_state, 
                    n_jobs=-1,
                    class_weight='balanced'  # Handle class imbalance
                )
                temp_model.fit(X_train, y_train_binary)
                
                # Predict on held-out bolt
                y_pred_binary = temp_model.predict(X_test)
                
                accuracy = accuracy_score(y_test_binary, y_pred_binary)
                
                # Convert back to interpretable labels for reporting
                true_interpretable = ['all_tight' if x == 0 else 'some_bolt_loose' for x in y_test_binary]
                pred_interpretable = ['all_tight' if x == 0 else 'some_bolt_loose' for x in y_pred_binary]
                
                results[bolt_label] = {
                    'accuracy': accuracy,
                    'num_test_samples': len(y_test_binary),
                    'true_labels': list(set(true_interpretable)),
                    'predicted_labels': list(set(pred_interpretable)),
                    'original_spatial_label': bolt_label,
                    'binary_test': True
                }
                
                print(f"    âœ… Accuracy: {accuracy:.4f}")
                print(f"       True: {set(true_interpretable)}")
                print(f"       Pred: {set(pred_interpretable)}")
                
                # For overall accuracy calculation
                all_predictions.extend(y_pred_binary)
                all_true.extend(y_test_binary)
                successful_tests += 1
                
            except Exception as e:
                print(f"    âŒ Error: {e}")
                results[bolt_label] = {
                    'accuracy': 0.0,
                    'num_test_samples': len(indices),
                    'error': str(e),
                    'original_spatial_label': bolt_label
                }
        
        # Calculate overall accuracy
        if all_true and all_predictions:
            overall_accuracy = accuracy_score(all_true, all_predictions)
        else:
            overall_accuracy = 0.0
        
        # Summary
        print(f"\nðŸ“Š LOBO VALIDATION SUMMARY:")
        print(f"   Tests completed: {successful_tests}/{len(bolt_groups)}")
        print(f"   Overall binary accuracy: {overall_accuracy:.4f}")
        
        if successful_tests > 0:
            accuracies = [r['accuracy'] for r in results.values() if 'accuracy' in r and r['accuracy'] > 0]
            if accuracies:
                print(f"   Average per-bolt accuracy: {np.mean(accuracies):.4f}")
                print(f"   Best single-bolt accuracy: {max(accuracies):.4f}")
                print(f"   Worst single-bolt accuracy: {min(accuracies):.4f}")
        
        print(f"\nðŸŽ¯ INTERPRETATION:")
        if overall_accuracy > 0.90:
            print(f"   âœ… Excellent spatial generalization! Model can detect loose bolts at new positions.")
        elif overall_accuracy > 0.80:
            print(f"   âœ… Good spatial generalization. Model shows promise for new bolt positions.")
        elif overall_accuracy > 0.70:
            print(f"   âš ï¸ Moderate spatial generalization. Consider more training data or feature engineering.")
        else:
            print(f"   âŒ Poor spatial generalization. Model may be overfitting to specific bolt positions.")
        
        return results, overall_accuracy
    
    def _group_by_bolt_configuration(self, processor, design_cols: List[str], 
                                   y_series: pd.Series) -> Dict[str, List[int]]:
        """Group design points by bolt configuration for proper LOBO validation"""
        
        print("ðŸ”§ Grouping design points by bolt configuration...")
        bolt_groups = {}
        
        # Debug: Check what labels we actually have
        unique_labels = y_series.unique()
        print(f"Unique labels in dataset: {list(unique_labels)}")
        
        # Create groups based on the actual labels (which bolt pattern is loose)
        for i, label in enumerate(y_series):
            if label not in bolt_groups:
                bolt_groups[label] = []
            bolt_groups[label].append(i)
        
        # Print grouping summary
        print(f"Created {len(bolt_groups)} LOBO groups:")
        for label, indices in bolt_groups.items():
            print(f"  '{label}': {len(indices)} samples")
        
        return bolt_groups
    
    def analyze_feature_importance(self, feature_names: List[str]) -> pd.DataFrame:
        """
        Analyze feature importance from trained models
        """
        print("\nðŸ” Analyzing feature importance...")
        
        importance_data = []
        
        # Random Forest importance
        if self.rf_model is not None:
            rf_importance = self.rf_model.feature_importances_
            
            for i, (name, importance) in enumerate(zip(feature_names, rf_importance)):
                importance_data.append({
                    'feature': name,
                    'rf_importance': importance,
                    'xgb_importance': 0.0,  # Default
                    'ensemble_importance': importance  # Will update if XGB available
                })
        
        # XGBoost importance
        if self.xgb_model is not None:
            try:
                xgb_importance = self.xgb_model.feature_importances_
                
                for i, importance in enumerate(xgb_importance):
                    if i < len(importance_data):
                        importance_data[i]['xgb_importance'] = importance
                        # Ensemble importance (average of RF and XGB)
                        importance_data[i]['ensemble_importance'] = (
                            importance_data[i]['rf_importance'] + importance
                        ) / 2
            except Exception as e:
                print(f"Warning: Could not get XGBoost importance: {e}")
        
        # Create DataFrame and sort by ensemble importance
        importance_df = pd.DataFrame(importance_data)
        importance_df = importance_df.sort_values('ensemble_importance', ascending=False)
        
        print(f"âœ… Feature importance analysis completed")
        print(f"Top 5 features:")
        for i, row in importance_df.head().iterrows():
            print(f"  {i+1}. {row['feature']} ({row['ensemble_importance']:.6f})")
        
        return importance_df
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Make predictions using the ensemble"""
        if self.rf_model is None:
            raise ValueError("Models not trained. Call train_ensemble() first.")
        
        X_scaled = self.scaler.transform(X)
        
        # Use Random Forest as primary predictor
        predictions = self.rf_model.predict(X_scaled)
        
        # Convert back to original labels
        return self.label_encoder.inverse_transform(predictions)
    
    def get_model_summary(self) -> Dict[str, Any]:
        """Get summary of trained models"""
        return {
            'n_classes': self.n_classes,
            'class_names': list(self.class_names) if self.class_names is not None else [],
            'is_multiclass': self.is_multiclass,
            'n_features': len(self.feature_names) if self.feature_names else 0,
            'models_trained': {
                'random_forest': self.rf_model is not None,
                'xgboost': self.xgb_model is not None
            }
        }


def run_complete_analysis(file_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run complete bolt health analysis pipeline
    """
    from heeds_data_processor import HEEDSDataProcessor
    
    print("ðŸš€ Starting complete bolt health analysis...")
    print(f"Configuration: {config}")
    
    # Step 1: Load data
    processor = HEEDSDataProcessor(
        file_path=file_path,
        loose_threshold=config['loose_threshold']
    )
    processor.load_data()
    
    # Step 2: Create ML dataset
    X, y, feature_names, label_info = processor.create_ml_dataset(
        feature_type=config['feature_type'],
        label_type=config['label_type']
    )
    
    # Step 3: Train models
    classifier = BoltHealthClassifier(random_state=config['random_state'])
    X_scaled, y_encoded, y_series = classifier.prepare_data(X, y)
    
    rf_score, xgb_score = classifier.train_ensemble(X_scaled, y_encoded)
    
    # Step 4: Validation
    validation_results, overall_accuracy = classifier.leave_one_bolt_out_validation(
        processor, X_scaled, y_series
    )
    
    # Step 5: Feature importance
    importance_df = classifier.analyze_feature_importance(feature_names)
    
    return {
        'processor': processor,
        'classifier': classifier,
        'rf_score': rf_score,
        'xgb_score': xgb_score,
        'overall_accuracy': overall_accuracy,
        'validation_results': validation_results,
        'importance_df': importance_df,
        'model_summary': classifier.get_model_summary()
    }