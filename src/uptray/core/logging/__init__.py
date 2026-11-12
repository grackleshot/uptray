"""Logging configuration for Uptray.

Provides rotating file logging and optional console output.
Configured via LOG_DIR env var or defaults to ~/.local/share/uptray/.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

__all__ = ["RotatingFileHandler", "get_logger", "setup_logging"]

_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
_LOG_DIR = Path(os.environ.get("LOG_DIR") or _DATA_HOME / "uptray")
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    *,
    verbose: bool = False,
) -> None:
    """Configure the root logger with file and optional console handlers.

    Args:
        level: Base log level for the root logger.
        verbose: If True, also emit DEBUG to stderr.
    """
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("uptray")
    root.setLevel(logging.DEBUG)

    # Close old handlers as well as removing them to avoid leaking file handles.
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()

    # Rotating file handler — captures everything at the base level
    file_handler = RotatingFileHandler(
        _LOG_DIR / "log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt=_DATE_FMT,
    ))
    root.addHandler(file_handler)

    # Console handler — only when verbose
    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s %(filename)s:%(lineno)d: %(message)s",
            datefmt=_DATE_FMT,
        ))
        root.addHandler(console)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger under the uptray namespace."""
    return logging.getLogger(f"uptray.{name}")
