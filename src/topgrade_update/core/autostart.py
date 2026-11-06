"""XDG autostart management."""

import os
import shutil
from pathlib import Path

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
AUTOSTART_DIR = _CONFIG_HOME / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "topgrade-update-tray.desktop"

# systemd-xdg-autostart-generator resolves bare Exec names against the user
# manager's PATH, which does not include ~/.local/bin on this system, so the
# autostart unit is silently not generated. Always write an absolute path.
_EXEC_PATH = shutil.which("topgrade-update") or str(
    Path.home() / ".local" / "bin" / "topgrade-update"
)

_AUTOSTART_CONTENT = f"""\
[Desktop Entry]
Type=Application
Name=Topgrade Update
Comment=System tray applet for topgrade update notifications
Exec={_EXEC_PATH} --tray
Icon=topgrade-update
Terminal=false
X-KDE-autostart-phase=2
Categories=System;Utilities;
Keywords=updates;pacman;aur;flatpak;topgrade;
"""


def enable_autostart() -> None:
    """Enable tray autostart at login."""
    AUTOSTART_DIR.mkdir(parents=True, exist_ok=True)
    AUTOSTART_FILE.write_text(_AUTOSTART_CONTENT)
    print(f"Autostart enabled: {AUTOSTART_FILE}")


def disable_autostart() -> None:
    """Disable tray autostart at login."""
    if AUTOSTART_FILE.exists():
        AUTOSTART_FILE.unlink()
        print(f"Autostart disabled (removed {AUTOSTART_FILE}).")
    else:
        print("Autostart was not enabled.")
