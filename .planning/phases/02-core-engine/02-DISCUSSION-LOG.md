# Phase 2: Core Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 02-core-engine
**Areas discussed:** Plugin discovery depth, Subprocess cleanup, Checker parallelism

---

## Plugin Discovery Depth

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Built-in only | ABC in core/, plain classes, no entry_points | |
| B — Full entry_points | Built-ins registered in pyproject.toml, third-party via entry_points | |
| C — Hybrid | Built-ins auto-registered, third-party via entry_points | ✓ |

**User's choice:** C — Hybrid
**Notes:** User wants extensibility without forcing built-ins to register via entry_points. Third-party packages can still add checkers by registering entry_points.

---

## Subprocess Cleanup

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Basic timeout | subprocess.run(timeout=30), may leave orphans | |
| B — Process-group killing | os.setsid + os.killpg(), kills entire tree on timeout | ✓ |

**User's choice:** B — Process-group killing
**Notes:** Chose robustness over simplicity. AUR helpers (paru/yay) spawn git and makepkg, so orphan prevention matters.

---

## Checker Parallelism

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Sequential | Run one checker at a time, predictable order | ✓ |
| B — Concurrent | ThreadPoolExecutor, faster but more complex | |
| C — Sequential with early exit | Skip slow checkers if fast one found updates | |

**User's choice:** A — Sequential
**Notes:** Simplicity preferred. checkupdates is fast; AUR/flatpak slow but tolerable. No need for threading complexity in core engine.

---

## the agent's Discretion

- Exact module layout for built-in checker classes
- Plugin registry implementation (dict vs list)
- is_available() caching strategy
- Timeout default value
- Whether to log subprocess stderr on failure

## Deferred Ideas

- Concurrent checker execution — Phase 3 or v2
- Plugin dependency ordering — not needed yet
- Per-plugin configuration beyond `enabled` — defer until needed
