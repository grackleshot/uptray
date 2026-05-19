# Requirements: Topgrade Update

**Defined:** 2026-05-19
**Core Value:** Users never miss available system updates because the tray applet silently checks and clearly surfaces them.

## v1 Requirements

### Project Structure & Packaging

- [ ] **PACK-01**: Code organized as `src/topgrade_update/` package with proper module boundaries
- [ ] **PACK-02**: `pyproject.toml` with hatchling backend, entry points, and `[gui]` optional dependency
- [ ] **PACK-03**: CLI entry point `topgrade-update` works with zero GUI dependencies installed
- [ ] **PACK-04**: `python -m topgrade_update` support via `__main__.py`

### Configuration System

- [ ] **CONF-01**: TOML config file at `~/.config/topgrade-update/config.toml`
- [ ] **CONF-02**: Configurable check interval (default 60 min, bounds: 5 min – 24 h)
- [ ] **CONF-03**: Per-source enable/disable (pacman, AUR, flatpak)
- [ ] **CONF-04**: Configurable terminal emulator priority list
- [ ] **CONF-05**: Notification settings (enable/disable, quiet hours start/end)
- [ ] **CONF-06**: Config loaded with precedence: CLI args > env vars > config file > defaults

### Modular Update Checkers

- [ ] **CHECK-01**: Plugin ABC with `name`, `is_available()`, `check() -> list[Update]`
- [ ] **CHECK-02**: Plugin discovery via hybrid approach — built-ins auto-registered, third-party via `importlib.metadata` entry points
- [ ] **CHECK-03**: Pacman checker via `checkupdates` (with timeout and error isolation)
- [ ] **CHECK-04**: AUR checker via auto-detected `paru` or `yay`
- [ ] **CHECK-05**: Flatpak checker with version and branch info
- [ ] **CHECK-06**: Per-checker timeout (default 30s) and graceful error handling
- [ ] **CHECK-07**: Failed checker does not block other checkers

### Notification System

- [ ] **NOTIFY-01**: Desktop notification on transition from 0 to >0 updates
- [ ] **NOTIFY-02**: Notification includes source breakdown (e.g., "5 packages, 2 AUR")
- [ ] **NOTIFY-03**: No re-notification for same update count on subsequent checks
- [ ] **NOTIFY-04**: Quiet hours respected (no notifications during configured window)
- [ ] **NOTIFY-05**: Notification actions: "Run Topgrade", "Dismiss"

### Tray Applet

- [ ] **TRAY-01**: System tray icon with state: idle, checking, up-to-date, updates-available
- [ ] **TRAY-02**: Badge count on icon when updates available
- [ ] **TRAY-03**: Context menu: status, check now, view updates, run topgrade, quit
- [ ] **TRAY-04**: Left-click shows updates dialog (if updates) or runs topgrade (if none)
- [ ] **TRAY-05**: Updates dialog shows per-source breakdown with package names
- [ ] **TRAY-06**: "Run Topgrade" button in updates dialog launches terminal
- [ ] **TRAY-07**: Icon caching — do not regenerate pixmap on every check
- [ ] **TRAY-08**: Last check timestamp shown in tooltip or menu
- [ ] **TRAY-09**: Tray persists when dialog closed (`setQuitOnLastWindowClosed(False)`)

### Topgrade Integration

- [ ] **TG-01**: Launch `topgrade` in detected terminal emulator
- [ ] **TG-02**: Terminal detection: `xdg-terminal-exec`, `$TERMINAL`, then ranked fallbacks
- [ ] **TG-03**: Parse `topgrade.toml` to skip checkers disabled there

### Logging & Observability

- [ ] **LOG-01**: Rotating file log at `~/.local/share/topgrade-update/log`
- [ ] **LOG-02**: Per-checker log entries with timing and error details
- [ ] **LOG-03**: CLI `--verbose` flag for debug output

### Quality & Testing

- [ ] **QUAL-01**: Full type hints across codebase
- [ ] **QUAL-02**: `mypy --strict` passes
- [ ] **QUAL-03**: `ruff` for linting and formatting
- [ ] **QUAL-04**: Unit tests for core logic (config, checkers, engine)
- [ ] **QUAL-05**: `pytest-qt` tests for tray GUI components

## v2 Requirements

### Enhanced Features

- **NEWS-01**: Arch Linux News integration — check for news since last update
- **MAINT-01**: Post-update helper reminders (orphans, pacnew, cache cleanup)
- **REBOOT-01**: Kernel/reboot required detection after updates
- **TRAY-10**: Snooze option (pause checks for N hours)
- **TRAY-11**: Update list preview in tray menu (package names + versions)
- **I18N-01**: gettext internationalization support

### Additional Checkers

- **CHECK-08**: `fwupdmgr` firmware update checker
- **CHECK-09**: Custom command checker (user-defined scripts)

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
| PACK-01 | Phase 1 | Pending |
| PACK-02 | Phase 1 | Pending |
| PACK-03 | Phase 1 | Pending |
| PACK-04 | Phase 1 | Pending |
| CONF-01 | Phase 2 | Pending |
| CONF-02 | Phase 2 | Pending |
| CONF-03 | Phase 2 | Pending |
| CONF-04 | Phase 2 | Pending |
| CONF-05 | Phase 2 | Pending |
| CONF-06 | Phase 2 | Pending |
| CHECK-01 | Phase 3 | Pending |
| CHECK-02 | Phase 3 | Pending |
| CHECK-03 | Phase 3 | Pending |
| CHECK-04 | Phase 3 | Pending |
| CHECK-05 | Phase 3 | Pending |
| CHECK-06 | Phase 3 | Pending |
| CHECK-07 | Phase 3 | Pending |
| NOTIFY-01 | Phase 4 | Pending |
| NOTIFY-02 | Phase 4 | Pending |
| NOTIFY-03 | Phase 4 | Pending |
| NOTIFY-04 | Phase 4 | Pending |
| NOTIFY-05 | Phase 4 | Pending |
| TRAY-01 | Phase 5 | Pending |
| TRAY-02 | Phase 5 | Pending |
| TRAY-03 | Phase 5 | Pending |
| TRAY-04 | Phase 5 | Pending |
| TRAY-05 | Phase 5 | Pending |
| TRAY-06 | Phase 5 | Pending |
| TRAY-07 | Phase 5 | Pending |
| TRAY-08 | Phase 5 | Pending |
| TRAY-09 | Phase 5 | Pending |
| TG-01 | Phase 6 | Pending |
| TG-02 | Phase 6 | Pending |
| TG-03 | Phase 6 | Pending |
| LOG-01 | Phase 7 | Pending |
| LOG-02 | Phase 7 | Pending |
| LOG-03 | Phase 7 | Pending |
| QUAL-01 | Phase 8 | Pending |
| QUAL-02 | Phase 8 | Pending |
| QUAL-03 | Phase 8 | Pending |
| QUAL-04 | Phase 8 | Pending |
| QUAL-05 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 34 total
- Mapped to phases: 34
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-19*
*Last updated: 2026-05-19 after initial definition*
