# Topgrade Update

> A professional Linux desktop update notifier and system tray applet for Arch-based systems.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy.readthedocs.io/)
[![ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://docs.astral.sh/ruff/)

## Features

- **System tray applet** with periodic update checking and a badge counter
- **Multi-source checking**: pacman, AUR (paru/yay/pikaur), Flatpak version and branch, firmware, reboot state — checkers run in parallel
- **Smart notifications**: deduplication that survives restarts, quiet hours, snooze, desktop action buttons, optional sound, and critical-urgency reboot alerts
- **Arch news**: reads the [archlinux.org news feed](https://archlinux.org/feeds/news/), flags items published since you last read the news, and opens them from the tray menu
- **Event-driven checks**: re-checks shortly after the pacman database changes (someone ran an upgrade), after resume from suspend, and skips checks while offline
- **Post-update maintenance reminders**: orphan packages, unmerged `.pacnew`/`.pacsave` files, oversized package cache — surfaced once per day after an update session ends
- **Update history**: the History window has a System log tab (recent upgrade sessions parsed from `/var/log/pacman.log`) and a Runs tab (past runs started from the app)
- **Dry-run preview**: launches `topgrade --dry-run` from the tray or dialog; when the preview succeeds, a **Run for real** button starts the actual update
- **In-app run window**: Simple and Verbose views, step checklist, and a prompt bar that surfaces questions from the running command, including answers you type (pacdiff menus, pacman "Enter a number")
- **Keeps running when closed**: closing the run window mid-update hides it instead of stopping the update; choose Run Topgrade in the tray to bring it back, and Cancel asks before stopping
- **Update only this source**: right-click a source in the Updates dialog to run topgrade for just that step
- **Topgrade integration**: respects your `topgrade.toml` (including `misc.disable`, `misc.only`, and `topgrade.d/` drop-ins), launches in your preferred terminal
- **Package navigation**: double-click a package in the dialog or click it in the tray menu to open its upstream page
- **Settings dialog**: edit interval (in minutes), sources including firmware and reboot, quiet hours, terminals, icons, and the autostart toggle without touching TOML; Restore Defaults resets the form
- **Colorblind-safe icon palette** (`tray.icon_style = "colorblind"`) plus a dedicated reboot-required icon
- **Single instance**: a second tray launch exits instead of duplicating notifications
- **Plugin architecture**: add custom checkers via entry points
- **Configurable**: TOML config at `~/.config/topgrade-update/config.toml`
- **CLI**: `topgrade-update --check`, `--list`, `--tray`, `--verbose`, `--json`, `--version`
- **systemd timer option**: run headless checks at boot and every 6 hours without the tray

## Requirements

The pacman checker uses `checkupdates`, which ships in the `pacman-contrib`
package. Without it the pacman source reports an error ("install
pacman-contrib") instead of silently showing zero updates.

```bash
sudo pacman -S pacman-contrib
```

## Installation

### On a CachyOS / Arch PC (recommended)

The repo is private, so each PC signs in to GitHub once with the GitHub CLI.
These commands work in fish and bash:

```bash
sudo pacman -S --needed github-cli
gh auth login
gh api -H "Accept: application/vnd.github.raw" repos/grackleshot/topgrade-update/contents/scripts/install.sh > /tmp/topgrade-update-install.sh
bash /tmp/topgrade-update-install.sh
```

The installer:

- installs whatever is missing of `git`, `github-cli`, `uv` and `pacman-contrib`
  (asks for your sudo password only if something is missing)
- installs `topgrade` from the repos or, failing that, the AUR via `paru`/`yay`
- runs `gh auth setup-git` so git can fetch this private repo
- installs the app with `uv tool install` from `main` (Python 3.14, PySide6)
- adds the app-menu entry and icon, turns on autostart, and starts the tray

Pass `--no-autostart` to skip autostart. Re-running the script is safe. If your
shell can't find `topgrade-update` afterwards, run `uv tool update-shell` once.

Update to the latest `main`:

```bash
uv tool upgrade topgrade-update
```

Uninstall:

```bash
topgrade-update --tray --disable
uv tool uninstall topgrade-update
rm ~/.local/share/applications/topgrade-update-tray.desktop \
   ~/.local/share/icons/hicolor/scalable/apps/topgrade-update.svg
```

### From source

```bash
git clone https://github.com/grackleshot/topgrade-update.git
cd topgrade-update
pip install -e '.[gui]'
```

### Desktop integration

```bash
./scripts/install-desktop-integration.sh
topgrade-update --tray --enable   # autostart at login
```

### Headless checks with a systemd user timer

Install a timer that runs `topgrade-update --check` at boot and every 6 hours
(useful when the tray is not running, e.g. on a minimal WM setup):

```bash
./scripts/install-desktop-integration.sh --systemd-timer
systemctl --user list-timers topgrade-update.timer   # verify
```

## Usage

### CLI

```bash
# Check for updates and notify
topgrade-update --check

# List available updates
topgrade-update --list

# List as JSON (for scripts)
topgrade-update --list --json

# Run topgrade in the current terminal
topgrade-update

# Launch the system tray applet
topgrade-update --tray

# Enable/disable autostart
topgrade-update --tray --enable
topgrade-update --tray --disable

# Verbose output
topgrade-update --check --verbose

# Print the version
topgrade-update --version
```

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | success / system is up to date |
| 1 | updates are available (`--check`), or topgrade/tray/GUI is unavailable |
| 2 | errors, or the check was incomplete |
| 3 | the tray applet is already running |

### Keyboard shortcuts

| Key | Where | Action |
| --- | --- | --- |
| Esc | Run window | Close a finished run (never mid-run) |
| Ctrl+1 / Ctrl+2 | Run window | Switch to Simple / Verbose view |
| Ctrl+F | Updates dialog | Focus the package filter |

### Configuration

Create `~/.config/topgrade-update/config.toml`:

```toml
# Check interval in seconds (default: 3600; allowed range: 300–86400)
check_interval = 3600

# Terminal emulator priority (first available wins)
terminals = ["konsole", "alacritty", "kitty", "xterm"]

# Per-source enable/disable
[sources.pacman]
enabled = true

[sources.aur]
enabled = true

[sources.flatpak]
enabled = true

[sources.firmware]
enabled = true

# Notification settings
[notifications]
enabled = true
quiet_hours_start = 23  # 11 PM
quiet_hours_end = 7     # 7 AM
sound = false           # request the notification server's default sound

# Tray behavior
[tray]
click_action = "default"      # "default", "show_updates", "run_topgrade"
snooze_hours = 4
icon_style = "default"        # "default" or "colorblind"
```

Snooze state and notification deduplication persist across restarts in
`~/.local/state/topgrade-update/state.json`, so restarting the tray does not
re-notify about updates you already saw.

Configuration precedence is **CLI arguments → environment variables → TOML file → defaults**.
Overrides apply to `--check`, `--list`, and `--tray`:

| Setting | Environment variable | CLI override |
| --- | --- | --- |
| Check interval | `TOPGRADE_UPDATE_CHECK_INTERVAL` | `--check-interval SECONDS` |
| Terminal priority | `TOPGRADE_UPDATE_TERMINALS` (colon-separated) | Repeat `--terminal COMMAND` |
| Checker enablement | `TOPGRADE_UPDATE_SOURCE_<NAME>_ENABLED` | `--enable-source NAME` / `--disable-source NAME` |
| Notifications | `TOPGRADE_UPDATE_NOTIFICATIONS_ENABLED` | `--enable-notifications` / `--disable-notifications` |
| Quiet hours | `TOPGRADE_UPDATE_QUIET_HOURS_START`, `TOPGRADE_UPDATE_QUIET_HOURS_END` | `--quiet-hours-start HOUR`, `--quiet-hours-end HOUR`, or `--no-quiet-hours` |
| Notification sound | `TOPGRADE_UPDATE_NOTIFICATIONS_SOUND` | `--sound` / `--no-sound` |
| Tray click action | `TOPGRADE_UPDATE_TRAY_CLICK_ACTION` | `--tray-click-action ACTION` |
| Snooze duration | `TOPGRADE_UPDATE_TRAY_SNOOZE_HOURS` | `--snooze-hours HOURS` |
| Icon style | `TOPGRADE_UPDATE_TRAY_ICON_STYLE` | `--icon-style default\|colorblind` |

Boolean environment values accept `true`/`false`, `yes`/`no`, `on`/`off`, or `1`/`0`.
For checker names, use uppercase letters and preserve underscores; for example,
`TOPGRADE_UPDATE_SOURCE_CUSTOM_MY_CHECK_ENABLED` controls the `custom_my_check` checker.

### Plugin architecture

Create a Python package with a custom checker:

```python
from topgrade_update.core.provider import UpdateChecker
from topgrade_update.core.models import Update

class MyChecker(UpdateChecker):
    name = "my-checker"
    label = "My Checker"

    def is_available(self) -> bool:
        return True  # or check for required tools

    def check(self) -> list[Update]:
        # Return list of Update objects
        return [Update(name="pkg", old_version="1.0", new_version="2.0", source="my-checker")]
```

Register via `pyproject.toml`:

```toml
[project.entry-points."topgrade_update.plugins"]
my-checker = "mypackage.plugins:MyChecker"
```

For a simple command-based checker, add a command that prints lines in
`name old-version -> new-version` format:

```toml
[[sources.custom_commands]]
name = "my-checker"
command = ["my-update-check", "--list"]
enabled = true
```

## Architecture

```
topgrade-update/
├── src/topgrade_update/
│   ├── cli/
│   │   └── main.py          # CLI entry point & argument parsing
│   ├── core/
│   │   ├── checkers/
│   │   │   ├── builtins.py   # Pacman, AUR, Flatpak, Firmware checkers
│   │   │   ├── facade.py     # UpdateEngine facade (check_all, find_terminal)
│   │   │   ├── reboot.py     # Reboot-required detection
│   │   │   └── __init__.py   # Public API re-exports
│   │   ├── logging/          # Rotating file + optional console logging
│   │   ├── arch_news.py      # Arch news feed reader + read markers
│   │   ├── autostart.py      # XDG autostart management
│   │   ├── config.py         # TOML config loader/saver
│   │   ├── engine.py         # UpdateEngine (parallel plugin orchestration)
│   │   ├── history.py        # pacman.log upgrade-session parser
│   │   ├── links.py          # Upstream package URL resolution
│   │   ├── maintenance.py    # Orphans / pacnew / cache detection
│   │   ├── models.py         # Update, CheckResult, Config dataclasses
│   │   ├── network.py        # NetworkManager connectivity probe
│   │   ├── notification_engine.py  # Dedup + quiet hours + deferral
│   │   ├── notifications.py  # DBus/jeepney + notify-send client
│   │   ├── quiet_hours.py    # Time window helpers
│   │   ├── state.py          # Persistent snooze/dedup state (XDG_STATE_HOME)
│   │   ├── subprocess.py     # Process-group timeout runner
│   │   └── topgrade_config.py # topgrade.toml/topgrade.d parser
│   └── gui/
│       ├── tray.py           # System tray applet (PySide6)
│       ├── tray_logic.py     # Pure Python tray helpers (testable)
│       ├── dialog.py         # Updates, history, maintenance dialogs
│       ├── settings.py       # Settings dialog
│       └── icons.py          # Programmatic icon generation
├── tests/                    # pytest test suite
├── icons/                    # SVG icon assets
├── scripts/                  # Helper scripts
└── pyproject.toml
```

## Quality

```bash
# Linting
ruff check src/ tests/

# Type checking
mypy src/

# Testing
pytest tests/

# All checks
ruff check src/ tests/ && mypy src/ && pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure `ruff check`, `mypy`, and `pytest` all pass
5. Submit a pull request

## License

MIT
