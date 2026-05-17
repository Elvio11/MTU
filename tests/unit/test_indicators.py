import pytest
from src.python.shared.indicators import (
    calculate_rsi, 
    calculate_volume_trend, 
    analyze_trend
)

def test_calculate_rsi():
    # Constant prices -> RSI returns 50.0 for flat action
    prices = [10.0] * 20
    assert calculate_rsi(prices) == 50.0
    
    # Uptrend
    prices = [10 + i for i in range(20)]
    rsi = calculate_rsi(prices)
    assert rsi > 50
    
    # Downtrend
    prices = [50 - i for i in range(20)]
    rsi = calculate_rsi(prices)
    assert rsi < 50
    
    # Edge case: empty or small list
    assert calculate_rsi([]) is None
    assert calculate_rsi([10.0]) is None

def test_calculate_volume_trend():
    # Static volume - need 12 elements for long_window
    volumes = [1000] * 15
    assert calculate_volume_trend(volumes) == 1.0
    
    # Growing volume
    # Last 3: 2000, 2000, 2000 -> Mean 2000
    # Last 12: 1000 * 9 + 2000 * 3 -> Mean (9000 + 6000) / 12 = 1250
    # 2000 / 1250 = 1.6
    volumes = [1000] * 9 + [2000] * 3
    assert calculate_volume_trend(volumes) == 1.6
    
    # Edge cases
    assert calculate_volume_trend([]) == 1.0
    assert calculate_volume_trend([100]) == 1.0

def test_analyze_trend():
    # Strong uptrend
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    assert analyze_trend(prices) == "bullish"
    
    # Strong downtrend
    prices = [15.0, 14.0, 13.0, 12.0, 11.0, 10.0]
    assert analyze_trend(prices) == "bearish"
    
    # Neutral
    prices = [10.0, 10.1, 10.0, 10.1, 10.0]
    assert analyze_trend(prices) == "neutral"
    
    # Small data
    assert analyze_trend([10.0, 11.0]) == "neutral"
