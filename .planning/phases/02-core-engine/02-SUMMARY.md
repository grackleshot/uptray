---
phase: 02-core-engine
plan: "02"
subsystem: core
tags: [abc, plugin, importlib, subprocess, process-group, discovery]

requires:
  - phase: 01-foundation
    provides: project structure, packaging, config system

provides:
  - UpdateChecker ABC with name, is_available, check interface
  - UpdateEngine with built-in and entry_points plugin discovery
  - run_checked subprocess helper with process-group cleanup on timeout
  - PacmanChecker, AurChecker, FlatpakChecker plugin implementations
  - Backwards-compatible check_all facade preserving CLI and tray contracts

affects:
  - 03-user-experience
  - 04-polish-quality

tech-stack:
  added: []
  patterns:
    - "ABC-based plugin interface with hybrid discovery"
    - "Process-group subprocess cleanup with os.setsid + os.killpg"
    - "Error isolation: per-checker try/except wrapping in engine"

key-files:
  created:
    - src/topgrade_update/core/provider.py
    - src/topgrade_update/core/engine.py
    - src/topgrade_update/core/subprocess.py
    - src/topgrade_update/core/checkers/builtins.py
    - src/topgrade_update/core/checkers/facade.py
  modified:
    - src/topgrade_update/core/checkers/__init__.py
    - pyproject.toml

key-decisions:
  - "Hybrid plugin discovery: built-ins auto-registered without entry_points, third-party via importlib.metadata"
  - "Process-group killing on timeout to prevent orphaned git/makepkg children from AUR helpers"
  - "Sequential checker execution to maintain predictable output order"
  - "Checker returns list[Update], engine wraps in CheckResult with timing/errors"

patterns-established:
  - "Plugin ABC: minimal three-method interface (name, is_available, check)"
  - "Subprocess safety: preexec_fn=os.setsid + os.killpg on TimeoutExpired"
  - "Facade pattern: checkers package re-exports compatible API for CLI/tray"

requirements-completed: [CHECK-01, CHECK-02, CHECK-03, CHECK-04, CHECK-05, CHECK-06, CHECK-07]

duration: N/A
completed: 2026-05-19
---

# Phase 2: Core Engine Summary

**Plugin-based update checker architecture with process-group subprocess cleanup, error isolation, and backwards-compatible CLI/tray integration**

## Performance

- **Duration:** N/A (executed across multiple sessions)
- **Started:** 2026-05-19
- **Completed:** 2026-05-19
- **Tasks:** 6
- **Files modified:** 8

## Accomplishments

- Abstract `UpdateChecker` base class with `name`, `label`, `is_available()`, and `check()` interface
- `UpdateEngine` orchestrates discovery (built-in + entry_points), execution, and error isolation
- `run_checked()` subprocess helper kills entire process groups on timeout via `os.setsid`/`os.killpg`
- Pacman, AUR (paru/yay), and Flatpak checkers ported to plugin classes with shared line parser
- Old standalone `checkers.py` refactored into `checkers/` package with facade preserving `check_all()` API
- `topgrade-update --list` and `--check` produce identical output to pre-refactor version

## Task Commits

1. **Task 1.1: Define UpdateChecker ABC** — `2ed7cf6` (feat)
2. **Task 1.2: Document entry_points group** — `2ed7cf6` (feat)
3. **Task 2.1: Process-group-aware subprocess runner** — `0744543` (feat)
4. **Task 2.2: Built-in checker plugin classes** — `0744543` (feat)
5. **Task 3.1: Wire UpdateEngine into existing API** — `7bcb2a9` (feat)
6. **Task 3.2: End-to-end backwards compatibility verification** — `7bcb2a9` (feat)

## Files Created/Modified

- `src/topgrade_update/core/provider.py` — `UpdateChecker` ABC
- `src/topgrade_update/core/engine.py` — `UpdateEngine` with discovery and orchestration
- `src/topgrade_update/core/subprocess.py` — `run_checked()` with process-group cleanup
- `src/topgrade_update/core/checkers/builtins.py` — `PacmanChecker`, `AurChecker`, `FlatpakChecker`
- `src/topgrade_update/core/checkers/facade.py` — Backwards-compatible `check_all()` facade
- `src/topgrade_update/core/checkers/__init__.py` — Package exports
- `pyproject.toml` — Added entry_points comment for third-party plugins

## Decisions Made

- **Hybrid discovery** (D-01): Built-ins auto-imported from `checkers.builtins`, third-party via `topgrade_update.plugins` entry_points group
- **Process-group cleanup** (D-02): `preexec_fn=os.setsid` in `Popen`, `os.killpg()` on `TimeoutExpired` to prevent zombies from AUR helpers
- **Sequential execution** (D-03): Checkers run one at a time for predictable output order
- **Minimal plugin interface** (D-04): Three methods only — no lifecycle hooks, no configuration schema beyond `enabled`
- **Error isolation** (D-05): Per-checker `try/except` in engine, failures captured in `CheckResult.error` without propagating

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Core engine ready for tray applet and notification system integration (Phase 3)
- Plugin interface stable — new checkers can be added by subclassing `UpdateChecker`
- Backwards compatibility verified — existing CLI and tray code work unchanged

---
*Phase: 02-core-engine*
*Completed: 2026-05-19*
