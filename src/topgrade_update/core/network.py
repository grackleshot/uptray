"""Network connectivity probing so update checks can be skipped while offline."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from subprocess import CompletedProcess

    Runner = Callable[..., CompletedProcess[str]]

_OFFLINE_STATES = {"none", "limited", "portal"}


def is_online(runner: Runner | None = None) -> bool:
    """Return True unless NetworkManager clearly reports no internet access.

    Falls open (True) whenever connectivity cannot be determined: when
    NetworkManager is absent, when the probe fails, or when it reports an
    unknown state. This keeps checks working on networkd-only systems.
    """
    from topgrade_update.core.subprocess import run_checked

    nmcli = shutil.which("nmcli")
    if nmcli is None:
        return True

    probe = runner or run_checked
    try:
        result = probe([nmcli, "networking", "connectivity"], timeout=10)
    except Exception:
        return True
    if result.returncode != 0:
        return True
    state = (result.stdout or "").strip().lower()
    if not state:
        return True
    return state not in _OFFLINE_STATES
