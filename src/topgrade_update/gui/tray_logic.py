"""Pure tray helper logic that is safe to test without Qt installed."""

from __future__ import annotations

from datetime import datetime


def is_snoozed(snooze_until: datetime | None, now: datetime | None = None) -> bool:
    """Return True when a snooze target exists and is still in the future."""
    return snooze_until is not None and (now or datetime.now()) < snooze_until


def snooze_label(snooze_until: datetime) -> str:
    """Format the tray status label for an active snooze."""
    return f"Snoozed until {snooze_until.strftime('%H:%M')}"
