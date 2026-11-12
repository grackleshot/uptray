"""Helpers for reading topgrade.toml integration settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

TOPGRADE_STEP_MAP: dict[str, set[str]] = {
    "pacman": {"pacman"},
    "yay": {"aur"},
    "paru": {"aur"},
    "pikaur": {"aur"},
    "trizen": {"aur"},
    "flatpak": {"flatpak"},
    "linux": {"pacman", "aur"},
    "system": {"pacman", "aur"},
    "firmware": {"firmware"},
}

# topgrade `--only` step per checker source (not the inverse of the map above:
# topgrade 17.16 rejects names like "pacman"/"aur"; both live under "system").
ONLY_STEP_FOR_SOURCE: dict[str, str] = {
    "pacman": "system",
    "aur": "system",
    "flatpak": "flatpak",
    "firmware": "firmware",
}

# Checkers that mirror a topgrade step and therefore follow misc.only.
_STEP_BACKED_CHECKERS = {"pacman", "aur", "flatpak", "firmware"}


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


def _topgrade_d_dir() -> Path:
    return _xdg_config_home() / "topgrade.d"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load one TOML file, returning {} when missing or unparsable."""
    if not path.is_file():
        return {}
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

    with path.open("rb") as f:
        raw = tomllib.load(f)
    return raw if isinstance(raw, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base``; override values win."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_topgrade_config(path: Path | None = None) -> dict[str, Any]:
    """Load topgrade config; when no path is given, merge topgrade.d/ + main file.

    Mirrors topgrade itself: files in ``CONFIG_DIR/topgrade.d/`` are merged
    first and the main ``topgrade.toml`` takes priority.
    """
    if path is not None:
        return _load_toml(path)

    merged: dict[str, Any] = {}
    dropin_dir = _topgrade_d_dir()
    if dropin_dir.is_dir():
        for dropin in sorted(dropin_dir.glob("*.toml")):
            merged = _deep_merge(merged, _load_toml(dropin))

    main = find_topgrade_toml()
    if main is not None:
        merged = _deep_merge(merged, _load_toml(main))
    return merged


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


def get_only_steps(config: dict[str, Any]) -> set[str] | None:
    """Return the ``misc.only`` step restriction, or None when unrestricted."""
    misc = config.get("misc")
    if not isinstance(misc, dict):
        return None
    only = misc.get("only")
    if not isinstance(only, list) or not only:
        return None
    return {value.lower() for value in only if isinstance(value, str)}


def map_disabled_checkers(disabled_topgrade_names: set[str]) -> set[str]:
    """Map topgrade disabled step/category names to topgrade-update checker names."""
    disabled: set[str] = set()
    for name in disabled_topgrade_names:
        disabled.update(TOPGRADE_STEP_MAP.get(name, set()))
    return disabled


def checkers_allowed_by_only(only_steps: set[str]) -> set[str]:
    """Map a ``misc.only`` restriction onto the checkers it still permits."""
    allowed: set[str] = set()
    for name in only_steps:
        allowed.update(TOPGRADE_STEP_MAP.get(name, set()))
    return allowed & _STEP_BACKED_CHECKERS


def only_restricted_checkers(only_steps: set[str]) -> set[str]:
    """Return step-backed checkers that ``misc.only`` excludes."""
    return _STEP_BACKED_CHECKERS - checkers_allowed_by_only(only_steps)
