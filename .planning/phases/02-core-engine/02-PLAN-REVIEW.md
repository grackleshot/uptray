# Plan Review: Phase 2 — Core Engine

**Reviewer:** subagent review  
**Date:** 2026-05-19  
**Plan:** `.planning/phases/02-core-engine/02-PLAN.md`

---

## VERDICT: ISSUES FOUND

The plan is well-structured and covers all required tasks, but it contains **three concrete code bugs** that will cause `mypy` or runtime failures, and it **contradicts an explicit architecture decision** in `02-CONTEXT.md`.

---

## Correct (what passes)

- **Task structure:** All 6 tasks (1.1, 1.2, 2.1, 2.2, 3.1, 3.2) contain `<read_first>`, `<action>`, and `<acceptance_criteria>` fields.
- **Action concreteness:** Every action includes exact code snippets (full module contents), exact TOML additions, or exact shell commands. No vague references.
- **Acceptance criteria verifiability:** Most criteria are grep-verifiable or command-verifiable. Task 3.2 uses runtime behavior verification, which is appropriate for end-to-end testing.
- **Requirement coverage:** CHECK-01 through CHECK-07 are all addressed:
  - CHECK-01 → Task 1.1 (`UpdateChecker` ABC)
  - CHECK-02 → Task 1.2 (entry_points registration)
  - CHECK-03 → Task 2.2 (`PacmanChecker`)
  - CHECK-04 → Task 2.2 (`AurChecker` with `paru`/`yay` auto-detect)
  - CHECK-05 → Task 2.2 (`FlatpakChecker` with `--columns=application,version,branch`)
  - CHECK-06 → Task 2.1 (`run_checked()` with 30s default timeout)
  - CHECK-07 → Task 1.1 (`check_all()` try/except per checker)
- **Dependencies:** Plan 2 correctly depends on Plan 1; Plan 3 correctly depends on Plan 2.
- **CONTEXT.md decisions — covered:**
  - **Process-group killing (D-02):** Task 2.1 implements `preexec_fn=os.setsid` + `os.killpg()` on `TimeoutExpired` exactly as specified.
  - **Sequential execution (D-03):** Task 1.1 `check_all()` iterates `self.available()` in a single loop with no concurrency.
  - **Error isolation (D-05):** Task 1.1 `check_all()` wraps each `checker.check()` in its own `try/except`, converting exceptions to `CheckResult.error` without halting the engine.

---

## Blockers (must fix before execution)

### BLOCKER-1: Task 1.1 — `provider.py` missing `Update` import
**Location:** Task 1.1, `src/topgrade_update/core/provider.py` snippet
**Issue:** `UpdateChecker.check()` is annotated `-> list[Update]`, but `Update` is never imported.
**Impact:**
- `mypy --strict` fails with an undefined name error.
- On Python 3.10–3.13 (project target is `>=3.10`), without `from __future__ import annotations`, this raises `NameError` at class-definition time.
**Fix:** Add `from topgrade_update.core.models import Update` to the module imports.

### BLOCKER-2: Task 1.1 — `engine.py` missing runtime `Config` import
**Location:** Task 1.1, `src/topgrade_update/core/engine.py` snippet, `check_all()` method
**Issue:** The method body does `cfg = Config()`, but `Config` is only imported inside `if TYPE_CHECKING:`.
**Impact:** Calling `UpdateEngine().check_all()` without arguments raises `NameError: name 'Config' is not defined`.
**Fix:** Change the inside-method import to:
```python
from topgrade_update.core.models import CheckResult, SourceConfig, Config
```

### BLOCKER-3: Task 1.1 — `discover_builtin()` imports from empty stub
**Location:** Task 1.1, `src/topgrade_update/core/engine.py` snippet, `discover_builtin()`
**Issue:** The method imports `PacmanChecker`, `AurChecker`, `FlatpakChecker` from `builtins.py`, but the same task instructs the agent to create `builtins.py` as an **empty stub** ("will be populated in Plan 2"). The acceptance criteria explicitly require `mypy src/topgrade_update/core/engine.py` to pass.
**Impact:** `mypy` fails with `attr-defined` / import errors because the module exports no such names.
**Fix options (pick one):**
1. Do **not** create `builtins.py` in Task 1.1. Create it in Task 2.2 instead. In Task 1.1, leave `discover_builtin()` as a `pass` with a `# TODO: populate in Plan 2` comment.
2. Keep the empty stub but defer the `discover_builtin()` implementation to Task 2.2 as well.
3. Create `builtins.py` in Task 1.1 with minimal `UpdateChecker` stubs so the imports resolve.

Option 1 is cleanest and avoids the contradiction.

### BLOCKER-4: Task 1.2 — Built-in entry_points registration violates CONTEXT D-01
**Location:** Task 1.2, `pyproject.toml` entry_points addition
**Issue:** `02-CONTEXT.md` Decision **D-01** states:
> "Hybrid approach — built-in checkers auto-registered **without pyproject.toml entry_points**, third-party checkers discovered via `importlib.metadata.entry_points`"

Task 1.2 adds built-in checkers (`pacman`, `aur`, `flatpak`) to `[project.entry-points."topgrade_update.plugins"]`, directly contradicting D-01.
**Impact:**
- Built-ins are registered twice (once by `discover_builtin()`, once by `discover_entry_points()`), which is redundant.
- Violates an explicit architecture decision recorded for this phase.
**Fix:** Remove Task 1.2 entirely, or repurpose it to document the entry_points group for **third-party** plugins only (without adding built-in entries).

---

## Notes (risks, observations, follow-ups)

### NOTE-1: Backwards-compatibility gap for unavailable checkers
**Location:** Task 1.1 `available()` + Task 3.1
**Issue:** The existing `check_all()` always returns a `CheckResult` for every enabled source. If a tool is missing, the checker sets `result.error = "...not found"`. The plan filters out unavailable checkers in `UpdateEngine.available()`, so missing tools produce **no result at all**.
**Impact:** Callers that expect a fixed-length result list (or count sources by `len(results)`) will see different behavior. The plan states "Ensure `check_all()` and `total_updates()` continue to work as before" but does not acknowledge this semantic shift.
**Mitigation:** Acceptable for CLI/tray (they only render `r.updates`), but document the change in the plan or acceptance criteria.

### NOTE-2: AUR source name changes from `"AUR"` to `"aur"`
**Location:** Task 2.2 `AurChecker.name`
**Issue:** Existing code uses `source="AUR"` (uppercase). The plan uses `name = "aur"` (lowercase). This fixes a latent bug where the existing `check_all()` looked up `"AUR"` in `cfg.sources` but `Config` stores the key as `"aur"`. However, it changes the visible source header in `--list` output from `AUR (N):` to `aur (N):`.
**Impact:** Minor UI change. Task 3.2 acceptance criteria should be updated to expect `"aur"` instead of `"AUR"`.

### NOTE-3: Flatpak branch column requested but not stored
**Location:** Task 2.2 `FlatpakChecker`
**Issue:** The checker passes `--columns=application,version,branch` but only consumes the first two columns. `Update` dataclass has no `branch` field.
**Impact:** CHECK-05 mentions "version and branch info," but the model does not support storing branch. This is a faithful port of existing code, not a new regression. Consider extending `Update` in a future phase if branch display is required.

### NOTE-4: REQUIREMENTS.md CHECK-02 conflicts with CONTEXT.md D-01
**Location:** Meta
**Issue:** `REQUIREMENTS.md` CHECK-02 says "Built-in plugins registered via `importlib.metadata` entry points". `CONTEXT.md` D-01 says built-ins should **not** use entry_points. The plan satisfies the requirement but violates the context.
**Recommendation:** Resolve the conflict at the project level. If D-01 is authoritative, update REQUIREMENTS.md. If CHECK-02 is authoritative, update CONTEXT.md. Do not leave the documents in conflict.

### NOTE-5: Task 3.2 CLI verification assumes installed package
**Location:** Task 3.2 acceptance criteria
**Issue:** Commands like `topgrade-update --list` require the package to be installed in the current environment (editable or otherwise). The plan does not mention installing the package before running these commands.
**Mitigation:** Add a prerequisite step: `python -m pip install -e .` or `hatch run`.

---

## Summary

| Check | Status | Notes |
|-------|--------|-------|
| Every task has required fields | PASS | All 6 tasks have `<read_first>`, `<action>`, `<acceptance_criteria>` |
| Actions are concrete | PASS | Full code, exact TOML, exact shell commands |
| Acceptance criteria grep-verifiable | PASS | Most are grep/command verifiable; 3.2 is behavior-verifiable |
| CHECK-01..CHECK-07 covered | PASS | All 7 requirements mapped to tasks |
| Dependencies correct | PASS | Plan 1 → Plan 2 → Plan 3 chain is correct |
| Plan executable without ambiguity | **FAIL** | 3 code bugs + 1 architecture contradiction block execution as written |
| Hybrid plugin discovery (D-01) | **FAIL** | Covered in code but contradicts D-01 by adding built-ins to entry_points |
| Process-group killing (D-02) | PASS | Task 2.1 implements `os.setsid` + `os.killpg` correctly |
| Sequential execution (D-03) | PASS | Task 1.1 `check_all()` is a plain `for` loop |
| Error isolation (D-05) | PASS | Task 1.1 `try/except` per checker, exceptions converted to `CheckResult.error` |

**Recommended next step:** Fix BLOCKER-1 through BLOCKER-4, then the plan is ready for execution.
