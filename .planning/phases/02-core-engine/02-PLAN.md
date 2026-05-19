# Phase 2: Core Engine — Plans

**Phase:** 2 — Core Engine
**Goal:** Modular plugin architecture for update checkers with error isolation and robust subprocess handling.
**Created:** 2026-05-19

---

## Plan 1: Plugin ABC, Registry, and Discovery

**Wave:** 1
**Depends on:** None
**Autonomous:** Yes
**Requirements addressed:** CHECK-01, CHECK-02, CHECK-07

### Objective
Create the plugin infrastructure: abstract base class, provider registry with hybrid discovery (built-in auto-registration + entry_points for third-party), and update engine that orchestrates checks with error isolation.

### Tasks

#### Task 1.1: Define Provider ABC

```xml
<task>
<id>1.1</id>
<title>Define UpdateChecker ABC</title>
<read_first>
- src/topgrade_update/core/models.py
- .planning/phases/02-core-engine/02-CONTEXT.md
</read_first>
<action>
Create `src/topgrade_update/core/provider.py` with an abstract base class `UpdateChecker`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from topgrade_update.core.models import Update

class UpdateChecker(ABC):
    name: ClassVar[str]
    label: ClassVar[str]

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def check(self) -> list[Update]: ...
```

Also create `src/topgrade_update/core/engine.py` with an `UpdateEngine` class:

```python
from __future__ import annotations

import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult, Config, Update
    from topgrade_update.core.provider import UpdateChecker


class UpdateEngine:
    def __init__(self) -> None:
        self._checkers: dict[str, UpdateChecker] = {}

    def register(self, checker: UpdateChecker) -> None:
        self._checkers[checker.name] = checker

    def discover_builtin(self) -> None:
        """Auto-register built-in checkers."""
        # NOTE: imports are deferred so builtins.py can be created in Plan 2
        from topgrade_update.core.checkers.builtins import (
            AurChecker,
            FlatpakChecker,
            PacmanChecker,
        )
        for cls in (PacmanChecker, AurChecker, FlatpakChecker):
            self.register(cls())

    def discover_entry_points(self) -> None:
        """Register third-party checkers from entry_points."""
        from importlib.metadata import entry_points

        eps = entry_points(group="topgrade_update.plugins")
        for ep in eps:
            try:
                checker_cls = ep.load()
                self.register(checker_cls())
            except Exception:
                continue

    def available(self) -> Iterator[UpdateChecker]:
        for c in self._checkers.values():
            if c.is_available():
                yield c

    def check_all(self, cfg: Config | None = None) -> list[CheckResult]:
        from topgrade_update.core.models import CheckResult, Config, SourceConfig
        if cfg is None:
            cfg = Config()
        results: list[CheckResult] = []
        for checker in self.available():
            src_cfg = cfg.sources.get(checker.name, SourceConfig())
            if not src_cfg.enabled:
                continue
            start = time.monotonic()
            try:
                updates = checker.check()
                result = CheckResult(
                    source=checker.name,
                    updates=updates,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception as exc:
                result = CheckResult(
                    source=checker.name,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            results.append(result)
        return results
```

Create `src/topgrade_update/core/checkers/__init__.py` (empty for now, will be populated in Plan 2).
Create `src/topgrade_update/core/checkers/builtins.py` (empty stub for now).
</action>
<acceptance_criteria>
- `src/topgrade_update/core/provider.py` exists and contains `UpdateChecker` ABC with `name`, `is_available()`, `check()`
- `src/topgrade_update/core/engine.py` exists and contains `UpdateEngine` with `register()`, `discover_builtin()`, `discover_entry_points()`, `available()`, `check_all()`
- `mypy src/topgrade_update/core/provider.py src/topgrade_update/core/engine.py` passes
- `python -c "from topgrade_update.core.engine import UpdateEngine; e = UpdateEngine(); print(e)"` runs without error
</acceptance_criteria>
</task>
```

#### Task 1.2: Document third-party entry_points group

```xml
<task>
<id>1.2</id>
<title>Document entry_points group for third-party plugins</title>
<read_first>
- pyproject.toml
- .planning/phases/02-core-engine/02-CONTEXT.md
</read_first>
<action>
Per CONTEXT.md D-01, built-in checkers are auto-registered without entry_points. Only third-party packages use entry_points.

Document the entry_points group in `pyproject.toml` by adding a comment in the `[project]` section:

```toml
# Third-party plugins can register via:
# [project.entry-points."topgrade_update.plugins"]
# mychecker = "mypackage.plugins:MyChecker"
```

Do NOT register built-in checkers here — they are auto-discovered by UpdateEngine.discover_builtin().
</action>
<acceptance_criteria>
- `pyproject.toml` contains a comment documenting the `topgrade_update.plugins` entry_points group
- No built-in checkers are registered under entry_points
- `tomllib` can parse pyproject.toml without errors
</acceptance_criteria>
</task>
```

---

## Plan 2: Port Checkers to Plugin Classes with Process-Group Cleanup

**Wave:** 2
**Depends on:** Plan 1
**Autonomous:** Yes
**Requirements addressed:** CHECK-03, CHECK-04, CHECK-05, CHECK-06

### Objective
Port the existing pacman, AUR, and flatpak checker functions into `UpdateChecker` subclasses. Replace basic `subprocess.run()` with process-group-aware subprocess handling that kills the entire process tree on timeout.

### Tasks

#### Task 2.1: Create robust subprocess runner with process-group cleanup

```xml
<task>
<id>2.1</id>
<title>Process-group-aware subprocess runner</title>
<read_first>
- src/topgrade_update/core/checkers.py (existing subprocess code)
- .planning/research/PITFALLS.md §"1.1 Orphaned / Zombie Processes"
- .planning/phases/02-core-engine/02-CONTEXT.md
</read_first>
<action>
Create `src/topgrade_update/core/subprocess.py` with a `run_checked()` function:

```python
from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from subprocess import CompletedProcess

_DEFAULT_TIMEOUT = 30


def run_checked(
    cmd: list[str],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    capture_output: bool = True,
    text: bool = True,
) -> CompletedProcess[str]:
    """Run a command with timeout, killing the entire process group on expiry.

    Uses os.setsid to create a new process group, then os.killpg to kill
    all children (e.g. git, makepkg spawned by paru/yay) on TimeoutExpired.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=text,
        preexec_fn=os.setsid,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait()
        raise
    return subprocess.CompletedProcess(
        args=cmd,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )
```
</action>
<acceptance_criteria>
- `src/topgrade_update/core/subprocess.py` exists with `run_checked()` function
- `run_checked()` uses `preexec_fn=os.setsid` in `subprocess.Popen`
- On `TimeoutExpired`, `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` is called
- `mypy src/topgrade_update/core/subprocess.py` passes
- `python -c "from topgrade_update.core.subprocess import run_checked; print(run_checked)"` works
</acceptance_criteria>
</task>
```

#### Task 2.2: Port pacman, AUR, flatpak checkers to plugin classes

```xml
<task>
<id>2.2</id>
<title>Built-in checker plugin classes</title>
<read_first>
- src/topgrade_update/core/checkers.py (ALL existing checker functions)
- src/topgrade_update/core/subprocess.py (from Task 2.1)
- src/topgrade_update/core/provider.py (ABC from Task 1.1)
- src/topgrade_update/core/models.py
</read_first>
<action>
Write `src/topgrade_update/core/checkers/builtins.py` with three `UpdateChecker` subclasses:

```python
from __future__ import annotations

import shutil
import time
from typing import ClassVar

from topgrade_update.core.models import Update
from topgrade_update.core.provider import UpdateChecker
from topgrade_update.core.subprocess import run_checked


def _parse_checkupdates_line(line: str, source: str) -> Update | None:
    parts = line.strip().split()
    if len(parts) < 4:
        return None
    return Update(
        name=parts[0],
        old_version=parts[1],
        new_version=parts[3],
        source=source,
    )


class PacmanChecker(UpdateChecker):
    name: ClassVar[str] = "pacman"
    label: ClassVar[str] = "Pacman"

    def is_available(self) -> bool:
        return shutil.which("checkupdates") is not None

    def check(self) -> list[Update]:
        r = run_checked(["checkupdates"])
        if r.returncode != 0 or not r.stdout.strip():
            return []
        updates: list[Update] = []
        for line in r.stdout.strip().splitlines():
            up = _parse_checkupdates_line(line, self.name)
            if up:
                updates.append(up)
        return updates


class AurChecker(UpdateChecker):
    name: ClassVar[str] = "aur"
    label: ClassVar[str] = "AUR"

    def is_available(self) -> bool:
        return shutil.which("paru") is not None or shutil.which("yay") is not None

    def check(self) -> list[Update]:
        for helper in ("paru", "yay"):
            if not shutil.which(helper):
                continue
            r = run_checked([helper, "-Qua"])
            if r.returncode != 0 or not r.stdout.strip():
                return []
            updates: list[Update] = []
            for line in r.stdout.strip().splitlines():
                up = _parse_checkupdates_line(line, self.name)
                if up:
                    updates.append(up)
            return updates
        return []


class FlatpakChecker(UpdateChecker):
    name: ClassVar[str] = "flatpak"
    label: ClassVar[str] = "Flatpak"

    def is_available(self) -> bool:
        return shutil.which("flatpak") is not None

    def check(self) -> list[Update]:
        r = run_checked([
            "flatpak",
            "remote-ls",
            "--updates",
            "--columns=application,version,branch",
        ])
        if r.returncode != 0 or not r.stdout.strip():
            return []
        updates: list[Update] = []
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                updates.append(
                    Update(
                        name=parts[0],
                        old_version="?",
                        new_version=parts[1],
                        source=self.name,
                    )
                )
        return updates
```

Update `src/topgrade_update/core/checkers/__init__.py` to export:
```python
from topgrade_update.core.checkers.builtins import AurChecker, FlatpakChecker, PacmanChecker

__all__ = ["PacmanChecker", "AurChecker", "FlatpakChecker"]
```
</action>
<acceptance_criteria>
- `src/topgrade_update/core/checkers/builtins.py` exists with `PacmanChecker`, `AurChecker`, `FlatpakChecker`
- Each class inherits from `UpdateChecker` and implements `name`, `label`, `is_available()`, `check()`
- Each `check()` method returns `list[Update]` (not `CheckResult`)
- `run_checked()` is used instead of `subprocess.run()`
- `mypy src/topgrade_update/core/checkers/builtins.py` passes
- `python -c "from topgrade_update.core.checkers.builtins import PacmanChecker; c = PacmanChecker(); print(c.name, c.is_available())"` works
</acceptance_criteria>
</task>
```

---

## Plan 3: Integration and Backwards Compatibility

**Wave:** 3
**Depends on:** Plan 2
**Autonomous:** Yes
**Requirements addressed:** CHECK-07 (integration test), all success criteria

### Objective
Wire the new plugin engine into existing CLI and tray code. Ensure `check_all()` and `total_updates()` continue to work as before. Remove or deprecate the old standalone checker functions.

### Tasks

#### Task 3.1: Refactor check_all() to use UpdateEngine

```xml
<task>
<id>3.1</id>
<title>Wire UpdateEngine into existing API</title>
<read_first>
- src/topgrade_update/core/checkers.py
- src/topgrade_update/core/engine.py
- src/topgrade_update/cli/main.py
- src/topgrade_update/gui/tray.py
</read_first>
<action>
Rewrite `src/topgrade_update/core/checkers.py` to delegate to `UpdateEngine`:

```python
from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from topgrade_update.core.engine import UpdateEngine

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult, Config


def _get_engine() -> UpdateEngine:
    """Return a fully-initialized UpdateEngine."""
    engine = UpdateEngine()
    engine.discover_builtin()
    engine.discover_entry_points()
    return engine


def check_all(cfg: Config | None = None) -> list[CheckResult]:
    """Run all enabled checkers and return results."""
    return _get_engine().check_all(cfg)


def total_updates(results: list[CheckResult]) -> int:
    """Return the total number of available updates across all results."""
    return sum(len(r.updates) for r in results)


def find_terminal(cfg: Config | None = None) -> tuple[str | None, list[str]]:
    """Return (cmd, args_template) for the first available terminal."""
    from topgrade_update.core.models import Config
    if cfg is None:
        cfg = Config()
    if shutil.which("xdg-terminal-exec"):
        return "xdg-terminal-exec", []
    env_term = shutil.which(os.environ.get("TERMINAL", ""))
    if env_term:
        return env_term, ["-e"]
    for cmd in cfg.terminals:
        path = shutil.which(cmd)
        if path:
            return path, ["-e"]
    return None, []
```

Remove all old standalone checker functions (`check_pacman`, `check_aur`, `check_flatpak`, `_run`, `_parse_checkupdates_line`).
</action>
<acceptance_criteria>
- `src/topgrade_update/core/checkers.py` no longer contains `check_pacman`, `check_aur`, `check_flatpak`, `_run`
- `check_all()` delegates to `UpdateEngine.check_all()`
- `total_updates()` and `find_terminal()` are preserved
- `mypy src/topgrade_update/core/checkers.py` passes
- `python -c "from topgrade_update.core.checkers import check_all; print(check_all)"` works
</acceptance_criteria>
</task>
```

#### Task 3.2: Verify end-to-end backwards compatibility

```xml
<task>
<id>3.2</id>
<title>End-to-end verification</title>
<read_first>
- src/topgrade_update/cli/main.py
- src/topgrade_update/gui/tray.py
</read_first>
<action>
Run the following verification commands in order:

1. `mypy src/` — must pass with no errors
2. `ruff check src/` — must pass with no errors
3. `topgrade-update --list` — must show updates in same format as before (source header + package list + total)
4. `topgrade-update --check` — must return exit code 1 if updates exist, 0 if not

If any command fails, fix the issue and re-run.
</action>
<acceptance_criteria>
- `mypy src/` exits with code 0
- `ruff check src/` exits with code 0
- `topgrade-update --list` produces output matching the format:
  - Blank line, then source header (e.g., `pacman (N):` or `aur (N):`)
  - `  {name} {old_version} -> {new_version}` per update
  - `Total: {N} update(s)` at end
- `topgrade-update --check` returns exit code matching update presence
</acceptance_criteria>
</task>
```

---

## Plan Summary

| Plan | Wave | Objective | Requirements |
|------|------|-----------|-------------|
| 1 | 1 | Plugin ABC, registry, discovery | CHECK-01, CHECK-02, CHECK-07 |
| 2 | 2 | Port checkers with process-group cleanup | CHECK-03, CHECK-04, CHECK-05, CHECK-06 |
| 3 | 3 | Integration and backwards compatibility | All (verification) |

## Must-Haves for Phase Success

1. `UpdateChecker` ABC exists with `name`, `is_available()`, `check()`
2. `UpdateEngine` can discover built-ins and entry_points plugins
3. Each built-in checker uses `run_checked()` with `os.setsid` + `os.killpg()`
4. `check_all()` returns same output format as before
5. `topgrade-update --list` and `--check` work identically to pre-refactor
6. `mypy` and `ruff` pass on all modified files
