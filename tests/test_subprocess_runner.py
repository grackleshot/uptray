"""Tests for the real (unmocked) behavior of run_checked."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from uptray.core.subprocess import run_checked


def test_run_checked_echo_returns_zero_and_captures_stdout() -> None:
    """A fast command completes normally and its stdout is captured."""
    completed = run_checked(["echo", "hi"])

    assert completed.returncode == 0
    assert "hi" in completed.stdout


def test_run_checked_returns_nonzero_exit_code() -> None:
    """A failing command is reported via returncode instead of raising."""
    completed = run_checked(["sh", "-c", "exit 3"])

    assert completed.returncode == 3


def _pids_with_cmdline(*args: bytes) -> set[int]:
    """Return PIDs whose /proc cmdline matches *args exactly."""
    pids: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes()
        except OSError:
            continue  # process exited during the scan
        if cmdline.split(b"\0")[:-1] == list(args):
            pids.add(int(entry.name))
    return pids


@pytest.mark.skipif(not os.path.isdir("/proc"), reason="needs Linux /proc")
def test_run_checked_timeout_kills_child_and_reaps_it() -> None:
    """On timeout the whole process group is killed and the child is reaped."""
    before = _pids_with_cmdline(b"sleep", b"10")

    with pytest.raises(subprocess.TimeoutExpired):
        run_checked(["sleep", "10"], timeout=1)

    leftover = _pids_with_cmdline(b"sleep", b"10") - before
    assert not leftover, f"sleep child left running after timeout: {leftover}"
