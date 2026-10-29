# Topgrade Update

> A professional Linux desktop update notifier and system tray applet for Arch-based systems.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![mypy](https://img.shields.io/badge/mypy-checked-blue.svg)](https://mypy.readthedocs.io/)
[![ruff](https://img.shields.io/badge/lint-ruff-orange.svg)](https://docs.astral.sh/ruff/)

## Features

- **System tray applet** with periodic update checking and a badge counter
- **Multi-source checking**: pacman, AUR (paru/yay), Flatpak version and branch, firmware, reboot state
- **Smart notifications**: deduplication, quiet hours, snooze, and desktop action buttons
- **Topgrade integration**: respects your `topgrade.toml`, launches in your preferred terminal
- **Plugin architecture**: add custom checkers via entry points
- **Configurable**: TOML config at `~/.config/topgrade-update/config.toml`
- **CLI**: `topgrade-update --check`, `--list`, `--tray`, `--verbose`, `--json`

## Installation

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
```

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

# Tray behavior
[tray]
click_action = "default"  # "default", "show_updates", "run_topgrade"
snooze_hours = 4
```

Configuration precedence is **CLI arguments → environment variables → TOML file → defaults**.
Overrides apply to `--check`, `--list`, and `--tray`:

| Setting | Environment variable | CLI override |
| --- | --- | --- |
| Check interval | `TOPGRADE_UPDATE_CHECK_INTERVAL` | `--check-interval SECONDS` |
| Terminal priority | `TOPGRADE_UPDATE_TERMINALS` (colon-separated) | Repeat `--terminal COMMAND` |
| Checker enablement | `TOPGRADE_UPDATE_SOURCE_<NAME>_ENABLED` | `--enable-source NAME` / `--disable-source NAME` |
| Notifications | `TOPGRADE_UPDATE_NOTIFICATIONS_ENABLED` | `--enable-notifications` / `--disable-notifications` |
| Quiet hours | `TOPGRADE_UPDATE_QUIET_HOURS_START`, `TOPGRADE_UPDATE_QUIET_HOURS_END` | `--quiet-hours-start HOUR`, `--quiet-hours-end HOUR`, or `--no-quiet-hours` |
| Tray click action | `TOPGRADE_UPDATE_TRAY_CLICK_ACTION` | `--tray-click-action ACTION` |
| Snooze duration | `TOPGRADE_UPDATE_TRAY_SNOOZE_HOURS` | `--snooze-hours HOURS` |

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
│   │   ├── config.py         # TOML config loader/saver
│   │   ├── engine.py         # UpdateEngine (plugin orchestration)
│   │   ├── models.py         # Update, CheckResult, Config dataclasses
│   │   ├── notification_engine.py  # Dedup + quiet hours + deferral
│   │   ├── notifications.py  # DBus/jeepney + notify-send client
│   │   ├── quiet_hours.py    # Time window helpers
│   │   ├── subprocess.py     # Process-group timeout runner
│   │   ├── topgrade_config.py # topgrade.toml parser
│   │   └── autostart.py      # XDG autostart management
│   └── gui/
│       ├── tray.py           # System tray applet (PySide6)
│       ├── tray_logic.py     # Pure Python tray helpers (testable)
│       ├── dialog.py         # Updates list dialog
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
