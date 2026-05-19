# Research: Modern Python Desktop Application Stack for Linux System Tray Applet

## Summary
For a Linux system tray applet targeting Arch-based systems (pacman/AUR/flatpak), the recommended stack is **PySide6** (LGPL, official Qt bindings) with `pyproject.toml` + **hatchling** build backend, **pytest-qt** for GUI testing, **structlog** or standard `logging` for logs, and **QSystemTrayIcon** for the tray icon (it speaks modern DBus StatusNotifierItem natively on Qt 6). Avoid Poetry for this use case unless you need lockfiles; avoid PyQt6 due to GPL licensing; avoid GTK-based tray libraries to prevent stacking two UI toolkits.

---

## Recommended Stack

### 1. GUI Framework: PySide6
- **Library:** `PySide6` (Qt for Python, official)
- **Version:** `>=6.8` (latest stable)
- **Rationale:** Official Qt Company bindings, LGPL license (no copyleft obligations on your code), follows Qt release schedule, includes `.pyi` type stubs for mypy/pyright. APIs are ~99.9% compatible with PyQt6. [Source](https://www.pythonguis.com/faq/pyqt6-vs-pyside6/)
- **Confidence:** Very High

### 2. System Tray: QSystemTrayIcon (built into PySide6)
- **Library:** `PySide6.QtWidgets.QSystemTrayIcon`
- **Rationale:** Qt 6's `QSystemTrayIcon` now supports the DBus **StatusNotifierItem** specification natively on Linux, covering KDE, GNOME (with extension), XFCE, LXQt, and DDE. It falls back to XEmbed on older systems. This is the modern, cross-platform standard. No need to pull in GTK/GObject AppIndicator stacks. [Source](https://doc.qt.io/qt-6/qsystemtrayicon.html)
- **Confidence:** Very High

### 3. Build System / Packaging: pyproject.toml + hatchling
- **Library:** `hatchling` build backend
- **Version:** Latest stable
- **Rationale:** `pyproject.toml` is the standardized configuration format (PEP 517/518/621/660). Hatchling is recommended by the Scientific Python Development Guide as an excellent default—fast, configurable, extensible, and modern. Since this app is Arch-specific (pacman/AUR/flatpak), it should be distributed via an Arch **PKGBUILD** or installed as an editable package (`pip install -e .`), not necessarily PyPI. Hatchling handles both. [Source](https://learn.scientific-python.org/development/guides/packaging-simple/)
- **Confidence:** High

### 4. Dependency Management: uv or pip + venv
- **Tool:** `uv` (modern, fast) or standard `pip` + `venv`
- **Rationale:** For a desktop app that won't be published to PyPI as a library, a lockfile isn't critical. `uv` provides fast resolution and virtualenv management. If you want reproducible builds, use `uv pip compile` or `requirements.txt` pinned in version control. Poetry/PDM are overkill here.
- **Confidence:** Medium-High

### 5. Type Hints & Static Analysis
- **Tools:** `mypy` or `pyright`, strict mode enabled
- **Rationale:** PySide6 ships with `.pyi` stubs and is `mypy --strict` compatible (Qt Company CI runs mypy on stubs). Best practices: use built-in generics (`list[str]`), shorthand unions (`str | None`), `object` over `Any` for generic inputs, and `TypeAlias` for aliases. [Source](https://typing.python.org/en/latest/reference/best-practices.html) [Source](https://doc.qt.io/qtforpython-6.8/developer/mypy-correctness.html)
- **Confidence:** Very High

### 6. Testing
- **Tools:** `pytest` + `pytest-qt` + `pytest-xvfb`
- **Rationale:** `pytest-qt` provides the `qtbot` fixture for simulating user interactions (mouse clicks, key presses, signal waiting). Separate business logic (update checking) from UI code and unit test it in isolation. Use `pytest-xvfb` or `xvfb-run` for headless CI. Mock subprocess calls to `pacman`, `flatpak`, and `topgrade`. [Source](https://pytest-qt.readthedocs.io)
- **Confidence:** Very High

### 7. Logging
- **Library:** `structlog` (development) bridged to standard `logging` or pure `logging` + `rich.logging.RichHandler`
- **Rationale:** For a desktop app, structured logging is helpful but not mandatory. A practical setup: use standard library `logging` configured with `RichHandler` for pretty console output during development, and a rotating file handler for production. If running as a systemd user service, log to stderr and let `journald` capture it. Use `logging.getLogger(__name__)` per module. Bridge Qt's `qDebug`/`qWarning` to Python logging via `QMessageLogger` if needed. [Source](https://www.structlog.org/en/25.4.0/logging-best-practices.html) [Source](https://blog.vibe-eval.com/content/posts/python-logging-config-actually-works/)
- **Confidence:** High

### 8. Desktop Integration & Distribution
- **Format:** Native Arch package (PKGBUILD) + systemd user service
- **Rationale:** Since the app checks `pacman`/`AUR`/`flatpak`, it is inherently Arch-specific. Distribute via the AUR with a `PKGBUILD` that installs the Python package and a `.desktop` file. Register a systemd user service for auto-start. Avoid AppImage/Flatpak for this tool—they add sandboxing complexity and are poorly suited for apps that need to invoke system package managers. If you need a standalone binary, `pyside6-deploy` (Nuitka-based) or `PyInstaller`/`cx_Freeze` are options, but native packaging is preferred. [Source](https://doc.qt.io/qtforpython-6.8/deployment/deployment-pyside6-deploy.html) [Source](https://github.com/beeware/briefcase/issues/718)
- **Confidence:** High

---

## Rationale for Each Choice

### Why PySide6 over PyQt6?
PySide6 is the official Qt for Python binding and uses the **LGPL** license. PyQt6 uses GPL (or requires a paid commercial license). For any project that may be distributed or whose license is not strictly GPL, PySide6 removes legal risk. The APIs are functionally identical, so migration from PyQt6 is trivial. PySide6 is also maintained by The Qt Company, ensuring tighter alignment with Qt releases. [Source](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/)

### Why hatchling over setuptools or Poetry?
Setuptools still works but carries legacy baggage (`setup.py`/`setup.cfg`/`MANIFEST.in`). Poetry 2.0 now supports PEP 621, but it is primarily a dependency manager with a packaging backend. Hatchling is a clean, fast, modern build backend that handles PEP 621 natively without imposing a specific workflow. It is the recommended default for new projects. [Source](https://learn.scientific-python.org/development/guides/packaging-simple/)

### Why QSystemTrayIcon over AppIndicator/pystray?
Qt 6's `QSystemTrayIcon` implements the **StatusNotifierItem** DBus protocol, which is the modern Linux standard for system tray icons. It works on all major DEs (KDE, GNOME with extension, XFCE, Cinnamon, LXQt, DDE). Using AppIndicator would require pulling in GObject/PyGObject and GTK dependencies, creating a heavy second UI stack for a Qt app. `pystray` is a fine abstraction but adds a dependency for functionality already present in Qt. [Source](https://doc.qt.io/qt-6/qsystemtrayicon.html) [Source](https://blog.tingping.se/2019/09/07/how-to-design-a-modern-status-icon.html)

### Why standard logging + Rich over just print()?
Desktop apps need persistent logs for debugging user issues. Python's `logging` module with `RichHandler` gives colored, structured console output in development and can easily switch to file/journal output in production. `structlog` is excellent if you need JSON structured logs, but for a single-user desktop app, standard logging properly configured is sufficient and has zero extra dependencies. [Source](https://signoz.io/guides/python-logging-best-practices/)

### Why pytest-qt?
It is the de-facto standard for testing Qt applications in Python. The `qtbot` fixture handles `QApplication` lifecycle, simulates user input, and provides `waitSignal` for async UI tests. It works with both PyQt and PySide. [Source](https://pytest-qt.readthedocs.io)

---

## What NOT to Use and Why

| Technology | Why Avoid |
|---|---|
| **PyQt6** | GPL license forces your entire application to be GPL if distributed, or requires an expensive commercial license. PySide6 is a drop-in LGPL alternative. |
| **setuptools with setup.py** | Legacy. Modern Python packaging uses `pyproject.toml` with a PEP 517 backend. Setuptools can still be used via `pyproject.toml`, but hatchling is cleaner. |
| **Poetry** (as primary backend) | Poetry 2.0 supports PEP 621, but it is opinionated and adds complexity. Overkill for a single desktop app that won't be a library on PyPI. |
| **AppIndicator / libayatana-appindicator** | GTK/GObject dependency. Pulls in an entire second UI toolkit into a Qt app. QSystemTrayIcon handles the same DBus protocols natively since Qt 6. |
| **AppImage** | Known runtime issues with Qt6/PySide6 on Linux due to missing system dependencies and library conflicts. [Source](https://github.com/beeware/briefcase/issues/718) |
| **Flatpak** | Sandboxing conflicts with invoking system package managers (`pacman`, `topgrade`). The app needs host system access, defeating Flatpak's purpose. |
| **print() for logging** | No timestamps, no levels, no filtering, can't redirect to files/journal. Unprofessional and unmaintainable. |
| **Gtk.StatusIcon** | Deprecated, removed in GTK4, X11-only. Dead technology. |

---

## Sources

- **Kept:**
  - [PyQt6 vs PySide6: Key Differences](https://www.pythonguis.com/faq/pyqt6-vs-pyside6/) — authoritative licensing and API comparison
  - [Licensing Differences Between PyQt6 and PySide6](https://www.pythonguis.com/faq/licensing-differences-between-pyqt6-and-pyside6/) — clear GPL vs LGPL implications
  - [Scientific Python: Simple Packaging](https://learn.scientific-python.org/development/guides/packaging-simple/) — authoritative modern Python packaging guide
  - [Python Packaging User Guide](https://packaging.python.org/guides/writing-pyproject-toml) — official PyPA guidance on pyproject.toml
  - [QSystemTrayIcon Documentation](https://doc.qt.io/qt-6/qsystemtrayicon.html) — official Qt docs confirming Linux StatusNotifierItem support
  - [pytest-qt Documentation](https://pytest-qt.readthedocs.io) — standard testing tool for Qt Python apps
  - [Typing Best Practices](https://typing.python.org/en/latest/reference/best-practices.html) — official Python typing team recommendations
  - [structlog Best Practices](https://www.structlog.org/en/25.4.0/logging-best-practices.html) — structured logging guidance
  - [PySide6 Deployment Guide](https://doc.qt.io/qtforpython-6.8/deployment/deployment-pyside6-deploy.html) — Qt official packaging options
  - [TingPing: How to design a modern status icon](https://blog.tingping.se/2019/09/07/how-to-design-a-modern-status-icon.html) — Linux tray architecture analysis

- **Dropped:**
  - SEO-heavy comparison sites with no primary evidence
  - Outdated pre-PEP 621 packaging tutorials recommending `setup.py`
  - AppImage builder guides (irrelevant for Arch-native system tool)

---

## Gaps

1. **No direct benchmark data** comparing hatchling vs setuptools build times for a small project. In practice, the difference is negligible for a ~400-line app.
2. **Wayland-specific tray behavior** is not deeply documented. QSystemTrayIcon relies on the compositor/DE implementing StatusNotifierItem. On minimal Wayland compositors (e.g., Sway without a tray applet), the icon may not appear. This is acceptable for a tool targeting mainstream DEs.
3. **AUR packaging specifics** (PKGBUILD templates for pyproject.toml-based Python apps) were not researched in this pass. Follow-up: examine `python-poetry` or `python-hatchling` PKGBUILDs in the AUR for patterns.

---

## Suggested Next Steps

1. Draft a `pyproject.toml` using `hatchling` backend with the `[project.scripts]` entry point.
2. Migrate existing PyQt6 imports to PySide6 (mostly `PyQt6` → `PySide6`, `pyqtSignal` → `Signal`, `pyqtSlot` → `Slot`).
3. Set up `pytest` + `pytest-qt` with a test skeleton for the tray icon and update-check logic.
4. Configure logging with `logging.getLogger(__name__)` and a `RichHandler` for development.
5. Create a `.desktop` file and systemd user service template for desktop integration.
