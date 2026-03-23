"""
Load and validate fem_input/config.yaml for the pipeline.

Every config-driven pipeline script imports this module to get model parameters.
"""

import os
import sys

try:
    import yaml
except ImportError:
    yaml = None


def load_dotenv(path=None):
    """Load .env file if present (simple key=value parser)."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), '..', '.env')
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _simple_yaml_parse(path):
    """Minimal YAML parser for flat/nested scalar values (fallback if PyYAML missing)."""
    config = {}
    stack = [config]
    indent_stack = [-1]
    with open(path, 'r') as f:
        for line in f:
            stripped = line.rstrip()
            if not stripped or stripped.lstrip().startswith('#'):
                continue
            indent = len(line) - len(line.lstrip())
            while indent <= indent_stack[-1]:
                stack.pop()
                indent_stack.pop()
            content = stripped.lstrip()
            if ':' in content:
                key, _, val = content.partition(':')
                key = key.strip()
                val = val.strip()
                if val == '':
                    new_dict = {}
                    stack[-1][key] = new_dict
                    stack.append(new_dict)
                    indent_stack.append(indent)
                elif val.startswith('[') and val.endswith(']'):
                    items = val[1:-1].split(',')
                    parsed = []
                    for item in items:
                        item = item.strip()
                        try:
                            parsed.append(int(item))
                        except ValueError:
                            try:
                                parsed.append(float(item))
                            except ValueError:
                                parsed.append(item.strip('"').strip("'"))
                    stack[-1][key] = parsed
                else:
                    val = val.strip('"').strip("'")
                    try:
                        stack[-1][key] = int(val)
                    except ValueError:
                        try:
                            stack[-1][key] = float(val)
                        except ValueError:
                            if val.lower() == 'true':
                                stack[-1][key] = True
                            elif val.lower() == 'false':
                                stack[-1][key] = False
                            else:
                                stack[-1][key] = val
    return config


def load_config(config_path=None):
    """Load config.yaml from fem_input/ or a custom path."""
    if config_path is None:
        candidates = [
            os.path.join(os.getcwd(), 'fem_input', 'config.yaml'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'fem_input', 'config.yaml'),
        ]
        for c in candidates:
            if os.path.exists(c):
                config_path = c
                break
        if config_path is None:
            raise FileNotFoundError("config.yaml not found in fem_input/")

    if yaml is not None:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print("WARNING: PyYAML not available, using simple parser")
        config = _simple_yaml_parse(config_path)

    # YAML parses "1.0e6" as a string; convert numeric-looking strings to floats
    # in sections that contain stiffness/numeric values
    for section in ['bolts', 'peaks', 'study']:
        if section in config:
            config[section] = ensure_float_recursive(config[section])

    return config


def ensure_float(value):
    """Ensure a value is a float (YAML may parse 1.0e6 as string)."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    return value


def ensure_float_recursive(obj):
    """Recursively convert string numbers to floats in config dicts/lists."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            result[k] = ensure_float_recursive(v)
        return result
    elif isinstance(obj, list):
        return [ensure_float_recursive(item) for item in obj]
    elif isinstance(obj, str):
        try:
            return float(obj)
        except (ValueError, TypeError):
            return obj
    return obj


def nastran_shorthand(value):
    """Convert float to Nastran shorthand notation (e.g., 1e8 -> '1.+8')."""
    if value == 0:
        return "0.0"
    exp = 0
    v = abs(value)
    if v >= 1:
        while v >= 10:
            v /= 10
            exp += 1
    else:
        while v < 1:
            v *= 10
            exp -= 1
    mantissa = value / (10 ** exp)
    if exp >= 0:
        if mantissa == int(mantissa):
            return f"{int(mantissa)}.+{exp}"
        else:
            return f"{mantissa:.6g}+{exp}"
    else:
        if mantissa == int(mantissa):
            return f"{int(mantissa)}.{exp}"
        else:
            return f"{mantissa:.6g}{exp}"


def nastran_field(value, width=8):
    """Format a float as a right-justified Nastran shorthand in a fixed-width field."""
    s = nastran_shorthand(value)
    return f"{s:>{width}s}"
