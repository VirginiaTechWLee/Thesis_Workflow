import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import queue
import traceback
from pathlib import Path

# Import your existing modules
try:
    from complete_bolt_prediction_script_v2 import main as run_analysis, CONFIG as DEFAULT_CONFIG
    from complete_bolt_prediction_script_v2 import (
        train_and_save_model, 
        load_and_format_fem_data, 
        load_model_and_predict, 
        display_results_and_validate
    )
except ImportError as e:
    messagebox.showerror("Import Error", 
                        f"Could not import required modules: {e}\n\n"
                        "Make sure these files are in the same directory:\n"
                        "- complete_bolt_prediction_script_v2.py\n"
                        "- bolt_health_classifier.py\n" 
                        "- heeds_data_processor.py")
    sys.exit(1)

class BoltHealthGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Bolt Health Monitoring System")
        self.root.geometry("900x700")
        
        # Configuration storage
        self.config = DEFAULT_CONFIG.copy()
        
        # Queue for thread communication
        self.output_queue = queue.Queue()
        
        # Create GUI components
        self.create_widgets()
        
        # Start output monitoring
        self.check_output_queue()
    
    def create_widgets(self):
        """Create all GUI components with tabbed interface"""
        
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="Bolt Health Monitoring System", 
                               font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 20))
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Create tabs
        self.create_config_tab()
        self.create_beam_layout_tab()
    def create_config_tab(self):
        """Create the main configuration tab"""
        
        # Configuration tab
        config_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(config_frame, text="Configuration & Analysis")
        
        # Configure grid weights for config frame
        config_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # === TRAINING DATA SECTION ===
        ttk.Label(config_frame, text="Training Data", 
                 font=("Arial", 12, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W)
        row += 1
        
        # Training data file
        ttk.Label(config_frame, text="HEEDS Training Data:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.training_file_var = tk.StringVar(value=self.config['training_data_file'])
        self.training_file_entry = ttk.Entry(config_frame, textvariable=self.training_file_var, width=50)
        self.training_file_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 5))
        ttk.Button(config_frame, text="Browse", 
                  command=lambda: self.browse_file(self.training_file_var, "HEEDS CSV")).grid(row=row, column=2, pady=2)
        row += 1
        
        # Loose threshold
        ttk.Label(config_frame, text="Loose Threshold:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.threshold_var = tk.IntVar(value=self.config['loose_threshold'])
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        ttk.Spinbox(threshold_frame, from_=1, to=11, textvariable=self.threshold_var, width=10).pack(side=tk.LEFT)
        ttk.Label(threshold_frame, text="(1=loose, 11=tight)").pack(side=tk.LEFT, padx=(10, 0))
        row += 1
        
        # Feature type
        ttk.Label(config_frame, text="Feature Type:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.feature_type_var = tk.StringVar(value=self.config['feature_type'])
        feature_combo = ttk.Combobox(config_frame, textvariable=self.feature_type_var, 
                                   values=['deltas_only', 'deltas_plus_modal', 'all_responses'], 
                                   state='readonly', width=20)
        feature_combo.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        row += 1
        
        # Label type
        ttk.Label(config_frame, text="Label Type:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.label_type_var = tk.StringVar(value=self.config['label_type'])
        label_combo = ttk.Combobox(config_frame, textvariable=self.label_type_var, 
                                 values=['spatial', 'binary'], state='readonly', width=20)
        label_combo.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        row += 1
        
        # Separator
        ttk.Separator(config_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, 
                                                           sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # === TEST DATA SECTION ===
        ttk.Label(config_frame, text="Test Data", 
                 font=("Arial", 12, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W)
        row += 1
        
        # Test FEM file
        ttk.Label(config_frame, text="Test FEM File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.test_file_var = tk.StringVar(value=self.config['test_fem_file'])
        self.test_file_entry = ttk.Entry(config_frame, textvariable=self.test_file_var, width=50)
        self.test_file_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 5))
        ttk.Button(config_frame, text="Browse", 
                  command=lambda: self.browse_file(self.test_file_var, "Test CSV")).grid(row=row, column=2, pady=2)
        row += 1
        
        # Baseline FEM file
        ttk.Label(config_frame, text="Baseline FEM File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.baseline_file_var = tk.StringVar(value=self.config.get('baseline_fem_file', ''))
        self.baseline_file_entry = ttk.Entry(config_frame, textvariable=self.baseline_file_var, width=50)
        self.baseline_file_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 5))
        ttk.Button(config_frame, text="Browse", 
                  command=lambda: self.browse_file(self.baseline_file_var, "Baseline CSV")).grid(row=row, column=2, pady=2)
        row += 1
        
        # Expected loose bolt
        ttk.Label(config_frame, text="Expected Loose Bolt:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.expected_bolt_var = tk.IntVar(value=self.config.get('expected_loose_bolt', 5))
        expected_frame = ttk.Frame(config_frame)
        expected_frame.grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        expected_spinbox = ttk.Spinbox(expected_frame, from_=1, to=20, textvariable=self.expected_bolt_var, width=10,
                                      command=self.update_expected_bolt_highlight)
        expected_spinbox.pack(side=tk.LEFT)
        # Bind to handle manual entry as well as spinbox buttons
        expected_spinbox.bind('<KeyRelease>', lambda e: self.root.after(100, self.update_expected_bolt_highlight))
        ttk.Label(expected_frame, text="(for validation)").pack(side=tk.LEFT, padx=(10, 0))
        row += 1
        
        # Separator
        ttk.Separator(config_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, 
                                                           sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # === MODEL SETTINGS SECTION ===
        ttk.Label(config_frame, text="Model Settings", 
                 font=("Arial", 12, "bold")).grid(row=row, column=0, columnspan=3, sticky=tk.W)
        row += 1
        
        # Model save directory
        ttk.Label(config_frame, text="Model Save Directory:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.model_dir_var = tk.StringVar(value=self.config['model_save_dir'])
        self.model_dir_entry = ttk.Entry(config_frame, textvariable=self.model_dir_var, width=50)
        self.model_dir_entry.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 5))
        ttk.Button(config_frame, text="Browse", 
                  command=self.browse_directory).grid(row=row, column=2, pady=2)
        row += 1
        
        # Random state
        ttk.Label(config_frame, text="Random State:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.random_state_var = tk.IntVar(value=self.config['random_state'])
        ttk.Spinbox(config_frame, from_=0, to=1000, textvariable=self.random_state_var, width=10).grid(row=row, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        row += 1
        
        # Control buttons
        button_frame = ttk.Frame(config_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=20)
        
        self.run_button = ttk.Button(button_frame, text="Run Analysis", command=self.run_analysis)
        self.run_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_analysis, state='disabled')
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Clear Output", command=self.clear_output).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        
        row += 1
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(config_frame, text="Status:").grid(row=row, column=0, sticky=tk.W)
        self.progress_label = ttk.Label(config_frame, textvariable=self.progress_var)
        self.progress_label.grid(row=row, column=1, sticky=tk.W, padx=(5, 0))
        row += 1
        
        self.progress_bar = ttk.Progressbar(config_frame, mode='indeterminate')
        self.progress_bar.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 10))
        row += 1
        
        # Output area
        ttk.Label(config_frame, text="Output:", font=("Arial", 12, "bold")).grid(row=row, column=0, sticky=tk.W)
        row += 1
        
        self.output_text = scrolledtext.ScrolledText(config_frame, height=15, width=100)
        self.output_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        
        # Configure row weight for output area
        config_frame.rowconfigure(row, weight=1)
    
    def create_beam_layout_tab(self):
        """Create the beam layout visualization tab"""
        
        # Beam layout tab
        beam_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(beam_frame, text="Beam Layout")
        
        # Configure grid weights
        beam_frame.columnconfigure(0, weight=1)
        beam_frame.rowconfigure(1, weight=1)
        
        # Title and description
        title_label = ttk.Label(beam_frame, text="Cantilever Beam - Bolt Layout", 
                               font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, pady=(0, 10))
        
        # Create canvas for SVG-like drawing
        self.beam_canvas = tk.Canvas(beam_frame, width=900, height=400, bg='white')
        self.beam_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Draw the beam layout
        self.draw_beam_layout()
        
        # Info panel
        info_frame = ttk.LabelFrame(beam_frame, text="Bolt Information", padding="10")
        info_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        
        info_text = """
Physical Layout:
â€¢ Linear cantilever beam from Z=0 to Z=1000
â€¢ 10 CBUSH elements (bolted connections) at Z=0, 100, 200, ..., 900
â€¢ Bolt 1 (Z=0): Driving CBUSH - fixed stiffness, excluded from analysis
â€¢ Bolts 2-10 (Z=100-900): Structural bolts that can be loosened

Node Mapping:
â€¢ Bolt 1: Nodes 1 â†” 111    â€¢ Bolt 6: Nodes 6 â†” 666
â€¢ Bolt 2: Nodes 2 â†” 222    â€¢ Bolt 7: Nodes 7 â†” 777
â€¢ Bolt 3: Nodes 3 â†” 333    â€¢ Bolt 8: Nodes 8 â†” 888
â€¢ Bolt 4: Nodes 4 â†” 444    â€¢ Bolt 9: Nodes 9 â†” 999
â€¢ Bolt 5: Nodes 5 â†” 555    â€¢ Bolt 10: Nodes 10 â†” 1010

Training Parameters:
â€¢ Each bolt has K4_X, K5_X, K6_X stiffness parameters
â€¢ Values: 1-11 scale (1=loose, 9=tight baseline, 11=very tight)
â€¢ Loose threshold: Values â‰¤ threshold considered loose
        """
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT, 
                              font=("Courier", 9))
        info_label.pack(anchor=tk.W)
        
        # Analysis thread
        self.analysis_thread = None
        self.stop_flag = False
    
    def draw_beam_layout(self):
        """Draw the cantilever beam layout on canvas"""
        canvas = self.beam_canvas
        canvas.delete("all")  # Clear canvas
        
        # Store bolt visual elements for dynamic updates
        self.bolt_circles = {}
        self.bolt_labels = {}
        
        # Colors
        beam_color = "#ddd"
        support_color = "#666"
        driving_bolt_color = "#ff6b6b"
        structural_bolt_color = "#74b9ff"
        expected_loose_color = "#fd79a8"
        predicted_bolt_color = "#fdcb6e"
        
        # Beam structure (main beam)
        canvas.create_rectangle(50, 180, 850, 220, fill=beam_color, outline="#666", width=2)
        
        # Fixed support
        canvas.create_rectangle(30, 160, 70, 240, fill=support_color, outline="#333", width=2)
        canvas.create_polygon([30, 160, 10, 140, 10, 260, 30, 240], fill="#888", outline="#333", width=2)
        
        # Ground lines
        canvas.create_line(5, 260, 35, 275, fill="#333")
        canvas.create_line(5, 270, 35, 285, fill="#333")
        canvas.create_line(5, 280, 35, 295, fill="#333")
        
        # Bolt positions and information
        bolt_positions = [
            (70, 1, "Bolt 1", "CBUSH 1", "Z=0", driving_bolt_color, "Driving CBUSH\nK=1e8 (fixed)"),
            (150, 2, "Bolt 2", "CBUSH 2", "Z=100", structural_bolt_color, "Node 2 â†” 222"),
            (230, 3, "Bolt 3", "CBUSH 3", "Z=200", structural_bolt_color, "Node 3 â†” 333"),
            (310, 4, "Bolt 4", "CBUSH 4", "Z=300", structural_bolt_color, "Node 4 â†” 444"),
            (390, 5, "Bolt 5", "CBUSH 5", "Z=400", structural_bolt_color, "Node 5 â†” 555"),
            (470, 6, "Bolt 6", "CBUSH 6", "Z=500", structural_bolt_color, "Node 6 â†” 666"),
            (550, 7, "Bolt 7", "CBUSH 7", "Z=600", structural_bolt_color, "Node 7 â†” 777"),
            (630, 8, "Bolt 8", "CBUSH 8", "Z=700", structural_bolt_color, "Node 8 â†” 888"),
            (710, 9, "Bolt 9", "CBUSH 9", "Z=800", structural_bolt_color, "Node 9 â†” 999"),
            (790, 10, "Bolt 10", "CBUSH 10", "Z=900", structural_bolt_color, "Node 10 â†” 1010")
        ]
        
        # Draw bolts and store references
        for x, bolt_num, bolt_name, cbush_name, z_pos, default_color, node_info in bolt_positions:
            # Determine actual color based on current state
            color = self.get_bolt_color(bolt_num, default_color)
            
            # Bolt circle
            if bolt_num == 1:
                radius = 15
                width = 3
            else:
                radius = 12  
                width = 2
                
            bolt_circle = canvas.create_oval(x-radius, 200-radius, x+radius, 200+radius, 
                                           fill=color, outline=self.darken_color(color), width=width)
            
            # Store reference for updates
            self.bolt_circles[bolt_num] = {
                'circle': bolt_circle,
                'x': x,
                'radius': radius,
                'default_color': default_color
            }
            
            # Labels
            canvas.create_text(x, 130, text=bolt_name, font=("Arial", 12, "bold"))
            canvas.create_text(x, 260, text=node_info, font=("Arial", 9))
            canvas.create_text(x, 315, text=z_pos, font=("Arial", 9), fill="#666")
            
            # Special labels for bolt 1
            if bolt_num == 1:
                canvas.create_text(x, 145, text="(Driving CBUSH)", font=("Arial", 9), fill="#d63031")
                canvas.create_text(x, 275, text="K=1e8 (fixed)", font=("Arial", 9), fill="#d63031")
        
        # Position markers
        marker_positions = [70, 150, 310, 470, 630, 790]
        for x in marker_positions:
            canvas.create_line(x, 280, x, 290, fill="#666")
        
        # Legend
        legend_x = 50
        legend_y = 340
        canvas.create_text(legend_x, legend_y, text="Legend:", font=("Arial", 12, "bold"), anchor="w")
        
        # Legend items
        legend_items = [
            (legend_x + 80, driving_bolt_color, "Driving CBUSH (Fixed)"),
            (legend_x + 280, structural_bolt_color, "Structural bolts"),
            (legend_x + 420, expected_loose_color, "Expected loose (test setup)"),
            (legend_x + 620, predicted_bolt_color, "Predicted loose (result)")
        ]
        
        for x, color, text in legend_items:
            canvas.create_oval(x-8, legend_y-8, x+8, legend_y+8, fill=color, outline=self.darken_color(color))
            canvas.create_text(x+15, legend_y, text=text, font=("Arial", 10), anchor="w")
        
        # Title
        canvas.create_text(450, 30, text="Cantilever Beam - Bolt Health Monitoring Layout", 
                          font=("Arial", 16, "bold"), fill="#333")
        
        # Status indicators (will be updated dynamically)
        self.expected_status = None
        self.predicted_status = None
        
        # Initial highlight of expected bolt
        self.update_expected_bolt_highlight()
    
    def get_bolt_color(self, bolt_num, default_color):
        """Determine the color for a bolt based on current state"""
        expected_bolt = self.expected_bolt_var.get()
        
        # Handle prediction results if available
        predicted_bolt = getattr(self, 'predicted_bolt', None)
        
        # Priority: predicted > expected > default
        if predicted_bolt == bolt_num:
            return "#fdcb6e"  # Predicted bolt color (orange)
        elif expected_bolt == bolt_num and bolt_num > 1:  # Don't highlight bolt 1
            return "#fd79a8"  # Expected loose color (pink)
        else:
            return default_color
    
    def darken_color(self, hex_color):
        """Darken a hex color for outline"""
        if hex_color.startswith('#'):
            hex_color = hex_color[1:]
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        darker_rgb = tuple(max(0, int(c * 0.7)) for c in rgb)
        return f"#{darker_rgb[0]:02x}{darker_rgb[1]:02x}{darker_rgb[2]:02x}"
    
    def update_expected_bolt_highlight(self):
        """Update the highlighting of the expected loose bolt"""
        if not hasattr(self, 'bolt_circles'):
            return
            
        expected_bolt = self.expected_bolt_var.get()
        canvas = self.beam_canvas
        
        # Clear previous status text if it exists
        if hasattr(self, 'expected_status') and self.expected_status:
            canvas.delete(self.expected_status)
        
        # Update all bolt colors
        for bolt_num, bolt_info in self.bolt_circles.items():
            color = self.get_bolt_color(bolt_num, bolt_info['default_color'])
            canvas.itemconfig(bolt_info['circle'], fill=color, outline=self.darken_color(color))
        
        # Add status text
        if expected_bolt == 1:
            status_text = "Note: Bolt 1 is the driving CBUSH and cannot be tested for looseness"
            color = "#e17055"
        elif expected_bolt < 1 or expected_bolt > 10:
            status_text = f"Warning: Bolt {expected_bolt} is outside valid range (2-10 for structural bolts)"
            color = "#e17055"
        else:
            status_text = f"Expected test condition: Bolt {expected_bolt} will be loosened"
            color = "#00b894"
            
        self.expected_status = canvas.create_text(450, 60, text=status_text, 
                                                font=("Arial", 11), fill=color)
    
    def update_predicted_bolt_highlight(self, predicted_bolt_num=None, prediction_label=None, confidence=None):
        """Update the highlighting of the predicted loose bolt"""
        if not hasattr(self, 'bolt_circles'):
            return
            
        # Store prediction for color determination
        self.predicted_bolt = predicted_bolt_num
        
        canvas = self.beam_canvas
        
        # Clear previous prediction status
        if hasattr(self, 'predicted_status') and self.predicted_status:
            canvas.delete(self.predicted_status)
        
        # Update all bolt colors
        for bolt_num, bolt_info in self.bolt_circles.items():
            color = self.get_bolt_color(bolt_num, bolt_info['default_color'])
            canvas.itemconfig(bolt_info['circle'], fill=color, outline=self.darken_color(color))
        
        # Add prediction status text
        if predicted_bolt_num:
            expected_bolt = self.expected_bolt_var.get()
            if predicted_bolt_num == expected_bolt:
                status_text = f"CORRECT: Predicted bolt {predicted_bolt_num} matches expected bolt {expected_bolt}"
                if confidence:
                    status_text += f" (confidence: {confidence:.1%})"
                color = "#00b894"  # Green for correct
            else:
                status_text = f"INCORRECT: Predicted bolt {predicted_bolt_num}, expected bolt {expected_bolt}"
                if confidence:
                    status_text += f" (confidence: {confidence:.1%})"
                color = "#e17055"  # Red for incorrect
        elif prediction_label:
            if prediction_label == 'all_tight':
                status_text = "Prediction: No loose bolts detected"
                color = "#74b9ff"  # Blue for all tight
            else:
                status_text = f"Prediction: {prediction_label}"
                color = "#fdcb6e"  # Orange for other predictions
        else:
            status_text = "No prediction available"
            color = "#636e72"
            
        self.predicted_status = canvas.create_text(450, 80, text=status_text, 
                                                 font=("Arial", 11, "bold"), fill=color)
    
    def browse_file(self, var, title):
        """Browse for a file"""
        filename = filedialog.askopenfilename(
            title=f"Select {title} File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if filename:
            var.set(filename)
    
    def browse_directory(self):
        """Browse for a directory"""
        directory = filedialog.askdirectory(title="Select Model Save Directory")
        if directory:
            self.model_dir_var.set(directory)
    
    def update_config(self):
        """Update configuration from GUI values"""
        self.config.update({
            'training_data_file': self.training_file_var.get(),
            'loose_threshold': self.threshold_var.get(),
            'feature_type': self.feature_type_var.get(),
            'label_type': self.label_type_var.get(),
            'test_fem_file': self.test_file_var.get(),
            'baseline_fem_file': self.baseline_file_var.get() or None,
            'expected_loose_bolt': self.expected_bolt_var.get(),
            'model_save_dir': self.model_dir_var.get(),
            'random_state': self.random_state_var.get()
        })
    
    def validate_inputs(self):
        """Validate user inputs"""
        errors = []
        
        # Check required files exist
        training_file = self.training_file_var.get()
        if not os.path.exists(training_file):
            errors.append(f"Training data file not found: {training_file}")
        
        test_file = self.test_file_var.get()
        if not os.path.exists(test_file):
            errors.append(f"Test FEM file not found: {test_file}")
        
        baseline_file = self.baseline_file_var.get()
        if baseline_file and not os.path.exists(baseline_file):
            errors.append(f"Baseline FEM file not found: {baseline_file}")
        
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False
        
        return True
    
    def run_analysis(self):
        """Run the bolt health analysis in a separate thread"""
        if not self.validate_inputs():
            return
        
        self.update_config()
        
        # Update GUI state
        self.run_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.progress_var.set("Running analysis...")
        self.progress_bar.start()
        self.clear_output()
        self.stop_flag = False
        
        # Start analysis thread
        self.analysis_thread = threading.Thread(target=self.run_analysis_thread)
        self.analysis_thread.daemon = True
        self.analysis_thread.start()
    
    def run_analysis_thread(self):
        """Run analysis in separate thread with output capture"""
        try:
            # Redirect stdout to capture print statements
            import io
            import contextlib
            
            output_buffer = io.StringIO()
            
            # Create custom stdout that both prints and captures
            class TeeOutput:
                def __init__(self, queue):
                    self.queue = queue
                
                def write(self, text):
                    if text.strip():  # Only send non-empty lines
                        self.queue.put(('output', text))
                
                def flush(self):
                    pass
            
            # Replace stdout temporarily
            original_stdout = sys.stdout
            sys.stdout = TeeOutput(self.output_queue)
            
            try:
                # Import and modify the global CONFIG in the original module
                import complete_bolt_prediction_script_v2 as script_module
                
                # Fix the string subtraction bug in the original code
                self.patch_fem_data_processing(script_module)
                
                # Temporarily update the module's CONFIG
                original_config = script_module.CONFIG.copy()
                script_module.CONFIG.update(self.config)
                
                # Run the main analysis
                script_module.main()
                
                # Restore original config
                script_module.CONFIG.update(original_config)
                
                # Signal completion
                self.output_queue.put(('status', 'Analysis completed successfully!'))
                
            finally:
                # Restore stdout
                sys.stdout = original_stdout
                
        except Exception as e:
            error_msg = f"Error during analysis: {str(e)}\n{traceback.format_exc()}"
            self.output_queue.put(('error', error_msg))
        
        finally:
            self.output_queue.put(('done', None))
    
    def patch_fem_data_processing(self, script_module):
        """Fix the string subtraction bug and feature alignment issues"""
        import pandas as pd
        
        # Store original functions
        original_load_and_format = script_module.load_and_format_fem_data
        original_load_model_and_predict = script_module.load_model_and_predict
        
        def fixed_load_and_format_fem_data(fem_file, baseline_file=None):
            """Fixed version that converts to numeric before subtraction"""
            
            print("="*80)
            print("STEP 2: PROCESSING NEW FEM DATA")
            print("="*80)
            
            print(f"ðŸ“‚ Loading new FEM case: {fem_file}")
            
            if not os.path.exists(fem_file):
                raise FileNotFoundError(f"FEM file not found: {fem_file}")
            
            # Load FEM data
            fem_data = pd.read_csv(fem_file)
            print(f"   Raw data shape: {fem_data.shape}")
            
            # Check if already in HEEDS format
            if 'Parameter' in fem_data.columns:
                print("   âœ… Data already in HEEDS format")
                fem_data_heeds = fem_data
            else:
                # Convert to HEEDS format if needed
                fem_data_heeds = script_module.convert_fem_to_heeds_format(fem_data)
            
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
            
            # Get feature data and convert to numeric immediately
            feature_data = fem_indexed.loc[response_rows, design_col]
            feature_data = pd.to_numeric(feature_data, errors='coerce').fillna(0)
            
            # Calculate deltas if baseline provided
            if baseline_file and os.path.exists(baseline_file):
                print(f"ðŸ“‚ Loading baseline: {baseline_file}")
                baseline_data = pd.read_csv(baseline_file)
                
                # Check if baseline is also in HEEDS format
                if 'Parameter' in baseline_data.columns:
                    baseline_heeds = baseline_data
                else:
                    baseline_heeds = script_module.convert_fem_to_heeds_format(baseline_data)
                
                baseline_indexed = baseline_heeds.set_index('Parameter')
                
                baseline_design_cols = [col for col in baseline_heeds.columns if col.startswith('Design')]
                baseline_col = baseline_design_cols[0] if baseline_design_cols else design_col
                
                baseline_features = baseline_indexed.loc[response_rows, baseline_col]
                # Convert baseline to numeric too
                baseline_features = pd.to_numeric(baseline_features, errors='coerce').fillna(0)
                
                # Calculate deltas (now both are numeric)
                print("   ðŸ”„ Calculating deltas from baseline...")
                feature_data = feature_data - baseline_features
                print(f"   âœ… Deltas calculated for {len(feature_data)} features")
            else:
                print("   âš ï¸ No baseline file provided - using raw values (not deltas)")
            
            # Convert to DataFrame
            features_df = pd.DataFrame([feature_data.values], columns=feature_data.index)
            
            print(f"   âœ… Final formatted features: {features_df.shape}")
            
            return features_df
        
        def fixed_load_model_and_predict(features_df, model_dir):
            """Fixed version with proper feature alignment debugging"""
            
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
                        import pickle
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
            
            # DEBUG: Check for feature alignment issues
            if feature_names is not None:
                test_features = set(features_df.columns)
                training_features = set(feature_names)
                
                missing_in_test = training_features - test_features
                extra_in_test = test_features - training_features
                
                print(f"ðŸ” Feature alignment check:")
                print(f"   Missing in test: {len(missing_in_test)}")
                print(f"   Extra in test: {len(extra_in_test)}")
                
                if len(missing_in_test) > 100:
                    print(f"   âš ï¸ Large number of missing features - potential alignment issue")
                    # Show some examples of what's missing and what's extra
                    print(f"   Missing examples: {list(missing_in_test)[:5]}")
                    print(f"   Extra examples: {list(extra_in_test)[:5]}")
                
                # Reorder and fill missing features
                print(f"   ðŸ”§ Aligning features with training data...")
                features_df = features_df.reindex(columns=feature_names, fill_value=0)
                print(f"   âœ… Features aligned")
            
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
            
            # Extract predicted bolt number for GUI highlighting
            predicted_bolt = None
            if prediction_label != 'all_tight' and 'loose_bolt_' in prediction_label:
                try:
                    bolt_part = prediction_label.replace('loose_bolt_', '')
                    if '_' not in bolt_part and bolt_part.isdigit():
                        predicted_bolt = int(bolt_part)
                except ValueError:
                    predicted_bolt = None
            
            results = {
                'prediction': prediction_label,
                'confidence': confidence,
                'predicted_bolt': predicted_bolt,
                'all_probabilities': class_probabilities,
                'top_5_predictions': sorted_predictions[:5]
            }
            
            return results
        
        def fixed_display_results_and_validate(results, expected_bolt=None):
            """Fixed version that sends prediction results to GUI without duplicating output"""
            
            # Send prediction results to GUI for diagram update
            if hasattr(self, 'output_queue'):
                self.output_queue.put(('prediction_result', results))
            
            # Return the predicted bolt for validation (don't call original display function)
            prediction = results['prediction']
            predicted_bolt = None
            if prediction != 'all_tight' and 'loose_bolt_' in prediction:
                try:
                    bolt_part = prediction.replace('loose_bolt_', '')
                    if '_' not in bolt_part and bolt_part.isdigit():
                        predicted_bolt = int(bolt_part)
                except ValueError:
                    predicted_bolt = None
            
            return predicted_bolt
        
        # Replace all functions in the module
        script_module.load_and_format_fem_data = fixed_load_and_format_fem_data
        script_module.load_model_and_predict = fixed_load_model_and_predict
        script_module.display_results_and_validate = fixed_display_results_and_validate
    
    def stop_analysis(self):
        """Stop the running analysis"""
        self.stop_flag = True
        self.output_queue.put(('status', 'Stopping analysis...'))
    
    def check_output_queue(self):
        """Check for messages from the analysis thread"""
        try:
            while True:
                message_type, message = self.output_queue.get_nowait()
                
                if message_type == 'output':
                    self.output_text.insert(tk.END, message)
                    self.output_text.see(tk.END)
                
                elif message_type == 'status':
                    self.progress_var.set(message)
                    if 'completed' in message.lower():
                        self.finish_analysis()
                
                elif message_type == 'prediction_result':
                    # Handle prediction results with diagram updates
                    prediction_data = message
                    predicted_bolt = prediction_data.get('predicted_bolt')
                    prediction_label = prediction_data.get('prediction')
                    confidence = prediction_data.get('confidence')
                    
                    # Update diagram highlighting
                    self.update_predicted_bolt_highlight(predicted_bolt, prediction_label, confidence)
                    
                    # Also update the output text
                    result_text = f"\nPREDICTION RESULTS:\n"
                    result_text += f"Predicted: {prediction_label}\n"
                    result_text += f"Confidence: {confidence:.1%}\n"
                    if predicted_bolt:
                        expected = self.expected_bolt_var.get()
                        result_text += f"Expected: Bolt {expected}, Predicted: Bolt {predicted_bolt}\n"
                        if predicted_bolt == expected:
                            result_text += "âœ… CORRECT PREDICTION!\n"
                        else:
                            result_text += "âŒ INCORRECT PREDICTION\n"
                    
                    self.output_text.insert(tk.END, result_text)
                    self.output_text.see(tk.END)
                
                elif message_type == 'error':
                    self.output_text.insert(tk.END, f"\nERROR: {message}\n")
                    self.output_text.see(tk.END)
                    messagebox.showerror("Analysis Error", message)
                    self.finish_analysis()
                
                elif message_type == 'done':
                    self.finish_analysis()
                
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_output_queue)
    
    def finish_analysis(self):
        """Clean up after analysis completion"""
        self.run_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.progress_bar.stop()
        if 'completed' not in self.progress_var.get().lower():
            self.progress_var.set("Analysis stopped")
    
    def clear_output(self):
        """Clear the output text area"""
        self.output_text.delete('1.0', tk.END)
    
    def save_config(self):
        """Save current configuration to file"""
        self.update_config()
        
        filename = filedialog.asksaveasfilename(
            title="Save Configuration",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write("# Bolt Health Monitoring Configuration\n")
                    for key, value in self.config.items():
                        f.write(f"{key} = {value}\n")
                messagebox.showinfo("Success", f"Configuration saved to {filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save configuration: {e}")

def main():
    """Main GUI application"""
    root = tk.Tk()
    app = BoltHealthGUI(root)
    
    # Center the window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (root.winfo_width() // 2)
    y = (root.winfo_screenheight() // 2) - (root.winfo_height() // 2)
    root.geometry(f"+{x}+{y}")
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        root.quit()

if __name__ == "__main__":
    main()