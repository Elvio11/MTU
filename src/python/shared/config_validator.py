"""
Config Validator - Validates config.yaml against JSON Schema
Section 6.1: Startup validates config against schema
"""

import json
import os
from typing import Dict, Any, Tuple

try:
    from jsonschema import validate, ValidationError, Draft7Validator
except ImportError:
    raise ImportError("jsonschema is required. Install with: pip install jsonschema")

# Load schema
SCHEMA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "config", "config.schema.json"
)


def load_schema() -> Dict[str, Any]:
    """Load the JSON schema from config.schema.json"""
    schema_path = os.path.abspath(SCHEMA_PATH)
    if not os.path.exists(schema_path):
        return None, f"Schema file not found: {schema_path}"

    with open(schema_path, "r") as f:
        return json.load(f), None


def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate config dict against JSON schema.
    Returns (is_valid, error_message).
    """
    schema, err = load_schema()
    if err:
        return False, err

    try:
        validate(instance=config, schema=schema)
        return True, ""
    except ValidationError as e:
        return (
            False,
            f"Config validation error: {e.message} (path: {'.'.join(str(p) for p in e.path)})",
        )


def validate_config_file(config_path: str) -> Tuple[bool, str]:
    """
    Validate a config file against JSON schema.
    Returns (is_valid, error_message).
    """
    if not os.path.exists(config_path):
        return False, f"Config file not found: {config_path}"

    with open(config_path, "r") as f:
        import yaml

        try:
            config = yaml.safe_load(f)
        except Exception as e:
            return False, f"Failed to parse YAML: {e}"

    return validate_config(config)


def get_config_errors(config: Dict[str, Any]) -> list:
    """Get all validation errors (not just the first one)"""
    schema, err = load_schema()
    if err:
        return [err]

    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(config), key=str)
    return [f"{e.message} (path: {'.'.join(str(p) for p in e.path)})" for e in errors]


if __name__ == "__main__":
    # Test with default config
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    config_path = os.path.join(project_root, "config", "config.yaml")

    is_valid, error = validate_config_file(config_path)
    if is_valid:
        print("[OK] Config is valid!")
    else:
        print(f"[FAIL] Config validation failed: {error}")
        errors = get_config_errors(None)  # Will need config passed
        if errors:
            print("Errors:")
            for err in errors:
                print(f"  - {err}")
