-- =============================================================================
-- PSD Results Database Schema
-- 
-- Database for storing Nastran PSD analysis results from HEEDS parametric
-- studies for ML-based bolt looseness detection.
--
-- Author: Wayne Lee (Virginia Tech)
-- =============================================================================

-- Studies table: Track different HEEDS studies
CREATE TABLE IF NOT EXISTS studies (
    study_id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_name TEXT NOT NULL UNIQUE,
    study_type TEXT NOT NULL,  -- 'sweep', 'doe', 'monte_carlo', 'manual'
    num_cases INTEGER,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT DEFAULT 'created'  -- 'created', 'running', 'completed', 'failed'
);

-- Cases table: Individual analysis cases within a study
CREATE TABLE IF NOT EXISTS cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_id INTEGER NOT NULL,
    case_name TEXT NOT NULL,
    case_number INTEGER,
    is_baseline INTEGER DEFAULT 0,
    pch_file TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (study_id) REFERENCES studies(study_id),
    UNIQUE(study_id, case_number)
);

-- Parameters table: Bolt stiffness values for each case
CREATE TABLE IF NOT EXISTS parameters (
    param_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    element_id INTEGER NOT NULL,  -- 1-10
    K4 REAL NOT NULL,          -- Rotational stiffness K4
    K5 REAL NOT NULL,          -- Rotational stiffness K5
    K6 REAL NOT NULL,          -- Rotational stiffness K6
    stiffness_level INTEGER,   -- 1-9 encoding (NULL if direct value)
    is_loosened BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (case_id) REFERENCES cases(case_id),
    UNIQUE(case_id, element_id)
);

-- PSD Data table: Full frequency-domain response curves
CREATE TABLE IF NOT EXISTS psd_data (
    psd_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,      -- Output node (1, 111, 222, ..., 1111)
    dof TEXT NOT NULL,             -- T1, T2, T3, R1, R2, R3
    data_type TEXT NOT NULL,   -- 'acceleration', 'displacement'
    frequency REAL NOT NULL,       -- Hz
    psd_value REAL NOT NULL,       -- PSD magnitude
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

-- Peaks table: Summary with area and top 3 peaks per node/DOF
CREATE TABLE IF NOT EXISTS peaks (
    peak_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    dof TEXT NOT NULL,
    data_type TEXT NOT NULL,
    area REAL,
    peak1_freq REAL,
    peak1_psd REAL,
    peak2_freq REAL,
    peak2_psd REAL,
    peak3_freq REAL,
    peak3_psd REAL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id),
    UNIQUE(case_id, node_id, dof, data_type)
);

-- Summary table: Aggregated metrics per case/node/dof
CREATE TABLE IF NOT EXISTS summary (
    summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    dof TEXT NOT NULL,
    data_type TEXT NOT NULL,
    area REAL,                     -- Area under PSD curve
    rms REAL,                      -- RMS value
    peak_freq_1 REAL,              -- Top peak frequency
    peak_psd_1 REAL,               -- Top peak value
    peak_freq_2 REAL,
    peak_psd_2 REAL,
    peak_freq_3 REAL,
    peak_psd_3 REAL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id),
    UNIQUE(case_id, node_id, dof, data_type)
);

-- Delta table: Differences from baseline
CREATE TABLE IF NOT EXISTS delta (
    delta_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    baseline_case_id INTEGER NOT NULL,
    node_id INTEGER NOT NULL,
    dof TEXT NOT NULL,
    data_type TEXT NOT NULL,
    delta_area REAL,
    delta_peak_freq_1 REAL,
    delta_peak_psd_1 REAL,
    FOREIGN KEY (case_id) REFERENCES cases(case_id),
    FOREIGN KEY (baseline_case_id) REFERENCES cases(case_id)
);

-- =============================================================================
-- INDEXES for query performance
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_cases_study ON cases(study_id);
CREATE INDEX IF NOT EXISTS idx_parameters_case ON parameters(case_id);
CREATE INDEX IF NOT EXISTS idx_parameters_element ON parameters(element_id);
CREATE INDEX IF NOT EXISTS idx_psd_data_case ON psd_data(case_id);
CREATE INDEX IF NOT EXISTS idx_psd_data_node_dof ON psd_data(node_id, dof);
CREATE INDEX IF NOT EXISTS idx_peaks_case ON peaks(case_id);
CREATE INDEX IF NOT EXISTS idx_summary_case ON summary(case_id);

-- =============================================================================
-- VIEWS for common queries
-- =============================================================================

-- View: Cases with loosened bolt info
CREATE VIEW IF NOT EXISTS v_cases_with_bolts AS
SELECT 
    c.case_id,
    c.case_name,
    c.study_id,
    s.study_name,
    GROUP_CONCAT(CASE WHEN p.is_loosened THEN p.element_id END) as loosened_bolts,
    COUNT(CASE WHEN p.is_loosened THEN 1 END) as num_loosened
FROM cases c
JOIN studies s ON c.study_id = s.study_id
LEFT JOIN parameters p ON c.case_id = p.case_id
GROUP BY c.case_id;

-- View: Summary statistics per study
CREATE VIEW IF NOT EXISTS v_study_stats AS
SELECT 
    s.study_id,
    s.study_name,
    s.study_type,
    COUNT(c.case_id) as total_cases,
    SUM(CASE WHEN c.status = 'completed' THEN 1 ELSE 0 END) as completed_cases,
    SUM(CASE WHEN c.status = 'failed' THEN 1 ELSE 0 END) as failed_cases
FROM studies s
LEFT JOIN cases c ON s.study_id = c.study_id
GROUP BY s.study_id;

-- =============================================================================
-- SAMPLE DATA for baseline
-- =============================================================================

-- Insert baseline study (uncomment to initialize)
-- INSERT INTO studies (study_name, study_type, num_cases, description)
-- VALUES ('baseline', 'manual', 1, 'Baseline configuration with all healthy bolts');
