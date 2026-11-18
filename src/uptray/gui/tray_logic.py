"""Pure tray helper logic that is safe to test without Qt installed."""

from __future__ import annotations

import contextlib
import errno
import fcntl
import os
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import IO, TYPE_CHECKING
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from uptray.core.logging import get_logger
from uptray.core.topgrade_session import private_runtime_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from threading import Event

PACMAN_LOCAL_DB_DIR = Path("/var/lib/pacman/local")
PACMAN_DEBOUNCE_MS = 5000
OFFLINE_RETRY_MS = 60_000
RESUME_CHECK_DELAY_MS = 10_000


def local_zone() -> tzinfo:
    """Return the system zone, including its daylight-saving rules when known.

    ``datetime.now().astimezone()`` only carries today's fixed offset. Using
    that offset for tomorrow's midnight is an hour off on a transition day.
    """
    configured = os.environ.get("TZ")
    if configured:
        key = configured[1:] if configured.startswith(":") else configured
        with contextlib.suppress(ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(key)
    try:
        target = Path("/etc/localtime").resolve()
    except OSError:
        target = None
    root = Path("/usr/share/zoneinfo")
    if target is not None and root in target.parents:
        with contextlib.suppress(ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(target.relative_to(root).as_posix())
    return datetime.now().astimezone().tzinfo or timezone.utc


def local_now() -> datetime:
    """Return the current local time with its timezone attached."""
    return datetime.now(local_zone())


def as_local(value: datetime) -> datetime:
    """Interpret a naive timestamp as local time and convert to that zone."""
    zone = local_zone()
    if value.tzinfo is None:
        return value.replace(tzinfo=zone)
    return value.astimezone(zone)


def next_local_midnight(now: datetime | None = None) -> datetime:
    """Return the next local midnight after ``now``."""
    current = as_local(now) if now is not None else local_now()
    tomorrow = current.date() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=current.tzinfo)


def is_snoozed(snooze_until: datetime | None, now: datetime | None = None) -> bool:
    """Return True when a snooze target exists and is still in the future."""
    if snooze_until is None:
        return False
    current = as_local(now) if now is not None else local_now()
    return current < as_local(snooze_until)


def snooze_label(snooze_until: datetime, now: datetime | None = None) -> str:
    """Format the tray status label for an active snooze."""
    current = as_local(now) if now is not None else local_now()
    target = as_local(snooze_until)
    clock = target.strftime("%H:%M")
    if target.date() == current.date():
        return f"Snoozed until {clock}"
    return f"Snoozed until {target.strftime('%Y-%m-%d')} {clock}"


def pacman_watch_dir(base: Path = PACMAN_LOCAL_DB_DIR) -> Path | None:
    """Return the directory to watch for pacman database changes, if present."""
    return base if base.is_dir() else None


def remaining_ms(target: datetime, now: datetime | None = None) -> int:
    """Milliseconds remaining until a snooze target, clamped at zero."""
    current = as_local(now) if now is not None else local_now()
    remaining = as_local(target) - current
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
        lock_path = runtime / "uptray.lock"
    else:
        # Not a predictable /tmp path, which another user could create to block us.
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        lock_path = cache / "uptray" / "tray.lock"
    handle: IO[str] | None = None
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        # O_RDWR keeps the current PID until this process holds the lock.
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        handle = os.fdopen(fd, "r+")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        os.fchmod(fd, 0o600)
    except OSError as exc:
        if handle is not None:
            handle.close()
        contended = isinstance(exc, BlockingIOError) or exc.errno in {
            errno.EAGAIN,
            errno.EWOULDBLOCK,
        }
        if contended:
            return None
        raise
    handle.seek(0)
    handle.truncate(0)
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle
