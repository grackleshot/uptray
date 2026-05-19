"""Robust subprocess execution with process-group cleanup."""

from __future__ import annotations

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

    Uses os.setsid to create a new process group, then os.killpg to kill
    all children (e.g. git, makepkg spawned by paru/yay) on TimeoutExpired.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        preexec_fn=os.setsid,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait()
        raise
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
