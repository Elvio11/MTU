import pytest
from unittest.mock import patch, MagicMock
from src.python.shared.safe_output import safe_print, safe_str, setup_console
import sys

def test_safe_str():
    assert safe_str("✅ Success") == "[OK] Success"
    assert safe_str("❌ Error") == "[X] Error"
    assert safe_str("Normal") == "Normal"

def test_safe_print():
    with patch("builtins.print") as mock_print:
        safe_print("✅", "❌", 123)
        mock_print.assert_called_with("[OK]", "[X]", 123)

def test_safe_print_unicode_error():
    # Force UnicodeEncodeError on the first call
    # The second call is the fallback
    with patch("builtins.print", side_effect=[UnicodeEncodeError("utf-8", "", 0, 1, ""), None]) as mock_print:
        safe_print("Special emoji 🦄")
        # Should call print twice
        assert mock_print.call_count == 2
        # Fallback should have replaced the emoji
        assert "Special emoji ?" in mock_print.call_args[0][0]

def test_setup_console_win32():
    # Test the function logic directly
    with patch("sys.platform", "win32"):
        mock_stdout = MagicMock()
        mock_stdout.buffer = MagicMock()
        with patch("sys.stdout", mock_stdout):
            with patch("codecs.getwriter") as mock_getwriter:
                setup_console()
                mock_getwriter.assert_called()

def test_setup_console_other():
    # Test other platform
    with patch("sys.platform", "linux"):
        with patch("codecs.getwriter") as mock_getwriter:
            setup_console()
            mock_getwriter.assert_not_called()
