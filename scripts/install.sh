#!/usr/bin/env bash
# Install (or reinstall) uptray on an Arch-based PC such as CachyOS,
# straight from GitHub. Safe to re-run. Update later with:
#   uv tool upgrade uptray

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: install.sh [--no-autostart]
  --no-autostart  Don't start the tray applet at login.

If the GitHub repo can't be read anonymously (a private copy), the script
signs in with the GitHub CLI (gh) so git and uv can fetch it.
USAGE
}

REPO="grackleshot/uptray"
# shortcut: PySide6 6.11 requires Python < 3.15; bump once PySide6 supports newer.
PYTHON="3.14"

AUTOSTART=1
for arg in "$@"; do
    case "$arg" in
        --no-autostart) AUTOSTART=0 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }
die() { echo "Error: $*" >&2; exit 1; }

[[ "${EUID:-$(id -u)}" -ne 0 ]] || die "run this as your desktop user, without sudo."
command -v pacman >/dev/null || die "this installer is for Arch-based systems (pacman)."

step "Checking system packages"
declare -A PACKAGE_FOR=(
    [git]=git [uv]=uv [checkupdates]=pacman-contrib
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
        "$helper" -S --needed topgrade-bin  # prebuilt; "topgrade" compiles for minutes
    else
        echo "topgrade isn't installed and no AUR helper was found." >&2
        echo "Update checks will work; install topgrade from the AUR to apply updates." >&2
    fi
fi

step "Checking access to github.com/$REPO"
if ! GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=true git ls-remote "https://github.com/$REPO.git" HEAD >/dev/null 2>&1; then
    # Private repo: sign in with the GitHub CLI so git (and uv) can fetch it.
    command -v gh >/dev/null || sudo pacman -S --needed github-cli
    gh auth status >/dev/null 2>&1 || gh auth login
    gh auth setup-git
fi

# The app used to be called topgrade-update: remove that install so only one remains.
if uv tool list 2>/dev/null | grep -q '^topgrade-update '; then
    step "Removing the old topgrade-update install"
    uv tool uninstall topgrade-update
    rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/topgrade-update-tray.desktop" \
        "${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps/topgrade-update.svg"
fi
# "[t]"/"[u]": run as bash -c "$(curl ...)", this script's own text is a process
# command line, and a plain pattern would match the installer itself.
if pgrep -f "[t]opgrade-update --tray" >/dev/null; then
    echo "An old topgrade-update tray is still running: quit it from its tray menu." >&2
fi

step "Installing uptray from github.com/$REPO (main)"
uv tool install --force --python "$PYTHON" "uptray[gui] @ git+https://github.com/$REPO.git"
BIN_DIR="$(uv tool dir --bin)"
BIN="$BIN_DIR/uptray"
export PATH="$BIN_DIR:$PATH"  # this copy wins over any other uptray

step "Installing the app menu entry and icon"
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git clone --quiet --depth 1 "https://github.com/$REPO.git" "$src"
bash "$src/scripts/install-desktop-integration.sh"

if ((AUTOSTART)); then
    step "Starting the tray applet at login"
    "$BIN" --tray --enable
fi

if [[ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]] && ! pgrep -f "[u]ptray --tray" >/dev/null; then
    step "Starting the tray applet now"
    setsid -f "$BIN" --tray >/dev/null 2>&1 < /dev/null
fi

step "Done: $("$BIN" --version)"
echo "Update later with:  uv tool upgrade uptray"
