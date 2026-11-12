#!/usr/bin/env bash
# Install desktop integration files (icon + .desktop file) for uptray.
# Usage: ./scripts/install-desktop-integration.sh [--systemd-timer]
#   --systemd-timer  Also install and enable a systemd user timer that runs
#                    `uptray --check` at boot and every 6 hours.

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo "Run this script as your desktop user, without sudo." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

INSTALL_TIMER=0
for arg in "$@"; do
    case "$arg" in
        --systemd-timer) INSTALL_TIMER=1 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

ICON_THEME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
ICON_DIR="$ICON_THEME_DIR/scalable/apps"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

echo "Installing icon to $ICON_DIR..."
mkdir -p "$ICON_DIR"
cp "$PROJECT_DIR/icons/hicolor/scalable/apps/uptray.svg" "$ICON_DIR/"

echo "Installing desktop file to $DESKTOP_DIR..."
mkdir -p "$DESKTOP_DIR"
# Absolute Exec path: ~/.local/bin is not always on the desktop session's PATH.
BIN="$(command -v uptray || true)"
sed "s|^Exec=uptray|Exec=${BIN:-uptray}|" \
    "$PROJECT_DIR/uptray.desktop" > "$DESKTOP_DIR/uptray.desktop"

echo "Updating icon cache..."
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache "$ICON_THEME_DIR" 2>/dev/null || true
fi

if [[ "$INSTALL_TIMER" -eq 1 ]]; then
    if ! command -v systemctl &>/dev/null; then
        echo "systemctl not found; skipping systemd timer." >&2
    else
        TIMER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
        echo "Installing systemd user units to $TIMER_DIR..."
        mkdir -p "$TIMER_DIR"
        cp "$PROJECT_DIR/systemd/uptray.service" "$TIMER_DIR/"
        cp "$PROJECT_DIR/systemd/uptray.timer" "$TIMER_DIR/"
        systemctl --user daemon-reload
        systemctl --user enable --now uptray.timer
        echo "Timer enabled. Adjust with: systemctl --user edit --full uptray.timer"
    fi
fi

echo "Done. Run 'uptray --tray --enable' to enable autostart."
