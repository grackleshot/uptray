"""Tests for Flatpak update parsing."""

from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from topgrade_update.core.checkers.builtins import FlatpakChecker


def test_flatpak_checker_keeps_version_and_branch() -> None:
    """The Flatpak branch is retained for display and machine-readable output."""
    checker = FlatpakChecker()
    command = [
        "flatpak",
        "remote-ls",
        "--updates",
        "--columns=application,version,branch",
    ]
    completed = CompletedProcess(
        args=command,
        returncode=0,
        stdout="org.example.App\t2.0\tstable\n",
        stderr="",
    )

    with patch("topgrade_update.core.checkers.builtins.run_checked", return_value=completed):
        [update] = checker.check()

    assert update.name == "org.example.App"
    assert update.new_version == "2.0"
    assert update.branch == "stable"


def test_flatpak_checker_allows_missing_branch() -> None:
    """Older or incomplete Flatpak output remains parseable."""
    checker = FlatpakChecker()
    completed = CompletedProcess(
        args=["flatpak"], returncode=0, stdout="org.example.App\t2.0\n", stderr=""
    )

    with patch("topgrade_update.core.checkers.builtins.run_checked", return_value=completed):
        [update] = checker.check()

    assert update.branch is None
