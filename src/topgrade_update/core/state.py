"""Persistent application state stored under XDG_STATE_HOME.

Survives tray restarts so that snoozes, notification deduplication, and
read-news markers behave consistently across sessions instead of resetting
every launch.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_STR_FIELDS = (
    "snooze_until",
    "last_seen_news",
    "maintenance_check_date",
)


def _state_dir() -> Path:
    """Return the XDG state directory for topgrade-update."""
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")


def state_path() -> Path:
    """Return the default state-file path."""
    return _state_dir() / "topgrade-update" / "state.json"


@dataclass
class AppState:
    """Mutable runtime state worth persisting between runs."""

    snooze_until: str | None = None  # ISO 8601 datetime of the snooze target
    prev_total: int = -1  # Update count seen by the last notification decision
    last_seen_news: str | None = None  # ISO date of the newest read news item
    reboot_notified: bool = False  # Reboot notification already sent
    maintenance_check_date: str | None = None  # YYYY-MM-DD of last reminder


def load_state(path: Path | None = None) -> AppState:
    """Load persisted state; missing or corrupt files fall back to defaults."""
    if path is None:
        path = state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return AppState()
    if not isinstance(raw, dict):
        return AppState()

    state = AppState()
    for field_name in _STR_FIELDS:
        value = raw.get(field_name)
        if isinstance(value, str):
            setattr(state, field_name, value)
    prev_total = raw.get("prev_total")
    if isinstance(prev_total, int) and not isinstance(prev_total, bool):
        state.prev_total = prev_total
    reboot_notified = raw.get("reboot_notified")
    if isinstance(reboot_notified, bool):
        state.reboot_notified = reboot_notified
    return state


def save_state(state: AppState, path: Path | None = None) -> None:
    """Atomically persist state as JSON."""
    if path is None:
        path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Could not persist state to %s: %s", path, exc)


def parse_snooze(value: str | None) -> datetime | None:
    """Parse a persisted ISO snooze timestamp, returning None when invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_snooze(value: datetime | None) -> str | None:
    """Format a snooze target for persistence."""
    return value.isoformat() if value is not None else None
