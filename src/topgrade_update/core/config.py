"""Configuration loading and management."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from topgrade_update.core.models import (
    Config,
    CustomCommandConfig,
    NotificationConfig,
    SourceConfig,
    TrayConfig,
)


def _xdg_config_home() -> Path:
    """Return the XDG config directory."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def default_config_path() -> Path:
    """Return the default configuration file path."""
    return _xdg_config_home() / "topgrade-update" / "config.toml"


def _merge_source_config(raw: dict[str, Any]) -> SourceConfig:
    """Build a SourceConfig from a raw dict."""
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("source enabled settings must be true or false")
    return SourceConfig(enabled=enabled)


def _merge_notification_config(raw: dict[str, Any]) -> NotificationConfig:
    """Build a NotificationConfig from a raw dict."""
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("notifications.enabled must be true or false")
    quiet_hours: dict[str, int | None] = {}
    for key in ("quiet_hours_start", "quiet_hours_end"):
        hour = raw.get(key)
        if hour is not None and (
            not isinstance(hour, int) or isinstance(hour, bool) or not 0 <= hour <= 23
        ):
            raise ValueError(f"notifications.{key} must be an integer from 0 to 23")
        quiet_hours[key] = hour
    return NotificationConfig(
        enabled=enabled,
        quiet_hours_start=quiet_hours["quiet_hours_start"],
        quiet_hours_end=quiet_hours["quiet_hours_end"],
    )


def _merge_tray_config(raw: dict[str, Any]) -> TrayConfig:
    """Build a TrayConfig from a raw dict."""
    click_action = raw.get("click_action", "default")
    if not isinstance(click_action, str) or click_action not in {
        "default",
        "show_updates",
        "run_topgrade",
    }:
        raise ValueError("tray.click_action must be default, show_updates, or run_topgrade")
    snooze_hours = raw.get("snooze_hours", 4)
    if (
        not isinstance(snooze_hours, int)
        or isinstance(snooze_hours, bool)
        or not 1 <= snooze_hours <= 24
    ):
        raise ValueError("tray.snooze_hours must be an integer from 1 to 24")
    return TrayConfig(
        click_action=click_action,
        snooze_hours=snooze_hours,
    )


def _merge_custom_command(raw: dict[str, Any]) -> CustomCommandConfig:
    """Build a validated custom-command config from a raw TOML table."""
    name = raw.get("name")
    command = raw.get("command")
    enabled = raw.get("enabled", True)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each sources.custom_commands entry needs a non-empty name")
    name = name.strip()
    if not isinstance(command, list) or not command or not all(
        isinstance(arg, str) and arg for arg in command
    ):
        raise ValueError(f"custom command {name!r} must have a non-empty command list")
    if not isinstance(enabled, bool):
        raise ValueError(f"custom command {name!r} enabled must be true or false")
    return CustomCommandConfig(name=name, command=command, enabled=enabled)


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
        interval = raw["check_interval"]
        if (
            not isinstance(interval, int)
            or isinstance(interval, bool)
            or not 300 <= interval <= 86400
        ):
            raise ValueError("check_interval must be an integer from 300 to 86400 seconds")
        cfg.check_interval = interval

    if "terminals" in raw:
        terminals = raw["terminals"]
        if not isinstance(terminals, list) or not all(
            isinstance(terminal, str) and terminal for terminal in terminals
        ):
            raise ValueError("terminals must be a list of non-empty command names")
        cfg.terminals = terminals

    if "sources" in raw:
        sources = raw["sources"]
        if not isinstance(sources, dict):
            raise ValueError("sources must be a TOML table")
        for name, src_raw in sources.items():
            if name == "custom_commands":
                if not isinstance(src_raw, list):
                    raise ValueError("sources.custom_commands must be an array of tables")
                cfg.custom_commands = [
                    _merge_custom_command(item)
                    for item in src_raw
                    if isinstance(item, dict)
                ]
                if len(cfg.custom_commands) != len(src_raw):
                    raise ValueError("each sources.custom_commands entry must be a table")
                names = [command.name.lower().replace(" ", "_") for command in cfg.custom_commands]
                if len(names) != len(set(names)):
                    raise ValueError("custom command names must be unique")
                continue
            if not isinstance(src_raw, dict):
                raise ValueError(f"sources.{name} must be a TOML table")
            cfg.sources[name] = _merge_source_config(src_raw)

    if "notifications" in raw:
        if not isinstance(raw["notifications"], dict):
            raise ValueError("notifications must be a TOML table")
        cfg.notifications = _merge_notification_config(raw["notifications"])

    if "tray" in raw:
        if not isinstance(raw["tray"], dict):
            raise ValueError("tray must be a TOML table")
        cfg.tray = _merge_tray_config(raw["tray"])

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
        f"terminals = {json.dumps(cfg.terminals, ensure_ascii=False)}",
        "",
        "[notifications]",
        f"enabled = {str(cfg.notifications.enabled).lower()}",
    ]
    if cfg.notifications.quiet_hours_start is not None:
        lines.append(f"quiet_hours_start = {cfg.notifications.quiet_hours_start}")
    if cfg.notifications.quiet_hours_end is not None:
        lines.append(f"quiet_hours_end = {cfg.notifications.quiet_hours_end}")

    lines.extend(
        [
            "",
            "[tray]",
            f"click_action = {json.dumps(cfg.tray.click_action, ensure_ascii=False)}",
            f"snooze_hours = {cfg.tray.snooze_hours}",
            "",
        ]
    )
    for name, src in cfg.sources.items():
        lines.append(f"[sources.{json.dumps(name, ensure_ascii=False)}]")
        lines.append(f"enabled = {str(src.enabled).lower()}")
        lines.append("")

    for custom in cfg.custom_commands:
        lines.extend(
            [
                "[[sources.custom_commands]]",
                f"name = {json.dumps(custom.name, ensure_ascii=False)}",
                f"command = {json.dumps(custom.command, ensure_ascii=False)}",
                f"enabled = {str(custom.enabled).lower()}",
                "",
            ]
        )

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
