# Topgrade Update

An interactive update notifier & applier using [topgrade](https://github.com/topgrade-rs/topgrade).

## Features

- **System tray applet** with badge count and update notifications
- **Multi-source checking**: pacman, AUR (paru/yay), flatpak
- **Desktop notifications** via libnotify
- **One-click upgrade**: launches topgrade in your preferred terminal
- **Configurable**: TOML config file with per-source settings

## Installation

```bash
pip install -e ".[gui]"
```

## Usage

```bash
topgrade-update              # Run topgrade interactively
topgrade-update -c/--check   # Check for updates and notify
topgrade-update -l/--list    # List available updates
topgrade-update --tray       # Launch the system tray applet
topgrade-update --tray --enable   # Enable tray autostart at login
```

## Configuration

Create `~/.config/topgrade-update/config.toml`:

```toml
check_interval = 3600  # seconds

[sources.pacman]
enabled = true

[sources.aur]
enabled = true

[sources.flatpak]
enabled = true

[notifications]
enabled = true
quiet_hours_start = 23
quiet_hours_end = 8
```
