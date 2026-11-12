"""One-time move of what the app left behind under its old name, topgrade-update."""

# shortcut: delete this module once no topgrade-update installs remain.

from __future__ import annotations

import os
from pathlib import Path

from uptray.core.logging import get_logger

OLD_NAME = "topgrade-update"
NEW_NAME = "uptray"


def _xdg(var: str, *default: str) -> Path:
    return Path(os.environ.get(var) or Path.home().joinpath(*default))


def migrate_from_old_name() -> list[Path]:
    """Move topgrade-update's config, data and state folders to uptray's.

    Never overwrites: when the new folder already exists the old one is left
    alone. An enabled old autostart entry is replaced by uptray's. Returns the
    folders that were moved.
    """
    log = get_logger("migrate")
    moved: list[Path] = []
    for base in (
        _xdg("XDG_CONFIG_HOME", ".config"),
        _xdg("XDG_DATA_HOME", ".local", "share"),
        _xdg("XDG_STATE_HOME", ".local", "state"),
    ):
        old, new = base / OLD_NAME, base / NEW_NAME
        if old.is_dir() and not new.exists():
            try:
                old.rename(new)
                moved.append(new)
            except OSError as exc:
                log.warning("Could not move %s to %s: %s", old, new, exc)
    # Window sizes and splitters (QSettings) moved with the config folder under the old name.
    old_layout = _xdg("XDG_CONFIG_HOME", ".config") / NEW_NAME / f"{OLD_NAME}.conf"
    new_layout = old_layout.with_name(f"{NEW_NAME}.conf")
    if old_layout.is_file() and not new_layout.exists():
        try:
            old_layout.rename(new_layout)
        except OSError as exc:
            log.warning("Could not move %s: %s", old_layout, exc)
    old_autostart = _xdg("XDG_CONFIG_HOME", ".config") / "autostart" / f"{OLD_NAME}-tray.desktop"
    if old_autostart.is_file():
        from uptray.core import autostart

        try:
            autostart.enable_autostart()
            old_autostart.unlink()
        except OSError as exc:
            log.warning("Could not replace old autostart entry: %s", exc)
    return moved
