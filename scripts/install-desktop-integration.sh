#!/usr/bin/env bash
# Install desktop integration files (icon + .desktop file) for topgrade-update.
# Usage: ./scripts/install-desktop-integration.sh

set -euo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    echo "Run this script as your desktop user, without sudo." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

ICON_THEME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
ICON_DIR="$ICON_THEME_DIR/scalable/apps"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

echo "Installing icon to $ICON_DIR..."
mkdir -p "$ICON_DIR"
cp "$PROJECT_DIR/icons/hicolor/scalable/apps/topgrade-update.svg" "$ICON_DIR/"

echo "Installing desktop file to $DESKTOP_DIR..."
mkdir -p "$DESKTOP_DIR"
cp "$PROJECT_DIR/topgrade-update-tray.desktop" "$DESKTOP_DIR/"

echo "Updating icon cache..."
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache "$ICON_THEME_DIR" 2>/dev/null || true
fi

echo "Done. Run 'topgrade-update --tray --enable' to enable autostart."
