# Topgrade Update

## What This Is

A desktop update notifier and system tray applet for Linux that checks pacman, AUR, Flatpak, firmware, and reboot state for available updates and launches `topgrade` to apply them. Provides both CLI and GUI (PySide6 tray icon) interfaces.

## Core Value

Users never miss available system updates because the tray applet silently checks and clearly surfaces them.

## Requirements

### Validated

- ✓ Check pacman updates via `checkupdates` — existing
- ✓ Check AUR updates via `paru` or `yay` — existing
- ✓ Check flatpak updates — existing
- ✓ Send desktop notifications via `notify-send` — existing
- ✓ PySide6 system tray applet with badge counter — Phase 1
- ✓ Launch `topgrade` in detected terminal — existing
- ✓ XDG autostart via `.desktop` file — existing
- ✓ CLI: `--check`, `--list`, default run modes — existing
- ✓ Modular package structure (`src/topgrade_update/`) — Phase 1
- ✓ `pyproject.toml` with hatchling, entry points, `[gui]` extras — Phase 1
- ✓ TOML config with XDG paths, validation, and CLI > env > file > defaults precedence — Phase 1
- ✓ DBus notification actions with plain notification fallback — Phase 3
- ✓ Full type hints, mypy strict, ruff — Phase 1
- ✓ Plugin ABC (`UpdateChecker`) with `name`, `is_available()`, `check()` — Phase 2
- ✓ Hybrid plugin discovery (built-in auto + entry_points third-party) — Phase 2
- ✓ Process-group killing on subprocess timeout (`start_new_session` + `os.killpg`) — Phase 2
- ✓ Per-checker error isolation (failed checker doesn't block others) — Phase 2
- ✓ Flatpak checker with version/branch info — Phase 2
- ✓ Backwards-compatible `check_all()` API via `UpdateEngine` — Phase 2
- ✓ Snooze persistence across restarts (XDG_STATE_HOME state file) — 2026-11
- ✓ Sound support for notifications (DBus sound hint + notify-send flag) — 2026-11
- ✓ Dry-run preview before topgrade (`--dry-run` from tray/dialog) — 2026-11
- ✓ Arch Linux news integration (NEWS-01): feed reader, [NEW] markers, read tracking — 2026-11
- ✓ Post-update helper reminders (MAINT-01): orphans, pacnew/pacsave, cache size — 2026-11
- ✓ pacman database watcher (re-check after manual upgrades) — 2026-11
- ✓ Resume-from-suspend + offline awareness — 2026-11
- ✓ Update history view (pacman.log session parser + dialog) — 2026-11
- ✓ Settings GUI dialog — 2026-11
- ✓ Colorblind icon variants + reboot icon state — 2026-11
- ✓ Reboot-required critical notification — 2026-11
- ✓ Parallel checker execution — 2026-11
- ✓ topgrade.toml alignment: `misc.only`, `topgrade.d/` merge, pikaur AUR helper — 2026-11
- ✓ Single-instance tray lock — 2026-11
- ✓ systemd user timer for headless checks — 2026-11
- ✓ In-app run window with Simple/Verbose views, prompt bar with typed answers, and failure reasons — 2026-11
- ✓ Closing the run window keeps the update running; Cancel asks first — 2026-11
- ✓ Dry run to "Run for real" handoff — 2026-11
- ✓ History window Runs tab (past run transcripts) — 2026-11
- ✓ "Update only this source" from the Updates dialog — 2026-11
- ✓ Remembered window geometry and keyboard shortcuts (Esc, Ctrl+1/2, Ctrl+F) — 2026-11
- ✓ Honest counts: reboot not counted as an update; missing pacman-contrib surfaced — 2026-11
- ✓ Settings polish (autostart toggle, interval in minutes, Restore Defaults) and CLI `--version` with exit-code docs — 2026-11

### Active

- [ ] i18n / gettext support (infrastructure not yet wrapped)

### Out of Scope

- macOS/Windows support — Linux-only focus for now
- Mobile app or web UI — desktop-only
- Package manager installation (AUR/PKGBUILD) — user handles deployment
- Real-time update streams — polling-based is sufficient
- Non-topgrade upgrade paths — topgrade is the intended tool

## Context

Started as a single ~400-line Python monolith. Evolved into a modular Python package with:
- 32 source files, 133+ tests, full type checking
- Plugin architecture with 5 built-in checkers (parallel execution) + entry point extensibility
- System tray applet with badge, snooze (persistent), per-source package menus, news, history
- Arch news feed integration with read markers
- Post-update maintenance reminders (orphans, pacnew, cache)
- Event-driven checks (pacman DB watcher, resume-from-suspend, offline gating)
- Rotating file logging with per-checker timing
- Desktop integration (SVG icon, .desktop file, install script, optional systemd timer)
- CI/CD with GitHub Actions (5 Python versions)
- Comprehensive documentation (README, architecture docs)

## Constraints

- **Tech stack**: Python 3 + PySide6 for tray; keep existing topgrade integration
- **Compatibility**: Must not break existing CLI flags or tray behavior
- **Scope**: Refactor and enhance; not a rewrite
- **Platform**: Linux desktop environments with system tray support

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| PySide6 over PyQt6 | LGPL license, official Qt bindings, drop-in replacement | ✓ Good |
| Single-file → package | Enables testing, modular checkers, installability | ✓ Good |
| TOML for config | Standard Python config format, human-editable | ✓ Good |
| hatchling build backend | Modern PEP 517, fast, handles entry points cleanly | ✓ Good |
| Hybrid plugin discovery | Built-ins auto-registered, third-party via entry_points | ✓ Good |
| Process-group killing | `start_new_session=True` + `os.killpg()` cleans up child processes | ✓ Good |
| Sequential execution | Simple, predictable, no threading complexity | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check - still the right priority?
3. Audit Out of Scope - reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-28 after implementation review*

## Quality Metrics (2026-10-28, post-review)

| Metric | Value |
|--------|-------|
| Source files | 25 |
| Test files | 12 |
| Tests | 58 |
| `ruff check` | All passed |
| `mypy --strict` | 0 issues |
| CI/CD | GitHub Actions (5 Python versions) |
| Icon | SVG, scalable |
| Desktop integration | .desktop file, install script |
| Logging | Rotating file, per-checker timing |
| CLI flags | `--check`, `--list`, `--tray`, `--verbose`, `--json`, `--enable`, `--disable` |
