"""Tests that built-in checkers are properly registered in the engine."""

from __future__ import annotations

from topgrade_update.core.engine import UpdateEngine


def test_all_builtin_checkers_registered() -> None:
    """Engine should discover all built-in checkers."""
    engine = UpdateEngine()
    engine.discover_builtin()

    registered_names = set(engine._checkers.keys())
    expected = {"pacman", "aur", "flatpak", "firmware", "reboot"}
    assert expected.issubset(registered_names), (
        f"Missing checkers: {expected - registered_names}"
    )


def test_reboot_checker_is_available() -> None:
    """Reboot checker should always be available."""
    engine = UpdateEngine()
    engine.discover_builtin()
    reboot = engine._checkers.get("reboot")
    assert reboot is not None
    assert reboot.is_available() is True
