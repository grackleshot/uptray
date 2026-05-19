# Roadmap: Topgrade Update

**Created:** 2026-05-19
**Granularity:** Coarse (4 phases)
**Execution:** Parallel plans within phases

---

## Phase 1: Foundation
**Goal:** Professional project structure with packaging, configuration, and quality tooling in place.

**Requirements:** PACK-01 through PACK-04, CONF-01 through CONF-06, QUAL-01 through QUAL-03

**Success Criteria:**
1. `pip install -e .` installs the package with working CLI entry point
2. `topgrade-update --help` works without PySide6 installed
3. Config file is created, loaded, and respected at runtime
4. `mypy --strict` and `ruff check` pass on all new code
5. Existing CLI behavior (`--check`, `--list`, default run) is preserved

**Plans:**
1. **Project skeleton** — `src/topgrade_update/` layout, `pyproject.toml`, hatchling backend, entry points, `__main__.py`
2. **Config system** — TOML loader, dataclass schema, XDG paths, precedence chain
3. **Type hints & tooling** — Add annotations to all new code, configure mypy + ruff

**Dependencies:** None (first phase)

---

## Phase 2: Core Engine
**Goal:** Modular plugin architecture for update checkers with error isolation and robust subprocess handling.

**Requirements:** CHECK-01 through CHECK-07

**Success Criteria:**
1. New checkers can be added by implementing the ABC and registering an entry point
2. Pacman, AUR, and Flatpak checkers run in isolation — one failure doesn't break others
3. Each checker respects a 30-second timeout and cleans up subprocesses on timeout
4. Results are returned as structured `Update` objects, not raw strings
5. `topgrade-update --list` uses the new plugin engine and produces same output

**Plans:**
1. **Plugin ABC & discovery** — Define `UpdateChecker` base class, `Update` dataclass, `importlib.metadata` loader
2. **Built-in checkers** — Port pacman, AUR, flatpak checkers to plugin classes with error isolation
3. **Update engine** — Orchestrator that runs enabled plugins, aggregates results, handles timeouts

**Dependencies:** Phase 1 (config system needed for per-source enable/disable)

---

## Phase 3: User Experience
**Goal:** Rich tray applet, smart notifications, and seamless topgrade integration.

**Requirements:** NOTIFY-01 through NOTIFY-05, TRAY-01 through TRAY-09, TG-01 through TG-03

**Success Criteria:**
1. Tray icon shows correct state and badge count after each check
2. Notification fires only on 0→N transitions, includes source breakdown
3. Quiet hours suppress notifications during configured window
4. Left-click opens updates dialog; right-click menu has all actions
5. "Run Topgrade" launches in detected terminal with `xdg-terminal-exec` fallback
6. `topgrade.toml` is parsed and disabled steps are skipped in checkers

**Plans:**
1. **Notification system** — DBus-based notifications with actions, deduplication, quiet hours
2. **Tray applet refactor** — Port to PySide6, icon caching, state management, updates dialog
3. **Topgrade integration** — Terminal detection, `topgrade.toml` parsing, launch logic

**Dependencies:** Phase 2 (update engine provides data for tray and notifications)

---

## Phase 4: Polish & Quality
**Goal:** Logging, tests, and final code quality to ship a maintainable v1.

**Requirements:** LOG-01 through LOG-03, QUAL-04 through QUAL-05

**Success Criteria:**
1. Logs are written to rotating file with per-checker timing and errors
2. `--verbose` CLI flag enables debug output to stderr
3. Unit tests cover config, checkers, and update engine with mocked subprocess
4. `pytest-qt` tests verify tray icon states and menu actions
5. CI-ready: `pytest`, `mypy`, `ruff` all pass

**Plans:**
1. **Logging** — Rotating file handler, per-module loggers, verbose CLI flag
2. **Unit tests** — Test config loading, plugin discovery, checker mocks, engine aggregation
3. **GUI tests** — `pytest-qt` tests for tray initialization, state changes, dialog actions

**Dependencies:** Phases 1-3 (all prior code must exist to test)

---

## Cross-Cutting Concerns

### Security (addressed in Phase 2)
- All subprocess calls use list args, never `shell=True`
- Timeouts use process-group killing to prevent zombies
- Input validation on config-derived paths and commands

### Performance (addressed in Phase 3)
- Icon pixmap caching to avoid regeneration every check
- Subprocess timeouts prevent indefinite hangs
- Notification deduplication reduces DBus traffic

### Backwards Compatibility (addressed in Phase 1)
- All existing CLI flags (`--check`, `--list`, `--tray`, `--enable`, `--disable`) preserved
- Default behavior (run topgrade) unchanged
- Autostart `.desktop` file format unchanged

---

## Phase Summary

| Phase | Name | Requirements | Plans | Dependencies |
|-------|------|--------------|-------|--------------|
| 1 | Foundation | 13 | 3 | — |
| 2 | Core Engine | 7 | 3 | Phase 1 |
| 3 | User Experience | 17 | 3 | Phase 2 |
| 4 | Polish & Quality | 8 | 3 | Phases 1-3 |

**Total:** 4 phases | 45 requirements | 12 plans
