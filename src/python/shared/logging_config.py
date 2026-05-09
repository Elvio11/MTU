"""
MTUS Logging Configuration
Provides structured logging across all agents
"""

import os
import json
from datetime import datetime
from typing import Optional
import logging
from logging.handlers import RotatingFileHandler


class MTUSLogger:
    """Centralized logger for all MTUS agents"""

    _loggers = {}
    _log_dir = "logs"

    @classmethod
    def get_logger(cls, agent_id: str) -> logging.Logger:
        """Get or create logger for an agent"""
        if agent_id in cls._loggers:
            return cls._loggers[agent_id]

        logger = logging.getLogger(agent_id)
        logger.setLevel(logging.DEBUG)

        os.makedirs(cls._log_dir, exist_ok=True)

        log_file = os.path.join(
            cls._log_dir,
            f"{agent_id.lower()}-{datetime.now().strftime('%Y-%m-%d')}.log",
        )

        file_handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
        file_handler.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        cls._loggers[agent_id] = logger
        return logger


def get_logger(agent_id: str) -> logging.Logger:
    """Shortcut function"""
    return MTUSLogger.get_logger(agent_id)
