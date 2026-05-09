import json
import time
from datetime import datetime
from typing import Any, Dict


class StructuredLogger:
    """Structured JSON logger per Section 9.1"""

    def __init__(self, agent_id: str, log_file: str = None):
        self.agent_id = agent_id
        self.log_file = (
            log_file
            or f"logs/{agent_id.lower()}-{datetime.now().strftime('%Y-%m-%d')}.json"
        )
        self.setup_log_file()

    def setup_log_file(self):
        import os

        os.makedirs("logs", exist_ok=True)

    def log(self, level: str, event: str, **kwargs: Any):
        """Emit structured JSON log per Section 9.1"""
        log_entry = {
            "level": level,
            "agent": self.agent_id,
            "event": event,
            "timestamp_utc": datetime.utcnow().isoformat(),
            **kwargs,
        }

        # Write to file (rotating daily per Section 5.1)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

        # Console output
        print(f"[{level}] {self.agent_id}: {event} - {kwargs}")

        # CRITICAL/ERROR → Telegram alert (implemented in agent)
        if level in ["ERROR", "CRITICAL"]:
            self.notify_telegram(log_entry)

    def notify_telegram(self, log_entry: Dict):
        """Send CRITICAL/ERROR to Telegram per Section 9.1"""
        # This is called by the agent's Telegram integration
        pass  # Actual implementation in telegram_bot.py

    # Convenience methods
    def debug(self, event: str, **kwargs):
        self.log("DEBUG", event, **kwargs)

    def info(self, event: str, **kwargs):
        self.log("INFO", event, **kwargs)

    def warn(self, event: str, **kwargs):
        self.log("WARN", event, **kwargs)

    def error(self, event: str, **kwargs):
        self.log("ERROR", event, **kwargs)

    def critical(self, event: str, **kwargs):
        self.log("CRITICAL", event, **kwargs)
