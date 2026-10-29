"""Tests for reboot-required detection."""

from __future__ import annotations

from pathlib import Path

from topgrade_update.core.checkers.reboot import RebootRequiredChecker


def test_reboot_checker_no_reboot_required(tmp_path: Path, monkeypatch: object) -> None:
    """No reboot required when /run/reboot-required doesn't exist."""
    checker = RebootRequiredChecker()
    # Mock os.path.isdir to return False for /var/lib/pacman/local
    monkeypatch.setattr("os.path.isdir", lambda x: False)
    result = checker.check()
    assert result == []


def test_reboot_checker_debian_style(tmp_path: Path, monkeypatch: object) -> None:
    """Detect reboot required via /run/reboot-required."""
    reboot_file = tmp_path / "reboot-required"
    reboot_file.write_text("Some reason\n")

    def mock_open(path: str, *args: object, **kwargs: object) -> object:
        if path == "/run/reboot-required":
            return reboot_file.open(*args, **kwargs)
        raise FileNotFoundError(path)

    monkeypatch.setattr("builtins.open", mock_open)
    checker = RebootRequiredChecker()
    result = checker.check()
    assert len(result) == 1
    assert result[0].source == "reboot"
    assert "reboot required" in result[0].new_version
