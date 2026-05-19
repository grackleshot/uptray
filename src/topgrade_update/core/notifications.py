"""Desktop notification handling."""

from __future__ import annotations

import contextlib
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"
ICON_NAME = "topgrade-update"


def _format_body(results: list[CheckResult]) -> str:
    """Format check results into a notification body."""
    parts: list[str] = []
    for r in results:
        if r.updates:
            parts.append(f"  {r.source}: {len(r.updates)}")
    return "\n".join(parts)


def send_notification(results: list[CheckResult]) -> None:
    """Send a desktop notification summarising available updates.

    Args:
        results: List of check results from all sources.
    """
    total = sum(len(r.updates) for r in results)
    if total == 0:
        return

    summary = f"{total} update(s) available"
    body = _format_body(results)

    with contextlib.suppress(FileNotFoundError):
        subprocess.Popen(
            [
                "notify-send",
                "-a", APP_NAME,
                "-i", ICON_NAME,
                summary,
                body,
            ]
        )
