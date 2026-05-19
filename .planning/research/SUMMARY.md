# Research Summary: Topgrade Update Improvements

## Stack Recommendation

| Layer | Choice | Rationale |
|-------|--------|-----------|
| GUI Framework | **PySide6** (≥6.8) | LGPL license (vs PyQt6 GPL), official Qt bindings, drop-in replacement |
| Tray Icon | `QSystemTrayIcon` (built-in) | Native StatusNotifierItem DBus support on Linux, no extra deps |
| Build System | `pyproject.toml` + **hatchling** | Modern PEP 517 backend, fast, handles entry points cleanly |
| Testing | `pytest` + `pytest-qt` + `pytest-xvfb` | Standard Qt testing with headless CI support |
| Logging | Standard `logging` + rotating file handler | Zero deps, integrates with journald if systemd service |
| Config | TOML + `@dataclass` | Human-friendly, maps cleanly to Python, stdlib `tomllib` on 3.11+ |
| Plugins | `importlib.metadata.entry_points()` | stdlib only, no external deps like stevedore/yapsy |

**Migration note:** PyQt6 → PySide6 is mostly `PyQt6` → `PySide6`, `pyqtSignal` → `Signal`.

## Key Features (Table Stakes)

1. Tray icon with badge/count display
2. Desktop notification on new updates (with source breakdown)
3. Click-to-update action
4. Periodic background checking
5. Multi-source support (pacman + AUR + flatpak)
6. Source distinction in UI
7. Last check timestamp

## Differentiators to Consider

1. Arch Linux News integration
2. Post-update maintenance helpers (orphans, pacnew)
3. Kernel/reboot required detection
4. Configurable check interval with GUI
5. Quiet hours / DND awareness
6. Update list preview in tray menu
7. Terminal auto-detection (not hardcoded)
8. Consent-first philosophy (defer, snooze)

## Anti-Features (Deliberately Avoid)

1. **Automatic installation** — never install without explicit user consent on Arch
2. **Auto-reboot** — notify only, never reboot without consent
3. **Modal blocking dialogs** — use tray + transient notifications
4. **Unsuppressible repeated notifications** — only notify on count changes
5. **Root for checking** — checking should never require root
6. **Bundled/package manager lock-in** — auto-detect, allow override

## Architecture Pattern

- **src-layout** package: `src/topgrade_update/`
- **Three layers:** `core/` (pure Python), `cli/` (argparse), `gui/` (PySide6)
- **Plugin ABC** with `importlib.metadata` discovery
- **QThread worker** for background checks (not main thread)
- **Config precedence:** CLI args > env vars > config file > defaults

## Critical Pitfalls to Avoid

1. **Subprocess zombies** — use `preexec_fn=os.setsid` + `os.killpg()` on timeout
2. **Blocking main thread** — all subprocess I/O in QThread worker
3. **Shell injection** — always pass commands as lists, never `shell=True`
4. **Notification spam** — batch into single summary, cooldown between notifications
5. **Tray memory leaks** — reuse one `QSystemTrayIcon`, never recreate
6. **Thread affinity violations** — create all GUI objects in main thread
7. **Partial failures** — isolate each checker in try/except, return result objects
