"""Read fem_input/config.yaml and print key=value pairs for GitHub Actions."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from config_loader import load_config

config = load_config()
study = config['study']

print('STUDY_NAME=' + str(study['name']))
print('STUDY_TYPE=' + str(study['type']))
print('EXPECTED_DESIGNS=' + str(study.get('expected_designs', len(study.get('sweep_levels', [])))))
print('SWEEP_BOLTS=' + ','.join(str(b) for b in study.get('sweep_bolts', [3])))
print('TOTAL_BOLTS=' + str(config['bolts']['total']))
print('STRUCTURAL_MODEL=' + str(config['files']['structural_model']))
print('RANDOM_RESPONSE=' + str(config['files'].get('random_response', 'RandomBeamX.dat')))
print('POSTPROCESSOR=' + str(config['files'].get('postprocessor', 'Pch_TO_CSV2.py')))
