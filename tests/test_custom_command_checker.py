"""Tests for the custom command checker."""

from __future__ import annotations

import logging
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from uptray.core.checkers.builtins import CustomCommandChecker, _command_error


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


def test_custom_checker_raises_on_command_error() -> None:
    """A failed custom checker must not masquerade as a successful empty check."""
    checker = CustomCommandChecker(["custom-command"])
    failed = CompletedProcess(
        args=["custom-command"], returncode=1, stdout="", stderr="permission denied"
    )

    with (
        patch("uptray.core.checkers.builtins.run_checked", return_value=failed),
        pytest.raises(RuntimeError, match="permission denied"),
    ):
        checker.check()


def test_custom_checker_accepts_empty_success() -> None:
    """A successful command with no output means there are no updates."""
    checker = CustomCommandChecker(["custom-command"])
    successful = CompletedProcess(
        args=["custom-command"], returncode=0, stdout="", stderr=""
    )

    with patch("uptray.core.checkers.builtins.run_checked", return_value=successful):
        assert checker.check() == []


def test_custom_checker_logs_unparsable_lines(caplog: pytest.LogCaptureFixture) -> None:
    checker = CustomCommandChecker(["custom-command"], "My Check")
    completed = CompletedProcess(
        args=["custom-command"],
        returncode=0,
        stdout="pkg 1.0 -> 2.0\noops\n",
        stderr="",
    )

    with (
        patch("uptray.core.checkers.builtins.run_checked", return_value=completed),
        caplog.at_level(logging.DEBUG, logger="uptray.checkers"),
    ):
        updates = checker.check()

    assert [update.name for update in updates] == ["pkg"]
    assert "oops" in caplog.text


def test_command_error_uses_stdout_when_stderr_is_empty() -> None:
    error = _command_error(["paru"], 1, "  ", "could not resolve host\n")

    assert "could not resolve host" in str(error)
    assert "exited with status" not in str(error)


def test_command_error_prefers_stderr() -> None:
    error = _command_error(["paru"], 1, "permission denied", "could not resolve host")

    assert "permission denied" in str(error)
    assert "could not resolve host" not in str(error)
