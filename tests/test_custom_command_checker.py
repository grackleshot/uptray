"""Tests for the custom command checker."""

from __future__ import annotations

from unittest.mock import patch

from topgrade_update.core.checkers.builtins import CustomCommandChecker


def test_custom_checker_has_unique_names() -> None:
    """Each instance should have a unique name without mutating ClassVar."""
    checker1 = CustomCommandChecker(["script1"], "MyChecker")
    checker2 = CustomCommandChecker(["script2"], "OtherChecker")

    # Each instance should have its own name
    assert checker1.name == "custom_mychecker"
    assert checker2.name == "custom_otherchecker"
    assert checker1.name != checker2.name


def test_custom_checker_default_name() -> None:
    checker = CustomCommandChecker(["script"])
    assert checker.name == "custom_custom"


def test_custom_checker_is_available() -> None:
    with patch("shutil.which", return_value="/usr/bin/echo"):
        checker = CustomCommandChecker(["echo", "--version"])
        assert checker.is_available() is True


def test_custom_checker_not_available() -> None:
    with patch("shutil.which", return_value=None):
        checker = CustomCommandChecker(["nonexistent-cmd"])
        assert checker.is_available() is False


def test_custom_checker_returns_empty_on_error() -> None:
    checker = CustomCommandChecker(["false"])
    # Should not raise, just return empty
    result = checker.check()
    assert result == []
