# Phase 2: Core Engine - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Modular plugin architecture for update checkers with error isolation and robust subprocess handling. Refactor existing standalone checker functions into a plugin system where each source (pacman, AUR, flatpak) implements a common interface. The update engine orchestrates checks, aggregates results, and ensures one failing checker doesn't break the others.

</domain>

<decisions>
## Implementation Decisions

### Plugin Discovery Depth
- **D-01:** Hybrid approach — built-in checkers auto-registered without `pyproject.toml` entry_points, third-party checkers discovered via `importlib.metadata.entry_points(group="topgrade_update.plugins")`
- Built-ins live in `src/topgrade_update/core/checkers/` and are imported/registered automatically
- Third-party packages register via `[project.entry-points."topgrade_update.plugins"]` in their own `pyproject.toml`

### Subprocess Cleanup
- **D-02:** Process-group killing on timeout — use `preexec_fn=os.setsid` when spawning subprocesses, kill entire process group with `os.killpg()` on `TimeoutExpired`
- Prevents orphaned children from `paru`/`yay` which spawn `git` and `makepkg`
- Always call `proc.communicate()` or `proc.wait()` after kill to reap zombies

### Checker Parallelism
- **D-03:** Sequential execution — run checkers one at a time (pacman → AUR → flatpak)
- Predictable output order, no threading complexity in core engine
- Total check time acceptable since `checkupdates` is fast; AUR/flatpak are the slow ones but still tolerable

### Plugin Interface
- **D-04:** ABC-based interface with three methods:
  - `name() -> str` — human-readable source name
  - `is_available() -> bool` — whether the checker can run in this environment
  - `check() -> list[Update]` — perform the check, return available updates
- Return type is `list[Update]` (not `CheckResult`) — the engine wraps it in `CheckResult` with timing/error info

### Error Isolation
- **D-05:** Each checker runs in its own `try/except` block within the engine
- Failed checkers return `CheckResult` with `error` field set, never raise through the engine
- Engine collects all results and returns them — caller decides how to handle failures

### the agent's Discretion
- Exact class/module layout for built-in checkers
- Whether to use a registry dict or a list for built-in plugins
- How to handle `is_available()` caching (call every time vs cache at startup)
- Timeout default value (research suggests 30s, but can adjust)
- Whether to log subprocess stderr on failure

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Plugin Design
- `.planning/research/ARCHITECTURE.md` §"Plugin Architecture Design" — `importlib.metadata` discovery, ABC interface, loading lifecycle
- `.planning/research/STACK.md` — PySide6, hatchling, stdlib-only plugins recommendation

### Pitfalls to Avoid
- `.planning/research/PITFALLS.md` §"1.1 Orphaned / Zombie Processes on Timeout" — `preexec_fn=os.setsid`, `os.killpg()` pattern
- `.planning/research/PITFALLS.md` §"1.2 Blocking the Event Loop" — keep subprocess I/O in worker threads, not main thread
- `.planning/research/PITFALLS.md` §"1.3 Shell Injection" — always pass commands as lists, never `shell=True`

### Existing Code
- `src/topgrade_update/core/models.py` — `Update`, `CheckResult`, `Config` dataclasses
- `src/topgrade_update/core/checkers.py` — current standalone checker functions (to be refactored into plugin classes)
- `src/topgrade_update/core/config.py` — config loading with per-source enable/disable

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Update` dataclass — already has `name`, `old_version`, `new_version`, `source` fields
- `CheckResult` dataclass — already has `source`, `updates`, `error`, `duration_ms` fields
- `_parse_checkupdates_line()` — can be reused by pacman and AUR plugin classes
- `_run()` helper — can become a method on the base class or a utility function

### Established Patterns
- Subprocess calls via `subprocess.run()` with `capture_output=True, text=True`
- Error handling via `try/except` + setting `result.error` string
- Duration tracking via `time.monotonic()` in milliseconds

### Integration Points
- `check_all()` in `core/checkers.py` becomes the `UpdateEngine` class
- CLI (`cli/main.py`) calls `check_all(cfg)` — interface should remain compatible
- Tray (`gui/tray.py`) calls `check_all(cfg)` via `CheckThread` — same interface

</code_context>

<specifics>
## Specific Ideas

- Keep the plugin interface minimal — three methods max. Don't over-engineer lifecycle hooks.
- The `Update` dataclass already captures structured data; the refactor is mostly about wrapping existing functions in classes.
- `find_terminal()` should probably move out of `checkers.py` — it's not a checker, it's a launcher utility.

</specifics>

<deferred>
## Deferred Ideas

- Concurrent checker execution (ThreadPoolExecutor) — deferred to Phase 3 or v2; sequential is sufficient for now
- Plugin dependency ordering (e.g., flatpak before AUR) — not needed with only 3 built-in sources
- Plugin configuration schema (beyond `enabled: bool`) — defer until a plugin actually needs it

</deferred>

---

*Phase: 02-core-engine*
*Context gathered: 2026-05-19*
