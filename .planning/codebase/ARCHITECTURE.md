# Codebase Architecture

## Overview

Single-file Python 3 application (~400 lines) providing update checking and a system tray applet for `topgrade`.

## Components

### 1. Update Checkers (no Qt dependency)
- `check_pacman()` — uses `checkupdates` command
- `check_aur()` — uses `paru -Qua` or `yay -Qua`
- `check_flatpak()` — uses `flatpak remote-ls --updates`
- `check_all()` — aggregates all checkers into a dict

### 2. Notification System
- `send_notification()` — wraps `notify-send` subprocess
- No Python notification library; relies on CLI tool

### 3. CLI Actions
- `cmd_check()` — check updates + notify, exit 1 if updates exist
- `cmd_list()` — print updates to stdout
- `cmd_run()` — exec `topgrade` directly

### 4. Autostart Management
- `enable_autostart()` / `disable_autostart()` — writes/removes XDG `.desktop` file
- Hardcoded desktop entry content

### 5. System Tray Applet (PyQt6)
- `cmd_tray()` — launches QApplication with QSystemTrayIcon
- `Tray` class — timer-driven update checking, context menu, click handlers
- `CheckThread` — QThread wrapper for non-blocking checks
- `UpdatesDialog` — QDialog showing available updates
- `make_icon()` — programmatically generates colored circle + arrow + badge icons
- `launch_topgrade_in_terminal()` — detects terminal, spawns topgrade

## Data Flow

```
Timer (1h) → CheckThread → check_all() → updates dict
                                    ↓
                          Tray._on_check_done()
                                    ↓
                    update icon + tooltip + notify
                                    ↓
                         user click → UpdatesDialog
                                    ↓
                         launch_topgrade_in_terminal()
```

## Key Characteristics

- **Monolithic**: All code in one file
- **Hardcoded**: Intervals, colors, terminals, package managers
- **No config system**: Everything is a constant
- **No tests**: No test suite
- **No packaging**: No pyproject.toml, setup.py, or install target
- **Linux-only**: Arch-centric package managers, XDG autostart
