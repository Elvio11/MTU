import pytest
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from src.python.shared.rotating_logger import RotatingLogger, get_logger

@pytest.fixture
def logger(tmp_path):
    log_dir = tmp_path / "logs"
    return RotatingLogger(str(log_dir), max_days=30, log_level="INFO")

def test_log_creation(logger):
    logger.info("Test message")
    today = datetime.now().date().isoformat()
    log_file = logger.log_dir / f"mtus_{today}.log"
    assert log_file.exists()
    
    content = log_file.read_text(encoding="utf-8")
    entry = json.loads(content.strip())
    assert entry["message"] == "Test message"
    assert entry["level"] == "INFO"

def test_log_level_filtering(logger):
    logger.debug("Debug message") # Should not be logged (level is INFO)
    today = datetime.now().date().isoformat()
    log_file = logger.log_dir / f"mtus_{today}.log"
    assert not log_file.exists()

def test_log_append(logger):
    logger.info("Msg 1")
    logger.info("Msg 2")
    
    today = datetime.now().date().isoformat()
    log_file = logger.log_dir / f"mtus_{today}.log"
    lines = log_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert "Msg 1" in lines[0]
    assert "Msg 2" in lines[1]

def test_cleanup_old_logs(logger):
    # Create an old log file
    old_date = (datetime.now() - timedelta(days=40)).date().isoformat()
    old_file = logger.log_dir / f"mtus_{old_date}.log"
    old_file.write_text("old data")
    
    assert old_file.exists()
    logger.run_cleanup()
    assert not old_file.exists()

def test_get_logger():
    l1 = get_logger(log_level="DEBUG")
    l2 = get_logger()
    assert l1 is l2
