"""Tests for the logging configuration module."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from uptray.core.logging import RotatingFileHandler, get_logger


@pytest.fixture(autouse=True)
def _reset_logger():
    """Close and clear root logger handlers before and after each test."""
    root = logging.getLogger("uptray")
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()


def test_get_logger_returns_correct_name() -> None:
    logger = get_logger("engine")
    assert logger.name == "uptray.engine"


def test_get_logger_nested_name() -> None:
    logger = get_logger("cli.main")
    assert logger.name == "uptray.cli.main"


def test_log_file_is_owner_readable_only(tmp_path: Path, monkeypatch: object) -> None:
    import stat

    import uptray.core.logging as log_mod

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    existing = log_dir / "log"
    existing.write_text("old\n", encoding="utf-8")
    existing.chmod(0o644)
    rotated = log_dir / "log.1"
    rotated.write_text("older\n", encoding="utf-8")
    rotated.chmod(0o644)
    monkeypatch.setattr(log_mod, "_LOG_DIR", log_dir)

    log_mod.setup_logging()
    get_logger("engine").info("hello")

    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(existing.stat().st_mode) == 0o600
    assert stat.S_IMODE(rotated.stat().st_mode) == 0o600


def test_setup_creates_log_dir(tmp_path: Path, monkeypatch: object) -> None:
    """setup_logging creates the log directory if it doesn't exist."""
    log_dir = tmp_path / "logs"
    import uptray.core.logging as log_mod

    monkeypatch.setattr(log_mod, "_LOG_DIR", log_dir)
    log_mod.setup_logging()
    assert log_dir.exists()


def test_verbose_adds_console_handler(tmp_path: Path, monkeypatch: object) -> None:
    """verbose=True adds a StreamHandler to stderr."""
    log_dir = tmp_path / "logs"
    import uptray.core.logging as log_mod

    monkeypatch.setattr(log_mod, "_LOG_DIR", log_dir)
    log_mod.setup_logging(verbose=True)
    root = logging.getLogger("uptray")
    has_console = any(
        isinstance(h, logging.StreamHandler)
        for h in root.handlers
    )
    assert has_console


def test_non_verbose_no_console_handler(tmp_path: Path, monkeypatch: object) -> None:
    """verbose=False only adds a file handler."""
    log_dir = tmp_path / "logs"
    import uptray.core.logging as log_mod

    monkeypatch.setattr(log_mod, "_LOG_DIR", log_dir)
    log_mod.setup_logging()
    root = logging.getLogger("uptray")
    # RotatingFileHandler is a StreamHandler subclass; exclude it
    plain_console = [
        h for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, RotatingFileHandler)
    ]
    assert len(plain_console) == 0


def test_setup_closes_existing_file_handler(tmp_path: Path, monkeypatch: object) -> None:
    """Reconfiguration closes the prior rotating log file descriptor."""
    log_dir = tmp_path / "logs"
    import uptray.core.logging as log_mod

    monkeypatch.setattr(log_mod, "_LOG_DIR", log_dir)
    log_mod.setup_logging()
    first_handler = logging.getLogger("uptray").handlers[0]
    assert first_handler.baseFilename == str(log_dir / "log")

    log_mod.setup_logging()

    assert first_handler.stream is None
