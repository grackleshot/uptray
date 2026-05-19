"""Configuration loading and management."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from topgrade_update.core.models import Config, NotificationConfig, SourceConfig


def _xdg_config_home() -> Path:
    """Return the XDG config directory."""
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def default_config_path() -> Path:
    """Return the default configuration file path."""
    return _xdg_config_home() / "topgrade-update" / "config.toml"


def _merge_source_config(raw: dict[str, Any]) -> SourceConfig:
    """Build a SourceConfig from a raw dict."""
    return SourceConfig(enabled=raw.get("enabled", True))


def _merge_notification_config(raw: dict[str, Any]) -> NotificationConfig:
    """Build a NotificationConfig from a raw dict."""
    return NotificationConfig(
        enabled=raw.get("enabled", True),
        quiet_hours_start=raw.get("quiet_hours_start"),
        quiet_hours_end=raw.get("quiet_hours_end"),
    )


def load_config(path: Path | None = None) -> Config:
    """Load configuration from TOML file, falling back to defaults.

    Args:
        path: Explicit config file path. If None, uses the default XDG location.

    Returns:
        A Config instance merged from defaults and the file.
    """
    if path is None:
        path = default_config_path()

    cfg = Config()

    if not path.exists():
        return cfg

    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

    with path.open("rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    if "check_interval" in raw:
        cfg.check_interval = int(raw["check_interval"])

    if "terminals" in raw:
        cfg.terminals = list(raw["terminals"])

    if "sources" in raw and isinstance(raw["sources"], dict):
        for name, src_raw in raw["sources"].items():
            if isinstance(src_raw, dict):
                cfg.sources[name] = _merge_source_config(src_raw)

    if "notifications" in raw and isinstance(raw["notifications"], dict):
        cfg.notifications = _merge_notification_config(raw["notifications"])

    return cfg


def save_config(cfg: Config, path: Path | None = None) -> None:
    """Save configuration to TOML file.

    Args:
        cfg: The configuration to save.
        path: Explicit config file path. If None, uses the default XDG location.
    """
    if path is None:
        path = default_config_path()

    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        f"check_interval = {cfg.check_interval}",
        "",
        "[notifications]",
        f"enabled = {str(cfg.notifications.enabled).lower()}",
    ]
    if cfg.notifications.quiet_hours_start is not None:
        lines.append(f"quiet_hours_start = {cfg.notifications.quiet_hours_start}")
    if cfg.notifications.quiet_hours_end is not None:
        lines.append(f"quiet_hours_end = {cfg.notifications.quiet_hours_end}")

    lines.append("")
    lines.append("[sources]")
    for name, src in cfg.sources.items():
        lines.append(f"[sources.{name}]")
        lines.append(f"enabled = {str(src.enabled).lower()}")
        lines.append("")

    if cfg.terminals != Config().terminals:
        lines.append("terminals = [")
        for term in cfg.terminals:
            lines.append(f'    "{term}",')
        lines.append("]")

    path.write_text("\n".join(lines))
