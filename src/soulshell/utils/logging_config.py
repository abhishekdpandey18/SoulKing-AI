"""
Logging setup for SoulShell Terminal.
Writes debug/diagnostic logs to the user's local data directory without exposing secrets.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from soulshell.core.config import get_default_data_dir


def setup_logging(
    log_level: str = "INFO", data_dir: Optional[Path] = None
) -> logging.Logger:
    """Configure rotating file logger for SoulShell Terminal."""
    target_dir = data_dir or get_default_data_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "soulshell.log"

    level = getattr(logging, (log_level or "INFO").upper(), logging.INFO)
    logger = logging.getLogger("soulshell")
    logger.setLevel(level)

    if not logger.handlers:
        try:
            handler = RotatingFileHandler(
                log_file, maxBytes=1_048_576, backupCount=2, encoding="utf-8"
            )
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        except OSError:
            logger.addHandler(logging.NullHandler())

    return logger
