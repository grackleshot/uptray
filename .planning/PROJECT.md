# Topgrade Update

## What This Is

A desktop update notifier and system tray applet for Linux that checks pacman, AUR, and flatpak for available updates and launches `topgrade` to apply them. Provides both CLI and GUI (PyQt6 tray icon) interfaces.

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
- ✓ TOML config with XDG paths and precedence chain — Phase 1
- ✓ Full type hints, mypy strict, ruff — Phase 1
- ✓ Plugin ABC (`UpdateChecker`) with `name`, `is_available()`, `check()` — Phase 2
- ✓ Hybrid plugin discovery (built-in auto + entry_points third-party) — Phase 2
- ✓ Process-group killing on subprocess timeout (`os.setsid` + `os.killpg`) — Phase 2
- ✓ Per-checker error isolation (failed checker doesn't block others) — Phase 2
- ✓ Flatpak checker with version/branch info — Phase 2
- ✓ Backwards-compatible `check_all()` API via `UpdateEngine` — Phase 2

### Active

- [ ] Richer notifications (actions, quiet hours, sound)
- [ ] Tray enhancements (per-source breakdown, snooze)
- [ ] Topgrade integration (respect `topgrade.toml`, dry-run preview)
- [ ] Logging with rotation to `~/.local/share/topgrade-update/`
- [ ] Unit and GUI tests

### Out of Scope

- macOS/Windows support — Linux-only focus for now
- Mobile app or web UI — desktop-only
- Package manager installation (AUR/PKGBUILD) — user handles deployment
- Real-time update streams — polling-based is sufficient
- Non-topgrade upgrade paths — topgrade is the intended tool

## Context

Single ~400-line Python monolith. Works well for daily use but lacks extensibility. No test suite, no config, hardcoded behaviors. The user wants to professionalize the codebase while preserving the simple UX that works.

## Constraints

- **Tech stack**: Python 3 + PyQt6 for tray; keep existing topgrade integration
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
| Process-group killing | `os.setsid` + `os.killpg()` prevents zombie children | ✓ Good |
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
*Last updated: 2026-05-19 after Phase 2*
