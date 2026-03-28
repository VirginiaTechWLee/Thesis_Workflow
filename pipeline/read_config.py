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
        'study_C': ('two_bolt_independent_sweep', 'study_C_two_bolt_independent'),
        'study_D': ('random_multi_bolt_sweep', 'study_D_random_multi_bolt'),
    }
    if study_type_override in study_type_map:
        stype, sname = study_type_map[study_type_override]
        study['type'] = stype
        study['name'] = sname
        # Compute expected designs dynamically
        n_bolts = len(study.get('sweep_bolts', []))
        n_levels = len(study.get('sweep_levels', []))
        if stype == 'single_bolt_sweep':
            study['expected_designs'] = n_bolts * (n_levels - 1) + 1  # +1 baseline shared
        elif stype == 'two_bolt_sweep':
            from math import comb
            study['expected_designs'] = comb(n_bolts, 2) * (n_levels - 1)
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
