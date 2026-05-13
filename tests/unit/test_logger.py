import pytest
from unittest.mock import patch, mock_open, MagicMock
import json
import logging
from src.python.shared.logger import StructuredLogger
from src.python.shared.logging_config import get_logger as get_mtus_logger, MTUSLogger

def test_structured_logger_init():
    logger = StructuredLogger("test_agent", "test.json")
    assert logger.agent_id == "test_agent"
    assert logger.log_file == "test.json"

def test_structured_logger_log():
    logger = StructuredLogger("test_agent", "test.json")
    
    with patch("builtins.open", mock_open()) as m:
        logger.info("test_event", key="value")
        
        # Check if file was opened correctly
        m.assert_called_with("test.json", "a")
        
        # Check if log entry is valid JSON
        handle = m()
        written_data = "".join(call.args[0] for call in handle.write.call_args_list)
        log_entry = json.loads(written_data.strip())
        
        assert log_entry["level"] == "INFO"
        assert log_entry["agent"] == "test_agent"
        assert log_entry["event"] == "test_event"
        assert log_entry["key"] == "value"
        assert "timestamp_utc" in log_entry

def test_structured_logger_error_notification():
    logger = StructuredLogger("test_agent", "test.json")
    
    with patch.object(logger, "notify_telegram") as mock_notify:
        with patch("builtins.open", mock_open()):
            logger.error("error_event")
            mock_notify.assert_called_once()
            
def test_structured_logger_levels():
    logger = StructuredLogger("test_agent", "test.json")
    with patch.object(logger, "log") as mock_log:
        logger.debug("d")
        mock_log.assert_called_with("DEBUG", "d")
        
        logger.warn("w")
        mock_log.assert_called_with("WARN", "w")
        
        logger.critical("c")
        mock_log.assert_called_with("CRITICAL", "c")

def test_mtus_logger_singleton():
    logger1 = get_mtus_logger("test_agent_2")
    logger2 = get_mtus_logger("test_agent_2")
    assert logger1 is logger2

def test_mtus_logger_setup():
    # Clear cache for fresh test
    MTUSLogger._loggers = {}
    with patch("os.makedirs") as mock_makedirs:
        with patch("src.python.shared.logging_config.RotatingFileHandler") as mock_handler:
            logger = MTUSLogger.get_logger("new_agent")
            mock_makedirs.assert_called_with("logs", exist_ok=True)
            assert logger.name == "new_agent"
            assert len(logger.handlers) > 0
