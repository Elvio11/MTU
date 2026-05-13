import pytest
from src.python.shared.position_validator import PositionValidator, get_position_validator

@pytest.fixture
def validator():
    return PositionValidator(max_position_size_sol=0.15, min_position_size_sol=0.001)

def test_validate_position_size(validator):
    assert validator.validate_position_size(0.1)[0] is True
    assert validator.validate_position_size(0.2)[0] is False # too big
    assert validator.validate_position_size(0.0001)[0] is False # too small

def test_validate_slippage(validator):
    assert validator.validate_slippage(1000)[0] is True
    assert validator.validate_slippage(3000)[0] is False # too high

def test_validate_token_address(validator):
    # Valid Solana address (base58)
    assert validator.validate_token_address("So11111111111111111111111111111111111111112")[0] is True
    # Invalid length
    assert validator.validate_token_address("short")[0] is False
    # Invalid characters (0, O, I, l)
    assert validator.validate_token_address("0OIl" * 10)[0] is False

def test_calculate_slippage_tier(validator):
    assert validator.calculate_slippage_tier(0) == 1000
    assert validator.calculate_slippage_tier(1) == 1500
    assert validator.calculate_slippage_tier(2) == 2000
    assert validator.calculate_slippage_tier(10) == 2000 # clamp to max

def test_validate_trade_params(validator):
    assert validator.validate_trade_params(0.1, 1000, "So11111111111111111111111111111111111111112")[0] is True
    assert validator.validate_trade_params(1.0, 1000, "So11111111111111111111111111111111111111112")[0] is False

def test_get_position_validator():
    v1 = get_position_validator()
    v2 = get_position_validator()
    assert v1 is v2
