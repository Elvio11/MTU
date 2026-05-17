import numpy as np
from typing import List, Dict, Optional

def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate the Relative Strength Index (RSI) for a given series of prices.
    """
    if len(prices) < period + 1:
        return None
    
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    if up == 0 and down == 0:
        rs = 1.0 # RSI 50
    elif down == 0:
        rs = 1000.0 # RSI near 100
    else:
        rs = up / down
        
    rsi = np.zeros_like(prices)
    rsi[:period] = 100.0 - (100.0 / (1.0 + rs))
    
    for i in range(period, len(prices)):
        delta = deltas[i - 1]
        if delta > 0:
            up_val = delta
            down_val = 0.0
        else:
            up_val = 0.0
            down_val = -delta
        
        up = (up * (period - 1) + up_val) / period
        down = (down * (period - 1) + down_val) / period
        
        if up == 0 and down == 0:
            rsi[i] = 50.0
        elif down == 0:
            rsi[i] = 100.0
        else:
            rs = up / down
            rsi[i] = 100.0 - (100.0 / (1.0 + rs))
            
    return float(rsi[-1])

def calculate_volume_trend(volumes: List[float], short_window: int = 3, long_window: int = 12) -> float:
    """
    Calculate the volume multiplier (current short average / historical long average).
    Returns 1.0 if insufficient data.
    """
    if len(volumes) < long_window:
        return 1.0
    
    short_avg = np.mean(volumes[-short_window:])
    long_avg = np.mean(volumes[-long_window:])
    
    if long_avg == 0:
        return 1.0
    
    return float(short_avg / long_avg)

def analyze_trend(prices: List[float]) -> str:
    """
    Determine basic price trend based on recent price action.
    Now more relaxed: checks if the current price is above the moving average of the last 5 candles.
    """
    if len(prices) < 5:
        return "neutral"
    
    current_price = prices[-1]
    avg_price = float(np.mean(prices[-5:]))
    
    # Check for strong breakout (all 3 of last 3 increasing)
    if prices[-1] > prices[-2] > prices[-3]:
        return "bullish"
        
    # Relaxed: overall upward trend
    if current_price > avg_price * 1.01: # 1% above average
        return "bullish"
    elif current_price < avg_price * 0.99: # 1% below average
        return "bearish"
    else:
        return "neutral"
