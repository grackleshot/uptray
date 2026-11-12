"""Post-update maintenance detection: orphans, pacnew files, package cache."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from uptray.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from subprocess import CompletedProcess

    Runner = Callable[..., CompletedProcess[str]]

CACHE_WARN_BYTES = 2 * 1024**3  # 2 GiB
_MAX_CONFIG_FILES = 100

KIND_ORPHANS = "orphans"
KIND_PACNEW = "pacnew"
KIND_CACHE = "cache"


@dataclass(frozen=True)
class MaintenanceFinding:
    """One actionable post-update maintenance item."""

    kind: str
    summary: str
    detail: list[str] = field(default_factory=list)


def find_orphans(runner: Runner | None = None) -> list[str]:
    """Return orphan package names via ``pacman -Qdtq`` (empty when none)."""
    if shutil.which("pacman") is None:
        return []
    from uptray.core.subprocess import run_checked

    probe = runner or run_checked
    try:
        result = probe(["pacman", "-Qdtq"])
    except Exception:
        return []
    if result.returncode != 0:  # exit 1 means "no orphans"
        return []
    return [line for line in (result.stdout or "").split() if line]


def find_unmerged_config_files(root: Path | None = None) -> list[str]:
    """Return relative paths of *.pacnew / *.pacsave files under /etc."""
    base = root or Path("/etc")
    found: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(base, onerror=lambda _error: None):
        for filename in filenames:
            if filename.endswith((".pacnew", ".pacsave")):
                path = Path(dirpath) / filename
                found.append(str(path.relative_to(base)))
                if len(found) >= _MAX_CONFIG_FILES:
                    found.sort()
                    return found
    found.sort()
    return found


def cache_usage(path: Path | None = None) -> int:
    """Return the total byte size of the pacman package cache."""
    cache_dir = path or Path("/var/cache/pacman/pkg")
    total = 0
    try:
        for entry in cache_dir.iterdir():
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0
    return total


def maintenance_summary(
    *,
    orphans: list[str] | None = None,
    config_files: list[str] | None = None,
    cache_bytes: int | None = None,
    runner: Runner | None = None,
    etc_root: Path | None = None,
    cache_dir: Path | None = None,
) -> list[MaintenanceFinding]:
    """Collect post-update maintenance findings.

    All inputs are injectable so callers can pre-compute or fake them; any
    omitted input is detected live. Detection failures never raise.
    """
    findings: list[MaintenanceFinding] = []

    if orphans is None:
        orphans = find_orphans(runner)
    if orphans:
        findings.append(
            MaintenanceFinding(
                kind=KIND_ORPHANS,
                summary=f"{len(orphans)} orphan package(s) installed",
                detail=orphans[:20],
            )
        )

    if config_files is None:
        config_files = find_unmerged_config_files(etc_root)
    if config_files:
        findings.append(
            MaintenanceFinding(
                kind=KIND_PACNEW,
                summary=f"{len(config_files)} unmerged .pacnew/.pacsave file(s)",
                detail=config_files[:20],
            )
        )

    if cache_bytes is None:
        cache_bytes = cache_usage(cache_dir)
    if cache_bytes > CACHE_WARN_BYTES:
        gib = cache_bytes / 1024**3
        findings.append(
            MaintenanceFinding(
                kind=KIND_CACHE,
                summary=f"Package cache is {gib:.1f} GiB (paccache can trim it)",
            )
        )

    if findings:
        get_logger("maintenance").info("Maintenance findings: %s", [f.kind for f in findings])
    return findings
