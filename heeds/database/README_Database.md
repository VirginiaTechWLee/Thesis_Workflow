# HEEDS PSD Results Database

SQLite database for storing Nastran PSD analysis results from HEEDS parametric studies.

## Purpose

Store and query:
- Study metadata (sweep, DOE, Monte Carlo)
- Case configurations (which bolts loosened, stiffness values)
- Full PSD curves (266 frequency points × 12 nodes × 6 DOFs)
- Peak frequencies and amplitudes
- Delta comparisons vs baseline

## Schema Overview

```
studies          → Study metadata (name, type, status)
    │
    └── cases    → Individual analysis cases
            │
            ├── parameters  → Bolt stiffness values (K4, K5, K6)
            ├── psd_data    → Full frequency-domain curves
            ├── peaks       → Top 3 peaks per node/DOF
            ├── summary     → Aggregated metrics
            └── delta       → Differences from baseline
```

## Quick Start

### Initialize Database

```python
import sqlite3

# Create database
conn = sqlite3.connect('heeds/database/psd_results.db')

# Load schema
with open('heeds/database/schema.sql', 'r') as f:
    conn.executescript(f.read())

conn.close()
```

### Insert a Study

```python
cursor.execute("""
    INSERT INTO studies (study_name, study_type, num_cases, description)
    VALUES (?, ?, ?, ?)
""", ('sweep_72', 'sweep', 72, 'Single bolt sweep study'))
```

### Query Examples

```sql
-- Get all cases with loosened bolt 5
SELECT c.case_label, p.k4, p.k5, p.k6
FROM cases c
JOIN parameters p ON c.case_id = p.case_id
WHERE p.bolt_id = 5 AND p.is_loosened = 1;

-- Get peak frequencies for a specific case
SELECT node_id, dof, peak_rank, frequency, psd_value
FROM peaks
WHERE case_id = 47
ORDER BY node_id, dof, peak_rank;

-- Compare case to baseline
SELECT 
    d.node_id, d.dof,
    d.delta_area,
    d.delta_peak_freq_1
FROM delta d
WHERE d.case_id = 47;

-- Find cases with largest response change
SELECT 
    c.case_label,
    MAX(ABS(d.delta_peak_psd_1)) as max_delta
FROM cases c
JOIN delta d ON c.case_id = d.case_id
GROUP BY c.case_id
ORDER BY max_delta DESC
LIMIT 10;
```

## Data Sizes

| Study Type | Cases | PSD Rows | Est. Size |
|------------|-------|----------|-----------|
| Baseline | 1 | 28,728 | ~2 MB |
| Sweep (72) | 72 | 2.07M | ~150 MB |
| DOE (200) | 200 | 5.75M | ~400 MB |
| Monte Carlo (1000) | 1000 | 28.7M | ~2 GB |

## Files

- `schema.sql` - Database schema (tables, indexes, views)
- `psd_results.db` - SQLite database file (created on first use)
- `setup_database.py` - Script to initialize database
- `Pch_TO_Database.py` - Script to insert PCH results

## Integration with HEEDS Workflow

1. **Workflow 3** runs HEEDS study
2. **Workflow 4** (future) extracts results and inserts to database
3. **ML Training** queries database for training data
