import os
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import asyncio


class RotatingLogger:
    """Rotating daily logger with 30-day retention"""

    def __init__(
        self, log_dir: str = "logs", max_days: int = 30, log_level: str = "INFO"
    ):
        self.log_dir = Path(log_dir)
        self.max_days = max_days
        self.log_level = log_level
        self.log_levels = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3, "CRITICAL": 4}
        self.current_level = self.log_levels.get(log_level, 1)
        self.current_date = datetime.now().date()
        self.current_file: Optional[Path] = None
        self.current_handle = None

        # Create log directory
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_file(self) -> Path:
        """Get today's log file"""
        today = datetime.now().date()
        if today != self.current_date:
            self.current_date = today
            if self.current_handle:
                self.current_handle.close()
                self.current_handle = None

        if not self.current_handle:
            self.current_file = self.log_dir / f"mtus_{today.isoformat()}.log"
            self.current_handle = open(self.current_file, "a", encoding="utf-8")

        return self.current_file

    def _cleanup_old_logs(self):
        """Delete logs older than max_days"""
        cutoff_date = datetime.now() - timedelta(days=self.max_days)

        for log_file in self.log_dir.glob("mtus_*.log"):
            try:
                # Extract date from filename
                date_str = log_file.stem.replace("mtus_", "")
                log_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                if log_date < cutoff_date.date():
                    log_file.unlink()
                    print(f"RotatingLogger: Deleted old log {log_file.name}")
            except Exception as e:
                pass  # Skip files that don't match pattern

    def log(self, level: str, message: str, **kwargs):
        """Log a message with structured data"""
        if self.log_levels.get(level, 1) < self.current_level:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }

        self._get_log_file() # Ensure handle is ready
        if self.current_handle:
            self.current_handle.write(json.dumps(log_entry) + "\n")
            self.current_handle.flush()

        # Also print to console for CRITICAL/ERROR
        if level in ("ERROR", "CRITICAL"):
            print(f"[{level}] {message}")

    def debug(self, message: str, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs):
        self.log("INFO", message, **kwargs)

    def warn(self, message: str, **kwargs):
        self.log("WARN", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs):
        self.log("CRITICAL", message, **kwargs)

    def close(self):
        """Close the current file handle"""
        if self.current_handle:
            self.current_handle.close()
            self.current_handle = None

    def run_cleanup(self):
        """Run cleanup of old logs"""
        self._cleanup_old_logs()


# Global logger instance
_logger: Optional[RotatingLogger] = None


def get_logger(
    log_dir: str = "logs", max_days: int = 30, log_level: str = "INFO"
) -> RotatingLogger:
    """Get or create the global logger instance"""
    global _logger
    if _logger is None:
        _logger = RotatingLogger(log_dir, max_days, log_level)
    return _logger
