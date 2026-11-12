"""Tests for the one-time move from the old topgrade-update name."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import uptray.core.autostart as autostart
from uptray.core.migrate import migrate_from_old_name


def _base(var: str) -> Path:
    return Path(os.environ[var])


def test_moves_old_folders_and_keeps_their_contents() -> None:
    old_config = _base("XDG_CONFIG_HOME") / "topgrade-update"
    old_config.mkdir(parents=True)
    (old_config / "config.toml").write_text("run_mode = 'simple'\n")
    old_runs = _base("XDG_DATA_HOME") / "topgrade-update" / "runs"
    old_runs.mkdir(parents=True)

    moved = migrate_from_old_name()

    assert (_base("XDG_CONFIG_HOME") / "uptray" / "config.toml").read_text() == (
        "run_mode = 'simple'\n"
    )
    assert (_base("XDG_DATA_HOME") / "uptray" / "runs").is_dir()
    assert not old_config.exists()
    assert len(moved) == 2


def test_never_overwrites_an_existing_new_folder() -> None:
    old = _base("XDG_CONFIG_HOME") / "topgrade-update"
    old.mkdir(parents=True)
    new = _base("XDG_CONFIG_HOME") / "uptray"
    new.mkdir(parents=True)

    assert migrate_from_old_name() == []
    assert old.is_dir()


def test_replaces_an_enabled_old_autostart_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    autostart_dir = _base("XDG_CONFIG_HOME") / "autostart"
    autostart_dir.mkdir(parents=True)
    old_entry = autostart_dir / "topgrade-update-tray.desktop"
    old_entry.write_text("[Desktop Entry]\n")
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", autostart_dir)
    monkeypatch.setattr(autostart, "AUTOSTART_FILE", autostart_dir / "uptray.desktop")

    migrate_from_old_name()

    assert not old_entry.exists()
    assert (autostart_dir / "uptray.desktop").is_file()


def test_keeps_remembered_window_sizes() -> None:
    old_config = _base("XDG_CONFIG_HOME") / "topgrade-update"
    old_config.mkdir(parents=True)
    (old_config / "topgrade-update.conf").write_text("[run_window]\n")

    migrate_from_old_name()

    assert (_base("XDG_CONFIG_HOME") / "uptray" / "uptray.conf").read_text() == "[run_window]\n"
