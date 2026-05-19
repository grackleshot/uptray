"""Update checkers for pacman, AUR, and flatpak."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import TYPE_CHECKING

from topgrade_update.core.models import CheckResult, Config, SourceConfig, Update

if TYPE_CHECKING:
    pass

_DEFAULT_TIMEOUT = 30


def _run(cmd: list[str], timeout: int = _DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a command with timeout, capturing stdout/stderr as text."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_checkupdates_line(line: str, source: str) -> Update | None:
    """Parse a line from checkupdates or AUR helper output."""
    parts = line.strip().split()
    if len(parts) < 4:
        return None
    return Update(
        name=parts[0],
        old_version=parts[1],
        new_version=parts[3],
        source=source,
    )


def check_pacman() -> CheckResult:
    """Check for available pacman updates via checkupdates."""
    result = CheckResult(source="pacman")
    if not shutil.which("checkupdates"):
        result.error = "checkupdates not found"
        return result

    start = time.monotonic()
    try:
        r = _run(["checkupdates"])
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().splitlines():
                up = _parse_checkupdates_line(line, "pacman")
                if up:
                    result.updates.append(up)
    except subprocess.TimeoutExpired:
        result.error = "timed out"
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
    finally:
        result.duration_ms = int((time.monotonic() - start) * 1000)

    return result


def check_aur() -> CheckResult:
    """Check for available AUR updates via paru or yay."""
    result = CheckResult(source="AUR")
    for helper in ("paru", "yay"):
        if not shutil.which(helper):
            continue
        start = time.monotonic()
        try:
            r = _run([helper, "-Qua"])
            if r.returncode == 0 and r.stdout.strip():
                for line in r.stdout.strip().splitlines():
                    up = _parse_checkupdates_line(line, "AUR")
                    if up:
                        result.updates.append(up)
        except subprocess.TimeoutExpired:
            result.error = "timed out"
        except Exception as exc:  # noqa: BLE001
            result.error = str(exc)
        finally:
            result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    result.error = "no AUR helper found"
    return result


def check_flatpak() -> CheckResult:
    """Check for available flatpak updates."""
    result = CheckResult(source="flatpak")
    if not shutil.which("flatpak"):
        result.error = "flatpak not found"
        return result

    start = time.monotonic()
    try:
        r = _run(
            ["flatpak", "remote-ls", "--updates", "--columns=application,version,branch"]
        )
        if r.returncode == 0 and r.stdout.strip():
            for line in r.stdout.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    result.updates.append(
                        Update(
                            name=parts[0],
                            old_version="?",
                            new_version=parts[1],
                            source="flatpak",
                        )
                    )
    except subprocess.TimeoutExpired:
        result.error = "timed out"
    except Exception as exc:  # noqa: BLE001
        result.error = str(exc)
    finally:
        result.duration_ms = int((time.monotonic() - start) * 1000)

    return result


def check_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all enabled checkers and return results.

    Args:
        cfg: Configuration object. If None, all sources are checked.

    Returns:
        List of CheckResult, one per source attempted.
    """
    if cfg is None:
        cfg = Config()

    from collections.abc import Callable

    checkers: list[tuple[str, Callable[[], CheckResult]]] = [
        ("pacman", check_pacman),
        ("AUR", check_aur),
        ("flatpak", check_flatpak),
    ]

    results: list[CheckResult] = []
    for name, fn in checkers:
        src_cfg = cfg.sources.get(name, SourceConfig())
        if not src_cfg.enabled:
            continue
        results.append(fn())

    return results


def total_updates(results: list[CheckResult]) -> int:
    """Return the total number of available updates across all results."""
    return sum(len(r.updates) for r in results)


def find_terminal(cfg: Config | None = None) -> tuple[str | None, list[str]]:
    """Return (cmd, args_template) for the first available terminal.

    Args:
        cfg: Configuration with terminal priority list.

    Returns:
        Tuple of (terminal command or None, argument template).
    """
    if cfg is None:
        cfg = Config()

    # Try xdg-terminal-exec first (freedesktop standard)
    if shutil.which("xdg-terminal-exec"):
        return "xdg-terminal-exec", []

    # Try $TERMINAL env var
    env_term = shutil.which(os.environ.get("TERMINAL", ""))
    if env_term:
        return env_term, ["-e"]

    # Fallback to configured priority list
    for cmd in cfg.terminals:
        path = shutil.which(cmd)
        if path:
            return path, ["-e"]

    return None, []
