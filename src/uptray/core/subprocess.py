"""Robust subprocess execution with process-group cleanup."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from subprocess import CompletedProcess

_DEFAULT_TIMEOUT = 30


def run_checked(
    cmd: list[str],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    capture_output: bool = True,
    text: bool = True,
) -> CompletedProcess[str]:
    """Run a command with timeout, killing the entire process group on expiry.

    Starts a new session for each command, then signals its process group on
    timeout so child processes (such as AUR build helpers) are cleaned up too.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as timeout_error:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise timeout_error
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
