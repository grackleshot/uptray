"""Pure tray helper logic that is safe to test without Qt installed."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

PACMAN_LOCAL_DB_DIR = Path("/var/lib/pacman/local")
PACMAN_DEBOUNCE_MS = 5000
OFFLINE_RETRY_MS = 60_000
RESUME_CHECK_DELAY_MS = 10_000


def is_snoozed(snooze_until: datetime | None, now: datetime | None = None) -> bool:
    """Return True when a snooze target exists and is still in the future."""
    return snooze_until is not None and (now or datetime.now()) < snooze_until


def snooze_label(snooze_until: datetime) -> str:
    """Format the tray status label for an active snooze."""
    return f"Snoozed until {snooze_until.strftime('%H:%M')}"


def pacman_watch_dir(base: Path = PACMAN_LOCAL_DB_DIR) -> Path | None:
    """Return the directory to watch for pacman database changes, if present."""
    return base if base.is_dir() else None


def remaining_ms(target: datetime, now: datetime | None = None) -> int:
    """Milliseconds remaining until a snooze target, clamped at zero."""
    remaining = target - (now or datetime.now())
    return max(0, int(remaining.total_seconds() * 1000))


def is_reboot_pending(updates_by_source: dict[str, int]) -> bool:
    """Return True when the reboot source reported pending items."""
    return updates_by_source.get("reboot", 0) > 0

