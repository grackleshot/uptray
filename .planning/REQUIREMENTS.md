# Requirements: Topgrade Update

**Defined:** 2026-05-19
**Core Value:** Users never miss available system updates because the tray applet silently checks and clearly surfaces them.

## v1 Requirements

### Project Structure & Packaging

- [x] **PACK-01**: Code organized as `src/topgrade_update/` package with proper module boundaries
- [x] **PACK-02**: `pyproject.toml` with hatchling backend, entry points, and `[gui]` optional dependency
- [x] **PACK-03**: CLI entry point `topgrade-update` works with zero GUI dependencies installed
- [x] **PACK-04**: `python -m topgrade_update` support via `__main__.py`

### Configuration System

- [x] **CONF-01**: TOML config file at `~/.config/topgrade-update/config.toml`
- [x] **CONF-02**: Configurable check interval (default 60 min, bounds: 5 min – 24 h)
- [x] **CONF-03**: Per-source enable/disable (pacman, AUR, flatpak)
- [x] **CONF-04**: Configurable terminal emulator priority list
- [x] **CONF-05**: Notification settings (enable/disable, quiet hours start/end)
- [x] **CONF-06**: Config loaded with precedence: CLI args > env vars > config file > defaults

### Modular Update Checkers

- [x] **CHECK-01**: Plugin ABC with `name`, `is_available()`, `check() -> list[Update]`
- [x] **CHECK-02**: Plugin discovery via hybrid approach — built-ins auto-registered, third-party via `importlib.metadata` entry points
- [x] **CHECK-03**: Pacman checker via `checkupdates` (with timeout and error isolation)
- [x] **CHECK-04**: AUR checker via auto-detected `paru` or `yay`
- [x] **CHECK-05**: Flatpak checker with version and branch info
- [x] **CHECK-06**: Per-checker timeout (default 30s) and graceful error handling
- [x] **CHECK-07**: Failed checker does not block other checkers

### Notification System

- [x] **NOTIFY-01**: Desktop notification on transition from 0 to >0 updates
- [x] **NOTIFY-02**: Notification includes source breakdown (e.g., "5 packages, 2 AUR")
- [x] **NOTIFY-03**: No re-notification for same update count on subsequent checks
- [x] **NOTIFY-04**: Quiet hours respected (no notifications during configured window)
- [x] **NOTIFY-05**: Notification actions: "Run Topgrade", "Snooze", and "Dismiss" when supported

### Tray Applet

- [x] **TRAY-01**: System tray icon with state: idle, checking, up-to-date, updates-available
- [x] **TRAY-02**: Badge count on icon when updates available
- [x] **TRAY-03**: Context menu: status, check now, view updates, run topgrade, quit
- [x] **TRAY-04**: Left-click shows updates dialog (if updates) or runs topgrade (if none)
- [x] **TRAY-05**: Updates dialog shows per-source breakdown with package names
- [x] **TRAY-06**: "Run Topgrade" button in updates dialog launches terminal
- [x] **TRAY-07**: Icon caching — do not regenerate pixmap on every check
- [x] **TRAY-08**: Last check timestamp shown in tooltip or menu
- [x] **TRAY-09**: Tray persists when dialog closed (`setQuitOnLastWindowClosed(False)`)

### Topgrade Integration

- [x] **TG-01**: Launch `topgrade` in detected terminal emulator
- [x] **TG-02**: Terminal detection: `xdg-terminal-exec`, `$TERMINAL`, then ranked fallbacks
- [x] **TG-03**: Parse `topgrade.toml` to skip checkers disabled there

### Logging & Observability

- [x] **LOG-01**: Rotating file log at `~/.local/share/topgrade-update/log`
- [x] **LOG-02**: Per-checker log entries with timing and error details
- [x] **LOG-03**: CLI `--verbose` flag for debug output

### Quality & Testing

- [x] **QUAL-01**: Full type hints across codebase
- [x] **QUAL-02**: `mypy --strict` passes
- [x] **QUAL-03**: `ruff` for linting and formatting
- [x] **QUAL-04**: Unit tests for core logic (config, checkers, engine) — 72 tests
- [x] **QUAL-05**: `pytest-qt` tests for tray GUI components — requires PySide6 in test env

### Additional Checkers

- [x] **CHECK-08**: `fwupdmgr` firmware update checker
- [x] **CHECK-09**: Custom command checker (user-defined scripts)

### Reboot Detection

- [x] **REBOOT-01**: Kernel/reboot required detection (Arch + Debian)

## v2 Requirements

### Enhanced Features

- **NEWS-01**: Arch Linux News integration — check for news since last update
- **MAINT-01**: Post-update helper reminders (orphans, pacnew, cache cleanup)
- **TRAY-10**: Snooze persistence across restarts (save to disk)
- **TRAY-11**: Update list preview in tray menu (package names + versions)
- **I18N-01**: gettext internationalization support
- **NOTIFY-06**: Sound support for notifications

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic update installation | Arch updates can break systems; explicit user action required |
| Auto-reboot after updates | Never reboot without consent; at most notify |
| macOS/Windows support | Linux-only focus; different package manager ecosystems |
| Mobile app or web UI | Desktop-only tool |
| Full package manager GUI | Users have pamac/octopi; stay focused on notification + launch |
| Non-topgrade upgrade paths | Topgrade is the intended tool |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PACK-01 | Phase 1 | Complete |
| PACK-02 | Phase 1 | Complete |
| PACK-03 | Phase 1 | Complete |
| PACK-04 | Phase 1 | Complete |
| CONF-01 | Phase 2 | Complete |
| CONF-02 | Phase 2 | Complete |
| CONF-03 | Phase 2 | Complete |
| CONF-04 | Phase 2 | Complete |
| CONF-05 | Phase 2 | Complete |
| CONF-06 | Phase 2 | Complete |
| CHECK-01 | Phase 3 | Complete |
| CHECK-02 | Phase 3 | Complete |
| CHECK-03 | Phase 3 | Complete |
| CHECK-04 | Phase 3 | Complete |
| CHECK-05 | Phase 3 | Complete |
| CHECK-06 | Phase 3 | Complete |
| CHECK-07 | Phase 3 | Complete |
| NOTIFY-01 | Phase 4 | Complete |
| NOTIFY-02 | Phase 4 | Complete |
| NOTIFY-03 | Phase 4 | Complete |
| NOTIFY-04 | Phase 4 | Complete |
| NOTIFY-05 | Phase 4 | Complete |
| TRAY-01 | Phase 5 | Complete |
| TRAY-02 | Phase 5 | Complete |
| TRAY-03 | Phase 5 | Complete |
| TRAY-04 | Phase 5 | Complete |
| TRAY-05 | Phase 5 | Complete |
| TRAY-06 | Phase 5 | Complete |
| TRAY-07 | Phase 5 | Complete |
| TRAY-08 | Phase 5 | Complete |
| TRAY-09 | Phase 5 | Complete |
| TG-01 | Phase 6 | Complete |
| TG-02 | Phase 6 | Complete |
| TG-03 | Phase 6 | Complete |
| LOG-01 | Phase 7 | Complete |
| LOG-02 | Phase 7 | Complete |
| LOG-03 | Phase 7 | Complete |
| QUAL-01 | Phase 8 | Complete |
| QUAL-02 | Phase 8 | Complete |
| QUAL-03 | Phase 8 | Complete |
| QUAL-04 | Phase 8 | Complete |
| QUAL-05 | Phase 8 | Complete |
| CHECK-08 | Phase 8 | Complete |
| CHECK-09 | Phase 8 | Complete |
| REBOOT-01 | Phase 8 | Complete |

**Coverage:**
- v1 requirements: 45 total
- Mapped to phases: 45
- Unmapped: 0 ✓
- Complete: 45/45 (100%)

---
*Requirements defined: 2026-05-19*
*Last updated: 2026-10-28 after implementation review*
