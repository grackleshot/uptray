"""Upgrade-session history parsed from /var/log/pacman.log."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_PATH = Path("/var/log/pacman.log")
_MAX_SESSIONS = 30
_TAIL_BYTES = 512 * 1024  # last 512 KiB is plenty for dozens of sessions

_LINE_RE = re.compile(r"^\[(?P<ts>[^\]]+)\] \[ALPM\] (?P<body>.*)$")
_UPGRADED_RE = re.compile(r"^upgraded (?P<name>\S+) \((?P<old>\S+) -> (?P<new>\S+)\)$")
_INSTALLED_RE = re.compile(r"^installed (?P<name>\S+) \((?P<version>\S+)\)$")
_REMOVED_RE = re.compile(r"^removed (?P<name>\S+) \((?P<version>\S+)\)$")


@dataclass(frozen=True)
class PackageChange:
    """One package transition inside an upgrade session."""

    action: str  # "upgraded" | "installed" | "removed"
    name: str
    old_version: str
    new_version: str


@dataclass(frozen=True)
class UpgradeSession:
    """One ALPM transaction as recorded in pacman.log."""

    started: datetime
    finished: datetime | None
    changes: list[PackageChange] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        """Count changes by action."""
        counts = {"upgraded": 0, "installed": 0, "removed": 0}
        for change in self.changes:
            counts[change.action] += 1
        return counts


def parse_pacman_log(
    path: Path | None = None,
    *,
    max_sessions: int = _MAX_SESSIONS,
) -> list[UpgradeSession]:
    """Return the most recent upgrade sessions, oldest first.

    Sessions are delimited by ALPM ``transaction started`` / ``transaction
    completed`` markers; only sessions with at least one package change are
    returned. Unparsable lines are skipped, and a missing log yields [].
    """
    log_path = path or DEFAULT_LOG_PATH
    try:
        text = _read_tail(log_path)
    except OSError:
        return []

    sessions: list[UpgradeSession] = []
    current: UpgradeSession | None = None

    for line in text.splitlines():
        match = _LINE_RE.match(line)
        if match is None:
            continue
        timestamp = _parse_timestamp(match.group("ts"))
        if timestamp is None:
            continue
        body = match.group("body")

        if body == "transaction started":
            current = UpgradeSession(started=timestamp, finished=None, changes=[])
            continue
        if current is None:
            continue
        if body == "transaction completed":
            current = UpgradeSession(
                started=current.started,
                finished=timestamp,
                changes=current.changes,
            )
            if current.changes:
                sessions.append(current)
            current = None
            continue

        change = _parse_change(body)
        if change is not None:
            current = UpgradeSession(
                started=current.started,
                finished=current.finished,
                changes=[*current.changes, change],
            )

    if max_sessions > 0 and len(sessions) > max_sessions:
        sessions = sessions[-max_sessions:]
    return sessions


def _read_tail(path: Path) -> str:
    """Read the last _TAIL_BYTES of the log to bound memory on old systems."""
    data = path.read_bytes()
    if len(data) > _TAIL_BYTES:
        data = data[-_TAIL_BYTES:]
        newline = data.find(b"\n")
        data = data[newline + 1 :] if newline != -1 else data
    return data.decode("utf-8", errors="replace")


def _parse_timestamp(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def _parse_change(body: str) -> PackageChange | None:
    upgraded = _UPGRADED_RE.match(body)
    if upgraded:
        return PackageChange(
            action="upgraded",
            name=upgraded.group("name"),
            old_version=upgraded.group("old"),
            new_version=upgraded.group("new"),
        )
    installed = _INSTALLED_RE.match(body)
    if installed:
        return PackageChange(
            action="installed",
            name=installed.group("name"),
            old_version="",
            new_version=installed.group("version"),
        )
    removed = _REMOVED_RE.match(body)
    if removed:
        return PackageChange(
            action="removed",
            name=removed.group("name"),
            old_version=removed.group("version"),
            new_version="",
        )
    return None
