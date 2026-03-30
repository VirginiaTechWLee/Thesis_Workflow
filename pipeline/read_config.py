"""Read fem_input/config.yaml and print key=value pairs for GitHub Actions."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config

config = load_config()
study = config['study']

# Allow workflow to override study type via env var
study_type_override = os.environ.get('STUDY_TYPE_OVERRIDE', '').strip()
if study_type_override:
    # Map workflow input names to config type names and study names
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
        # Compute expected designs dynamically
        from math import comb
        n_bolts = len(study.get('sweep_bolts', []))
        n_levels = len(study.get('sweep_levels', []))
        n_non_baseline = n_levels - 1
        if stype == 'single_bolt_sweep':
            study['expected_designs'] = n_bolts * n_non_baseline + 1  # +1 shared baseline design
        elif stype == 'two_bolt_sweep':
            study['expected_designs'] = comb(n_bolts, 2) * n_non_baseline
        elif stype == 'three_bolt_sweep':
            study['expected_designs'] = comb(n_bolts, 3) * n_non_baseline
        elif stype == 'all_bolt_sweep':
            study['expected_designs'] = n_non_baseline
        elif stype == 'monte_carlo':
            n_samples = config.get('monte_carlo', {}).get('n_samples', 500)
            study['expected_designs'] = n_samples + 1  # +1 for baseline design
        print(f"# Override: study_type={study_type_override} -> type={stype}, name={sname}", file=sys.stderr)

print('STUDY_NAME=' + str(study['name']))
print('STUDY_TYPE=' + str(study['type']))
print('EXPECTED_DESIGNS=' + str(study.get('expected_designs', len(study.get('sweep_levels', [])))))
print('SWEEP_BOLTS=' + ','.join(str(b) for b in study.get('sweep_bolts', [3])))
print('TOTAL_BOLTS=' + str(config['bolts']['total']))
print('STRUCTURAL_MODEL=' + str(config['files']['structural_model']))
print('RANDOM_RESPONSE=' + str(config['files'].get('random_response', 'RandomBeamX.dat')))
print('POSTPROCESSOR=' + str(config['files'].get('postprocessor', 'Pch_TO_CSV2.py')))
print('DB_PATH=' + str(config.get('database', {}).get('default_path', 'D:\\thesis_database\\thesis_results.db')))
print('LLM_REPORTS=' + str(config.get('pipeline', {}).get('llm_reports', False)).lower())
