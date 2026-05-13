import pytest
from unittest.mock import patch, mock_open
from src.python.shared.operational_window import is_operational_window_active
from datetime import datetime
import pytz

@pytest.mark.parametrize("current_hour, start, end, expected", [
    (10, 9, 17, True),
    (8, 9, 17, False),
    (18, 9, 17, False),
    (23, 22, 6, True), # Overnight
    (2, 22, 6, True),  # Overnight
    (12, 22, 6, False), # Overnight
    (10, 0, 0, True),   # 24/7
])
def test_is_operational_window_active(current_hour, start, end, expected):
    ist = pytz.timezone("Asia/Kolkata")
    
    config_content = f"""
system:
  operational_window:
    start_hour_ist: {start}
    end_hour_ist: {end}
"""
    # Mock datetime.now to return a fixed time in IST
    with patch("src.python.shared.operational_window.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2024, 1, 1, current_hour, 0, 0, tzinfo=ist)
        with patch("builtins.open", mock_open(read_data=config_content)):
            assert is_operational_window_active() == expected

def test_is_operational_window_active_error():
    with patch("builtins.open", side_effect=Exception("error")):
        # When error occurs, defaults to 0-24 which is always active
        assert is_operational_window_active() == True
