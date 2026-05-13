import pytest
import base64
import struct
from src.python.shared.bonding_curve import decode_bonding_curve, calculate_progress, BONDING_CURVE_LAYOUT, INITIAL_REAL_TOKEN_RESERVES

def test_decode_bonding_curve_success():
    # Construct a valid buffer
    # Discriminator: 8 bytes
    # virtualTokenReserves: u64
    # virtualQuoteReserves: u64
    # realTokenReserves: u64
    # realQuoteReserves: u64
    # tokenTotalSupply: u64
    # complete: bool (1 byte)
    data = struct.pack(BONDING_CURVE_LAYOUT, b"discrim1", 1000, 2000, 3000, 4000, 5000, 1)
    data_b64 = base64.b64encode(data).decode()
    
    result = decode_bonding_curve(data_b64)
    assert result is not None
    assert result["virtualTokenReserves"] == 1000
    assert result["virtualQuoteReserves"] == 2000
    assert result["realTokenReserves"] == 3000
    assert result["realQuoteReserves"] == 4000
    assert result["tokenTotalSupply"] == 5000
    assert result["complete"] is True

def test_decode_bonding_curve_short_data():
    data = base64.b64encode(b"too_short").decode()
    assert decode_bonding_curve(data) is None

def test_decode_bonding_curve_invalid_base64():
    assert decode_bonding_curve("!!!not_base64!!!") is None

def test_calculate_progress():
    # Full progress
    assert calculate_progress(0) == 100.0
    assert calculate_progress(-1) == 100.0
    
    # Half progress
    half_reserves = INITIAL_REAL_TOKEN_RESERVES // 2
    progress = calculate_progress(half_reserves)
    assert 49.0 < progress < 51.0
    
    # Zero progress
    assert calculate_progress(INITIAL_REAL_TOKEN_RESERVES) == 0.0
    
    # Over progress
    assert calculate_progress(INITIAL_REAL_TOKEN_RESERVES * 2) == 0.0
