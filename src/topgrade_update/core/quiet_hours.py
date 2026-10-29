"""Quiet-hours time-window helpers."""

from __future__ import annotations

from datetime import datetime


def is_quiet_hours(
    start: int | None,
    end: int | None,
    now: datetime | None = None,
) -> bool:
    """Return True if current time is inside the configured quiet-hours window.

    Handles normal windows (9 -> 17) and wrap-around windows (23 -> 8).
    A start equal to end is treated as quiet-hours disabled.
    """
    if start is None or end is None or start == end:
        return False
    hour = (now or datetime.now()).hour
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end
