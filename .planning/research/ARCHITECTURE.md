# Research: Architecture Patterns for Modular Python Desktop Applications

## Summary

For a ~400-line monolithic script refactored into a maintainable desktop app, the recommended architecture is a **src-layout package** with `core/` (business logic), `cli/` and `gui/` (thin presentation layers), a lightweight **entry-points plugin system** using `importlib.metadata`, **TOML + dataclasses** for config, and **QThread worker objects** for background tasks. Optional GUI dependencies are declared via `pyproject.toml` extras and gated at runtime with `try/except ImportError`.

---

## Findings

### 1. Package Layout & Entry Points

1. **Use a `src/` layout** — separates installable package from tests/docs and prevents accidental imports from the working directory. [Source](https://packaging.python.org/en/latest/specifications/entry-points/)
2. **Define CLI entry points in `pyproject.toml`** under `[project.scripts]` (e.g., `myapp = "myapp.cli:main"`). For `python -m myapp` support, add a `src/myapp/__main__.py` that calls the CLI main. [Source](https://develop.kde.org/docs/getting-started/python/python-package/)
3. **Keep `main.py` minimal** — it should only construct `QApplication` and show the main window. All business logic lives elsewhere. [Source](https://www.pythonguis.com/faq/structuring-a-large-pyqt-application/)

### 2. CLI / GUI / Core Separation

4. **Split into three layers**: `core/` (pure Python business logic), `cli/` (argument parsing + orchestration), and `gui/` (PyQt6 widgets). Both CLI and GUI import from `core` only; `core` never imports CLI or GUI. [Source](https://stackoverflow.com/questions/2857634/how-can-i-create-a-gui-on-top-of-a-python-app-so-it-can-do-either-gui-or-cli)
5. **Use an abstract UI boundary only if needed** — for a small app, direct function calls from `cli.py` / `gui.py` into `core.py` are sufficient. MVC adds indirection that may not be warranted until the app grows. [Source](https://stackoverflow.com/questions/4522218/python-separate-program-logic-and-gui-code)
6. **The CLI layer is the only place that calls `sys.exit()`** — deeper code raises typed exceptions (`ConfigError`, `UpdateError`) which the CLI catches and maps to exit codes. The GUI catches them and shows message boxes. [Source](https://kb.adrianbacceli.com/00_Toolbox/Runbooks/Python-CLI-Apps-%E2%80%93-Opinionated-Whitepaper--and--Runbook)

### 3. Optional Dependencies & Runtime Gating

7. **Declare GUI extras in `pyproject.toml`**:
   ```toml
   [project.optional-dependencies]
   gui = ["PyQt6>=6.7", "PyQt6-Qt6>=6.7"]
   ```
   Users install with `pip install myapp[gui]`. [Source](https://packaging.python.org/specifications/pyproject-toml)
8. **Gate GUI imports at runtime** with `try/except ImportError` in the GUI module. The top-level entry point can auto-detect GUI availability and fall back to CLI mode. [Source](https://stackoverflow.com/questions/2857634/how-can-i-create-a-gui-on-top-of-a-python-app-so-it-can-do-either-gui-or-cli)
9. **Avoid heavy GUI imports in `core/` or `cli/`** — this ensures the CLI works with zero GUI dependencies installed and keeps import times fast. [Source](https://core.cz/en/blog/2026/python-production-architecture-2026/)

### 4. Plugin Architecture Design

10. **Use `importlib.metadata.entry_points()` (stdlib)** for plugin discovery — no external dependencies needed. Define a custom group such as `myapp.plugins` in `pyproject.toml`:
    ```toml
    [project.entry-points."myapp.plugins"]
    apt = "myapp.plugins.apt:AptChecker"
    brew = "myapp.plugins.brew:BrewChecker"
    ```
    [Source](https://packaging.python.org/guides/creating-and-discovering-plugins)
11. **Load plugins with a simple loop**:
    ```python
    from importlib.metadata import entry_points

    def discover_plugins(group="myapp.plugins"):
        eps = entry_points(group=group)
        return {ep.name: ep.load() for ep in eps}
    ```
    [Source](https://docs.python.org/3/library/importlib.metadata.html)
12. **Define a plugin interface via `abc.ABC`** — each plugin implements a base class with methods like `check() -> list[Update]`, `name() -> str`, and `is_available() -> bool`. [Source](https://engineersofai.com/docs/python/python-advanced/architecture-and-systems-design/Plugin-Systems)
13. **For built-in plugins**, include them as subpackages inside `myapp/plugins/` and register them via entry points in the *same* `pyproject.toml`. This keeps built-in and third-party plugins on equal footing. [Source](https://mathieularose.com/plugin-architecture-in-python)
14. **Avoid Stevedore/Yapsy for a small app** — they add dependencies and indirection. The stdlib `importlib.metadata` pattern is sufficient until you need complex lifecycle management or dependency ordering. [Source](https://yapsy.readthedocs.io/en/latest)

### 5. Configuration System Design

15. **Use TOML as the config file format** — it is human-friendly, supports nested tables, and is already used by `pyproject.toml`, making it familiar to Python developers. [Source](https://packaging.python.org/specifications/pyproject-toml)
16. **Model config with `@dataclass`** — nested dataclasses map cleanly to TOML tables:
    ```python
    @dataclass
    class SourceConfig:
        enabled: bool = True
        interval_hours: int = 24

    @dataclass
    class AppConfig:
        sources: dict[str, SourceConfig] = field(default_factory=dict)
    ```
    [Source](https://pypi.org/project/dataclass-binder/)
17. **Use `tomllib` (stdlib in Python 3.11+)** to parse TOML. For 3.10 support, add a conditional dependency on `tomli`. [Source](https://docs.python.org/3/library/tomllib.html)
18. **Validation strategy**: load raw TOML → merge with dataclass defaults → validate types manually or with `pydantic` if you already depend on it. For a lightweight app, a small helper that walks the dataclass and checks `isinstance` is enough. [Source](https://typed-settings.readthedocs.io/en/stable)
19. **Config precedence** (highest wins): CLI arguments > environment variables > user config file (`~/.config/myapp/config.toml`) > dataclass defaults. [Source](https://pypi.org/project/saneconfig/)

### 6. Background Task Patterns in PyQt6

20. **QThreadPool + QRunnable** is best for short, discrete tasks (e.g., a single update check) because it reuses threads automatically. However, it is harder to interrupt cleanly. [Source](https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-technologies.html)
21. **QThread with a worker object + `moveToThread()`** is the recommended pattern for long-running or persistent background workers (e.g., a timer-based update loop). The worker exposes slots and signals; the thread runs its own event loop via `exec()`. [Source](https://riverbankcomputing.com/static/Docs/PyQt6/api/qtcore/qthread.html)
22. **For a system-tray update checker**, use a worker QObject with a `QTimer` *inside* the worker thread. This avoids blocking the GUI thread while still allowing periodic checks. Communicate results back via signals (`updates_found = pyqtSignal(list)`). [Source](https://forum.qt.io/topic/145122/pyqt6-long-running-thread-qthread-qtimer-or-qrunnable)
23. **Graceful shutdown**: maintain an `is_killed` (or `running`) boolean on the worker. The main thread sets it to `False` on app exit; the worker checks it in its loop and returns early. Do not call `terminate()` on threads. [Source](https://www.pythonguis.com/faq/elegant-shutdown-of-running-threads/)
24. **QtAsyncio** exists in PySide6 (technical preview) but is **not available in PyQt6**. If you need `async/await` with PyQt6, run `asyncio` in a separate `threading.Thread` and bridge to Qt via signals/slots. [Source](https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html)

### 7. System Tray Specifics

25. **Use `QSystemTrayIcon`** with `app.setQuitOnLastWindowClosed(False)` so the app persists when the settings window is closed. [Source](https://www.pythonguis.com/tutorials/pyqt6-system-tray-mac-menu-bar-applications/)
26. **Tray menu structure**: Check Now, Settings (opens window), Separator, Quit. The update-check worker emits signals that trigger `tray_icon.showMessage()` for balloon notifications. [Source](https://doc.qt.io/qtforpython-6.10/examples/example_widgets_desktop_systray.html)

---

## Component Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI Entry (cli.py)          │  GUI Entry (gui.py / tray.py)    │
│  - argparse/typer            │  - PyQt6 widgets                 │
│  - prints / exit codes       │  - QSystemTrayIcon, signals      │
│  - NO Qt imports             │  - NO sys.exit in core path      │
└──────────────┬───────────────┴──────────────┬───────────────────┘
               │                              │
               ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Core Package                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │  Config     │  │  Plugins    │  │  Update Engine          │  │
│  │  (TOML +    │  │  (ABC +     │  │  - orchestrates checks  │  │
│  │   dataclass)│  │   entry_pts)│  │  - aggregates results   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                  │
│  Core rules:                                                     │
│  - No imports from cli/, gui/, or PyQt6                         │
│  - Raises exceptions; never calls sys.exit or QMessageBox       │
│  - Pure Python + stdlib (plus tomli on <3.11)                   │
└─────────────────────────────────────────────────────────────────┘
```

**What talks to what:**
- `cli.py` and `gui.py` both import `core`.
- `core` knows nothing about CLI or GUI.
- `gui.py` may import `cli.py` utilities (e.g., shared argument parsing) if needed, but not vice versa.
- Plugins implement an ABC defined in `core.plugins` and are discovered via `importlib.metadata`.
- Config is loaded once at startup and injected into core components.

---

## Data Flow

```
Startup:
  Entry point → load config (defaults → file → env) → discover plugins
  → instantiate UpdateEngine with config + plugins

CLI Check Flow:
  User runs "myapp check" → cli.py parses args → calls engine.check_all()
  → engine iterates enabled plugins → each plugin.check() returns updates
  → engine returns list → cli formats table → prints → exit 0/1

GUI Check Flow:
  Tray icon "Check Now" clicked → signal → gui calls engine.check_all()
  → work moved to QThread worker → worker signals "updates_found"
  → GUI slot receives list → updates menu + shows balloon notification

Settings Flow:
  GUI opens settings window → reads config dataclass → user edits fields
  → "Save" serializes back to TOML → hot-reload optional (restart engine)
```

---

## Suggested Build Order

1. **Project skeleton** — `src/` layout, `pyproject.toml`, entry points, `__main__.py`.
2. **Configuration system** — dataclasses + TOML loader + defaults. This unblocks everything else.
3. **Plugin ABC + built-in plugins** — define the interface, port existing logic into built-in plugins, register via entry points.
4. **Core update engine** — orchestrates plugin discovery, filtering by `enabled`, and aggregation.
5. **CLI layer** — thin argparse wrapper around core engine.
6. **GUI layer** — system tray, menu, settings window, background QThread worker.
7. **Optional dependency wiring** — add `[gui]` extras, runtime import gating, CI matrix testing both modes.

Dependencies:
- Step 1 has no internal deps.
- Step 2 has no internal deps.
- Step 3 depends on Step 2 (config may hold plugin settings).
- Step 4 depends on Steps 2 and 3.
- Steps 5 and 6 both depend on Step 4 (can be developed in parallel).
- Step 7 depends on Steps 5 and 6.

---

## Plugin Architecture Design

### Discovery

Plugins are discovered via `importlib.metadata.entry_points(group="myapp.plugins")`. Both built-in and third-party packages register entry points in `pyproject.toml`.

### Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class Update:
    name: str
    current: str
    latest: str

class UpdateChecker(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the plugin can run in this environment."""

    @abstractmethod
    def check(self) -> list[Update]:
        """Perform the check and return available updates."""
```

### Registration Example

```toml
[project.entry-points."myapp.plugins"]
apt = "myapp.plugins.apt:AptChecker"
```

### Loading

```python
from importlib.metadata import entry_points

def load_checkers() -> dict[str, type[UpdateChecker]]:
    return {ep.name: ep.load() for ep in entry_points(group="myapp.plugins")}
```

### Lifecycle

1. **Discovery**: at startup, load all entry points.
2. **Availability filtering**: instantiate each plugin and call `is_available()`. Only available plugins are retained.
3. **Execution**: `UpdateEngine` calls `check()` on enabled plugins sequentially or in parallel (QThreadPool for GUI).
4. **Cleanup**: plugins are stateless by convention; no explicit teardown required.

---

## Configuration System Design

### File Format

TOML, stored at `~/.config/myapp/config.toml` (XDG) or platform equivalent.

### Schema

```python
from dataclasses import dataclass, field

@dataclass
class PluginConfig:
    enabled: bool = True

@dataclass
class AppConfig:
    check_interval_hours: int = 24
    plugins: dict[str, PluginConfig] = field(default_factory=dict)
```

### Loading Logic

```python
import os
import tomllib
from pathlib import Path

DEFAULT_CONFIG = AppConfig()

def load_config(path: Path | None = None) -> AppConfig:
    cfg = DEFAULT_CONFIG
    if path is None:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "myapp" / "config.toml"
    if path.exists():
        with path.open("rb") as f:
            raw = tomllib.load(f)
        # merge raw into dataclass (custom helper or pydantic)
        cfg = merge_into_dataclass(raw, DEFAULT_CONFIG)
    return cfg
```

### Validation

- Type validation via dataclass construction.
- Unknown keys ignored or warned depending on strictness preference.
- Environment variable override optional: `MYAPP_CHECK_INTERVAL_HOURS=12`.

---

## Sources

- **Kept**: How to Structure a Large PyQt6 or PySide6 Application — python-guis.com (https://www.pythonguis.com/faq/structuring-a-large-pyqt-application/) — directory layout and separation of UI logic.
- **Kept**: Creating a Python package — KDE Develop (https://develop.kde.org/docs/getting-started/python/python-package/) — src layout, pyproject.toml entry points, `__main__.py`.
- **Kept**: Python Packaging User Guide — Entry points specification (https://packaging.python.org/en/latest/specifications/entry-points/) — official reference for console scripts and plugin entry points.
- **Kept**: Creating and discovering plugins — Python Packaging User Guide (https://packaging.python.org/guides/creating-and-discovering-plugins/) — official plugin discovery guide.
- **Kept**: `importlib.metadata` — Python stdlib docs (https://docs.python.org/3/library/importlib.metadata.html) — primary source for runtime entry point loading.
- **Kept**: How to Design and Implement a Plugin Architecture in Python — Mathieu Larose (https://mathieularose.com/plugin-architecture-in-python) — namespace package pattern.
- **Kept**: Plugin Systems — EngineersOfAI (https://engineersofai.com/docs/python/python-advanced/architecture-and-systems-design/Plugin-Systems) — ABC interface and entry point registration examples.
- **Kept**: Python CLI Apps – Opinionated Whitepaper — Adrian Baccelli (https://kb.adrianbacceli.com/00_Toolbox/Runbooks/Python-CLI-Apps-%E2%80%93-Opinionated-Whitepaper--and--Runbook) — CLI architecture, exception-to-exit-code mapping.
- **Kept**: Stack Overflow — Separate program logic and GUI code (https://stackoverflow.com/questions/4522218/python-separate-program-logic-and-gui-code) — straightforward separation advice.
- **Kept**: Stack Overflow — GUI on top of Python CLI app (https://stackoverflow.com/questions/2857634/how-can-i-create-a-gui-on-top-of-a-python-app-so-it-can-do-either-gui-or-cli) — runtime gating and three-layer split.
- **Kept**: pyproject.toml specification — Python Packaging User Guide (https://packaging.python.org/specifications/pyproject-toml) — extras/optional dependencies.
- **Kept**: Multithreading Technologies in Qt — Qt for Python docs (https://doc.qt.io/qtforpython-6/overviews/qtdoc-threads-technologies.html) — QThread vs QThreadPool vs QtConcurrent.
- **Kept**: QThread — PyQt Documentation v6.11.0 (https://riverbankcomputing.com/static/Docs/PyQt6/api/qtcore/qthread.html) — worker-object pattern.
- **Kept**: Qt Forum — PyQt6 long running thread discussion (https://forum.qt.io/topic/145122/pyqt6-long-running-thread-qthread-qtimer-or-qrunnable) — practical background worker advice.
- **Kept**: Elegant shutdown of running threads in PyQt6 — python-guis.com (https://www.pythonguis.com/faq/elegant-shutdown-of-running-threads/) — graceful QThreadPool worker termination.
- **Kept**: PySide6.QtAsyncio docs (https://doc.qt.io/qtforpython-6/PySide6/QtAsyncio/index.html) — notes on asyncio integration (PySide6 only, not PyQt6).
- **Kept**: System tray & Mac menu bar applications in PyQt6 — python-guis.com (https://www.pythonguis.com/tutorials/pyqt6-system-tray-mac-menu-bar-applications/) — `setQuitOnLastWindowClosed(False)` and tray patterns.
- **Kept**: System Tray Icon Example — Qt for Python (https://doc.qt.io/qtforpython-6.10/examples/example_widgets_desktop_systray.html) — official tray menu and notification example.
- **Kept**: `dataclass-binder` PyPI page (https://pypi.org/project/dataclass-binder/) — rationale for dataclass-based config over raw dicts.
- **Kept**: `saneconfig` PyPI page (https://pypi.org/project/saneconfig/) — precedence model (env > file > defaults).
- **Dropped**: Tkinter packaging guides (Cursa, AhmedSyntax) — not relevant to PyQt6 project.
- **Dropped**: Poetry-specific docs — project uses standard `pyproject.toml` / setuptools, not Poetry.
- **Dropped**: Yapsy / Stevedore docs — adds dependencies; stdlib `importlib.metadata` is sufficient.

---

## Gaps

1. **Asyncio with PyQt6**: The official QtAsyncio module is PySide6-only (technical preview). If the app needs `async/await` patterns (e.g., aiohttp for update checks), the recommended approach is running `asyncio` in a `threading.Thread` and bridging via signals. This adds complexity not present in a pure synchronous design.
2. **Config hot-reload**: The research covered initial loading but not runtime config changes. For a tray app, decide whether settings changes require a restart or if the engine should watch the config file.
3. **Cross-platform tray quirks**: Linux StatusNotifierItem vs XEmbed differences can cause tray icon disappearance on some DEs. Additional per-platform testing may be needed.
4. **Plugin execution ordering**: If plugins must run in a specific order or have dependencies on each other, a simple list is insufficient. A topological sort or explicit `priority` field would be needed.
5. **Bundling/PyInstaller**: The research touched on PyInstaller briefly but did not deeply investigate how `importlib.metadata` entry points behave when frozen. PyInstaller may require `--copy-metadata` flags to preserve entry point discovery.

---

## Supervisor coordination

N/A — research is complete. All assigned questions have been answered with sourced findings.
