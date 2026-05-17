import pytest
import os
import json
import yaml
from unittest.mock import patch, mock_open
from src.python.shared.config_validator import (
    validate_config,
    validate_config_file,
    get_config_errors,
    load_schema,
)

VALID_CONFIG = {
    "system": {"environment": "paper", "log_level": "INFO", "trading_enabled": True},
    "trading": {
        "position_size_sol": 0.1,
        "max_positions": 5,
        "slippage_bps": 100,
        "take_profit_bps": 200,
        "stop_loss_bps": 100,
    },
    "rpc": {
        "helius_url": "http://helius",
        "quicknode_url": "http://qn",
        "alchemy_url": "http://alch",
    },
}

SCHEMA = {
    "type": "object",
    "properties": {
        "system": {"type": "object", "required": ["environment"]},
        "trading": {"type": "object"},
    },
    "required": ["system", "trading"],
}


@pytest.fixture
def mock_schema():
    with patch(
        "src.python.shared.config_validator.load_schema", return_value=(SCHEMA, None)
    ):
        yield


def test_load_schema_success():
    m = mock_open(read_data=json.dumps(SCHEMA))
    with (
        patch("src.python.shared.config_validator.open", m),
        patch("os.path.exists", return_value=True),
    ):
        schema, err = load_schema()
        assert schema == SCHEMA
        assert err is None


def test_load_schema_not_found():
    with patch("os.path.exists", return_value=False):
        schema, err = load_schema()
        assert schema is None
        assert "not found" in err


def test_validate_config_success(mock_schema):
    is_valid, err = validate_config(VALID_CONFIG)
    assert is_valid is True
    assert err == ""


def test_validate_config_schema_load_error():
    with patch(
        "src.python.shared.config_validator.load_schema",
        return_value=(None, "Schema Error"),
    ):
        is_valid, err = validate_config(VALID_CONFIG)
        assert is_valid is False
        assert err == "Schema Error"


def test_validate_config_failure(mock_schema):
    invalid_config = {"trading": {}}  # Missing system
    is_valid, err = validate_config(invalid_config)
    assert is_valid is False
    assert "validation error" in err


def test_validate_config_file_success(mock_schema):
    m = mock_open(read_data=yaml.dump(VALID_CONFIG))
    with (
        patch("src.python.shared.config_validator.open", m),
        patch("os.path.exists", return_value=True),
    ):
        is_valid, err = validate_config_file("fake.yaml")
        assert is_valid is True


def test_validate_config_file_not_found():
    with patch("os.path.exists", return_value=False):
        is_valid, err = validate_config_file("missing.yaml")
        assert is_valid is False
        assert "not found" in err


def test_validate_config_file_invalid_yaml():
    with (
        patch(
            "src.python.shared.config_validator.open",
            mock_open(read_data="invalid: yaml: :"),
        ),
        patch("os.path.exists", return_value=True),
    ):
        is_valid, err = validate_config_file("bad.yaml")
        assert is_valid is False
        assert "parse YAML" in err


def test_get_config_errors(mock_schema):
    invalid_config = {}  # Missing everything
    errors = get_config_errors(invalid_config)
    assert len(errors) > 0
    assert any("system" in e for e in errors)


def test_get_config_errors_schema_fail():
    with patch(
        "src.python.shared.config_validator.load_schema",
        return_value=(None, "Schema Error"),
    ):
        errors = get_config_errors(VALID_CONFIG)
        assert errors == ["Schema Error"]


def test_import_error_jsonschema():
    import importlib
    import sys

    with patch.dict(sys.modules, {"jsonschema": None}):
        with pytest.raises(ImportError, match="jsonschema is required"):
            importlib.reload(
                sys.modules.get("src.python.shared.config_validator")
                or __import__("src.python.shared.config_validator")
            )


VALID_CONFIG_DICT = {
    "system": {
        "trading_active": True,
        "operational_window": {"start_hour_ist": 9, "end_hour_ist": 17},
        "environment": "paper",
    },
    "wallets": {"sniper_keystore_path": "/sn", "main_keystore_path": "/mn"},
    "trading": {
        "position_size_sol": 0.1,
        "max_simultaneous_positions": 5,
        "max_trades_per_hour": 10,
    },
    "rpc": {"providers": [{"name": "helius", "http_url": "https://helius.com"}]},
}


def test_main_block_config_validator():
    import runpy

    real_abspath = os.path.abspath

    def _fix_project_root(path):
        result = real_abspath(path)
        if result.rstrip("\\").endswith("\\src"):
            return real_abspath(os.path.join(result, ".."))
        return result

    with patch("os.path.abspath", side_effect=_fix_project_root):
        with patch("yaml.safe_load", return_value=VALID_CONFIG_DICT):
            runpy.run_module("src.python.shared.config_validator", run_name="__main__")


def test_main_block_config_validator_invalid():
    import runpy

    real_abspath = os.path.abspath

    def _fix_project_root(path):
        result = real_abspath(path)
        if result.rstrip("\\").endswith("\\src"):
            return real_abspath(os.path.join(result, ".."))
        return result

    with patch("os.path.abspath", side_effect=_fix_project_root):
        with patch("yaml.safe_load", return_value={}):
            runpy.run_module("src.python.shared.config_validator", run_name="__main__")
