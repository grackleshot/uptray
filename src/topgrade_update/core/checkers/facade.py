"""Update checker facade — delegates to UpdateEngine."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from topgrade_update.core.engine import UpdateEngine

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult, Config


def _get_engine() -> UpdateEngine:
    """Return a fully-initialized UpdateEngine."""
    engine = UpdateEngine()
    engine.discover_builtin()
    engine.discover_entry_points()
    return engine


def check_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all enabled checkers and return results."""
    return _get_engine().check_all(cfg)


def total_updates(results: list[CheckResult]) -> int:
    """Return the total number of available updates across all results."""
    return sum(len(r.updates) for r in results)


def find_terminal(cfg: Config | None = None) -> tuple[str | None, list[str]]:
    """Return (cmd, args_template) for the first available terminal."""
    from topgrade_update.core.models import Config

    if cfg is None:
        cfg = Config()
    if shutil.which("xdg-terminal-exec"):
        return "xdg-terminal-exec", []
    env_term = shutil.which(os.environ.get("TERMINAL", ""))
    if env_term:
        return env_term, ["-e"]
    for cmd in cfg.terminals:
        path = shutil.which(cmd)
        if path:
            return path, ["-e"]
    return None, []
