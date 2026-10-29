"""Helpers for reading topgrade.toml integration settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

TOPGRADE_STEP_MAP: dict[str, set[str]] = {
    "pacman": {"pacman"},
    "yay": {"aur"},
    "paru": {"aur"},
    "flatpak": {"flatpak"},
    "linux": {"pacman", "aur"},
    "system": {"pacman", "aur"},
    "firmware": {"firmware"},
}


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def find_topgrade_toml() -> Path | None:
    """Find topgrade.toml in standard locations."""
    paths = [
        _xdg_config_home() / "topgrade.toml",
        _xdg_config_home() / "topgrade" / "topgrade.toml",
        Path.home() / ".topgrade.toml",
    ]
    for path in paths:
        if path.exists():
            return path
    return None


def load_topgrade_config(path: Path | None = None) -> dict[str, Any]:
    """Load topgrade.toml and return parsed dict."""
    if path is None:
        path = find_topgrade_toml()
    if path is None or not path.exists():
        return {}

    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

    with path.open("rb") as f:
        raw = tomllib.load(f)
    return raw if isinstance(raw, dict) else {}


def get_disabled_steps(config: dict[str, Any]) -> set[str]:
    """Extract disabled steps from Topgrade's ``misc.disable`` list.

    Also accepts the earlier boolean formats for compatibility with configs
    written against the first Topgrade Update release.
    """
    disabled = {
        key.lower()
        for key, value in config.items()
        if not isinstance(value, dict) and value is False
    }
    misc = config.get("misc")
    if isinstance(misc, dict):
        raw_disabled = misc.get("disable", [])
        if isinstance(raw_disabled, list):
            disabled.update(
                value.lower()
                for value in raw_disabled
                if isinstance(value, str)
            )
    return disabled


def get_disabled_categories(config: dict[str, Any]) -> set[str]:
    """Extract disabled category names from topgrade config."""
    return {
        key.lower()
        for key, value in config.items()
        if isinstance(value, dict) and value.get("disabled") is True
    }


def map_disabled_checkers(disabled_topgrade_names: set[str]) -> set[str]:
    """Map topgrade disabled step/category names to topgrade-update checker names."""
    disabled: set[str] = set()
    for name in disabled_topgrade_names:
        disabled.update(TOPGRADE_STEP_MAP.get(name, set()))
    return disabled
