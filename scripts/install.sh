#!/usr/bin/env bash
# Install (or reinstall) topgrade-update on an Arch-based PC such as CachyOS,
# straight from the private GitHub repo. Safe to re-run.
#
# Usage: bash install.sh [--no-autostart]
#   --no-autostart  Don't start the tray applet at login.
#
# Needs a one-time `gh auth login` (the script offers it) because the repo is
# private. Update later with: uv tool upgrade topgrade-update

set -euo pipefail

REPO="grackleshot/topgrade-update"
# shortcut: PySide6 6.11 requires Python < 3.15; bump once PySide6 supports newer.
PYTHON="3.14"

AUTOSTART=1
for arg in "$@"; do
    case "$arg" in
        --no-autostart) AUTOSTART=0 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
die() { echo "Error: $*" >&2; exit 1; }

[[ "${EUID:-$(id -u)}" -ne 0 ]] || die "run this as your desktop user, without sudo."
command -v pacman >/dev/null || die "this installer is for Arch-based systems (pacman)."

step "Checking system packages"
declare -A PACKAGE_FOR=(
    [git]=git [gh]=github-cli [uv]=uv [checkupdates]=pacman-contrib
)
missing=()
for cmd in "${!PACKAGE_FOR[@]}"; do
    command -v "$cmd" >/dev/null || missing+=("${PACKAGE_FOR[$cmd]}")
done
if ((${#missing[@]})); then
    sudo pacman -S --needed "${missing[@]}"
fi

if ! command -v topgrade >/dev/null; then
    step "Installing topgrade"
    if pacman -Si topgrade >/dev/null 2>&1; then
        sudo pacman -S --needed topgrade
    elif helper="$(command -v paru || command -v yay)"; then
        "$helper" -S --needed topgrade
    else
        echo "topgrade isn't installed and no AUR helper was found." >&2
        echo "Update checks will work; install topgrade from the AUR to apply updates." >&2
    fi
fi

step "Signing in to GitHub"
gh auth status >/dev/null 2>&1 || gh auth login
gh auth setup-git  # lets git (and uv) fetch the private repo over HTTPS

step "Installing topgrade-update from github.com/$REPO (main)"
uv tool install --force --python "$PYTHON" "topgrade-update[gui] @ git+https://github.com/$REPO.git"
BIN_DIR="$(uv tool dir --bin)"
BIN="$BIN_DIR/topgrade-update"
export PATH="$BIN_DIR:$PATH"  # this copy wins over any other topgrade-update

step "Installing the app menu entry and icon"
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git clone --quiet --depth 1 "https://github.com/$REPO.git" "$src"
bash "$src/scripts/install-desktop-integration.sh"

if ((AUTOSTART)); then
    step "Starting the tray applet at login"
    "$BIN" --tray --enable
fi

if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]] && ! pgrep -f "topgrade-update --tray" >/dev/null; then
    step "Starting the tray applet now"
    setsid -f "$BIN" --tray >/dev/null 2>&1 < /dev/null
fi

step "Done: $("$BIN" --version)"
echo "Update later with:  uv tool upgrade topgrade-update"
