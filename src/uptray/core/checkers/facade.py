"""Update checker facade — delegates to UpdateEngine."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from uptray.core.engine import UpdateEngine
from uptray.core.logging import get_logger
from uptray.core.topgrade_config import (
    find_topgrade_toml,
    get_disabled_categories,
    get_disabled_steps,
    get_only_steps,
    load_topgrade_config,
    map_disabled_checkers,
    only_restricted_checkers,
)

if TYPE_CHECKING:
    from uptray.core.models import CheckResult, Config


def _get_engine() -> UpdateEngine:
    """Return a fully-initialized UpdateEngine."""
    engine = UpdateEngine()
    engine.discover_builtin()
    engine.discover_entry_points()
    return engine


def _get_topgrade_disabled_checkers() -> set[str]:
    """Return checker names disabled by topgrade.toml."""
    path = find_topgrade_toml()
    if path is None:
        return set()

    try:
        topgrade_cfg = load_topgrade_config(path)
    except (OSError, ValueError) as exc:
        get_logger("checkers").warning("Could not read Topgrade config %s: %s", path, exc)
        return set()
    disabled_topgrade_names = get_disabled_steps(topgrade_cfg) | get_disabled_categories(
        topgrade_cfg
    )
    disabled = map_disabled_checkers(disabled_topgrade_names)

    # When topgrade is restricted to specific steps (misc.only), every other
    # step-backed checker is skipped too.
    only_steps = get_only_steps(topgrade_cfg)
    if only_steps is not None:
        disabled |= only_restricted_checkers(only_steps)
    return disabled


def check_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all enabled checkers and return results."""
    topgrade_disabled = _get_topgrade_disabled_checkers()
    return _get_engine().check_all(cfg, topgrade_disabled=topgrade_disabled)


def total_updates(results: list[CheckResult]) -> int:
    """Return the number of available package updates (a pending reboot is not one)."""
    return sum(len(r.updates) for r in results if r.source != "reboot")


def find_terminal(cfg: Config | None = None) -> tuple[str | None, list[str]]:
    """Return (cmd, args_template) for the first available terminal."""
    from uptray.core.models import Config

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
