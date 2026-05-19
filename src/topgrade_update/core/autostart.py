"""XDG autostart management."""

from pathlib import Path

AUTOSTART_DIR = Path.home() / ".config" / "autostart"
AUTOSTART_FILE = AUTOSTART_DIR / "topgrade-update-tray.desktop"

_AUTOSTART_CONTENT = """\
[Desktop Entry]
Type=Application
Name=Topgrade Update Tray
Comment=System tray applet for topgrade update notifications
Exec=topgrade-update --tray
Icon=topgrade-update
Terminal=false
X-KDE-autostart-phase=2
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
