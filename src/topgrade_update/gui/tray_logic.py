"""Pure tray helper logic that is safe to test without Qt installed."""

from __future__ import annotations

import contextlib
import fcntl
import os
from datetime import datetime
from pathlib import Path
from typing import IO, TYPE_CHECKING

from topgrade_update.core.logging import get_logger
from topgrade_update.core.topgrade_session import private_runtime_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from threading import Event

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


def _watch_resume(emit: Callable[[], None], stop: Event) -> None:
    """Watch logind PrepareForSleep on the system bus and emit on wake.

    Runs in a daemon thread; failures are non-fatal (no resume detection).
    """
    try:
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus
        from jeepney.io.blocking import open_dbus_connection

        bus = open_dbus_connection(bus="SYSTEM")
    except Exception:
        return
    rule = MatchRule(
        type="signal",
        sender="org.freedesktop.login1",
        interface="org.freedesktop.login1.Manager",
        member="PrepareForSleep",
        path="/org/freedesktop/login1",
    )
    try:
        bus.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
        with bus.filter(rule) as matches:
            while not stop.is_set():
                try:
                    message = bus.recv_until_filtered(matches, timeout=0.25)
                except TimeoutError:
                    continue
                body = getattr(message, "body", ())
                if body and body[0] is False:  # False = resuming
                    emit()
    except Exception as exc:
        get_logger("tray").debug("Resume watcher stopped: %s", exc)
    finally:
        with contextlib.suppress(Exception):
            bus.close()


def _acquire_instance_lock() -> IO[str] | None:
    """Take an exclusive single-instance lock, or None when already held."""
    runtime = private_runtime_dir()
    if runtime is not None:
        lock_path = runtime / "topgrade-update.lock"
    else:
        # Not a predictable /tmp path, which another user could create to block us.
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        lock_path = cache / "topgrade-update" / "tray.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("w")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    handle.truncate(0)
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle
