# Phase 3: User Experience — Plans

**Phase:** 3 — User Experience
**Goal:** Rich tray applet, smart notifications, and seamless topgrade integration.
**Created:** 2026-05-19

---

## Plan 1: Smart Notifications

**Wave:** 1
**Depends on:** None
**Autonomous:** Yes
**Requirements addressed:** NOTIFY-01, NOTIFY-02, NOTIFY-03, NOTIFY-04, NOTIFY-05

### Objective
Replace the simple `notify-send` subprocess with a hybrid DBus notification system that supports action buttons, deduplication (no re-notify for same count), quiet hours with deferred batching, and graceful fallback to `notify-send` when DBus actions aren't available.

### Tasks

#### Task 1.1: DBus notification client with fallback

```xml
<task>
<id>1.1</id>
<title>Hybrid DBus notification client</title>
<read_first>
- src/topgrade_update/core/notifications.py
- .planning/phases/03-user-experience/03-CONTEXT.md §"Notification Actions"
- .planning/research/PITFALLS.md §"4.1 Notification Spam"
</read_first>
<action>
Rewrite `src/topgrade_update/core/notifications.py` to use a hybrid approach:

1. Try importing `jeepney` (lightweight, pure Python DBus library). If unavailable, fall back to `notify-send` subprocess.
2. Create a `NotificationClient` class with methods:
   - `notify(summary: str, body: str, actions: list[tuple[str, str]] | None = None) -> str | None` — returns notification ID or None
   - `close(notification_id: str) -> None`
3. Actions format: `[("action-id", "Label"), ...]` e.g., `[("run", "Run Topgrade"), ("dismiss", "Dismiss")]`
4. If `jeepney` is unavailable OR the notification server doesn't support actions, fall back to `notify-send` with no actions.
5. Keep the existing `send_notification(results: list[CheckResult])` function as the public API, but implement it via `NotificationClient`.

Add `jeepney` as an optional dependency in `pyproject.toml` under `[project.optional-dependencies]`:
```toml
gui = ["PySide6>=6.5", "jeepney>=0.8"]
```

The `NotificationClient` should be importable without PySide6 (pure Python + jeepney).
</action>
<acceptance_criteria>
- `src/topgrade_update/core/notifications.py` contains `NotificationClient` class with `notify()` and `close()` methods
- `NotificationClient` tries `jeepney` first, falls back to `notify-send` subprocess
- `send_notification()` is preserved as public API but delegates to `NotificationClient`
- `pyproject.toml` `[project.optional-dependencies].gui` includes `jeepney>=0.8`
- `mypy src/topgrade_update/core/notifications.py` passes
- `python -c "from topgrade_update.core.notifications import NotificationClient; print(NotificationClient)"` works without PySide6 installed
</acceptance_criteria>
</task>
```

#### Task 1.2: Notification deduplication logic

```xml
<task>
<id>1.2</id>
<title>Notification deduplication engine</title>
<read_first>
- src/topgrade_update/core/notifications.py (after Task 1.1)
- src/topgrade_update/gui/tray.py (Tray._on_check_done)
- .planning/phases/03-user-experience/03-CONTEXT.md §"Notification Deduplication"
</read_first>
<action>
Create `src/topgrade_update/core/notification_engine.py` with a `NotificationEngine` class:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

@dataclass
class NotificationState:
    prev_total: int = -1
    prev_sources: set[str] = field(default_factory=set)
    quiet_hours_active: bool = False
    deferred_notifications: list[dict] = field(default_factory=list)

class NotificationEngine:
    def __init__(self) -> None:
        self._state = NotificationState()

    def should_notify(self, results: list[CheckResult]) -> bool:
        """Return True if a notification should be sent for these results.

        Rules per CONTEXT.md D-01..D-03:
        - Notify on 0 -> N (first updates appear)
        - Notify on N -> M where M > N (count increased)
        - Do NOT notify on decrease, no change, or same count
        """
        total = sum(len(r.updates) for r in results)
        prev = self._state.prev_total
        self._state.prev_total = total
        return total > 0 and (prev == 0 or total > prev)

    def enter_quiet_hours(self) -> None:
        self._state.quiet_hours_active = True

    def exit_quiet_hours(self) -> list[dict]:
        """Return deferred notifications and clear queue."""
        self._state.quiet_hours_active = False
        deferred = self._state.deferred_notifications
        self._state.deferred_notifications = []
        return deferred

    def maybe_defer(self, results: list[CheckResult]) -> bool:
        """If quiet hours are active, queue the notification and return True.
        Otherwise return False (caller should send immediately).
        """
        if not self._state.quiet_hours_active:
            return False
        self._state.deferred_notifications.append({"results": results})
        return True
```

Update `Tray._on_check_done()` in `tray.py` to use `NotificationEngine`:
1. Instantiate `NotificationEngine` in `Tray.__init__`
2. In `_on_check_done()`, call `engine.should_notify(results)` before calling `send_notification()`
3. If quiet hours are active, call `engine.maybe_defer(results)` instead of sending
4. Add a timer or check on each `_on_check_done()` to detect quiet hours end and send batched deferred notifications
</action>
<acceptance_criteria>
- `src/topgrade_update/core/notification_engine.py` exists with `NotificationEngine` class
- `should_notify()` returns True only on 0->N and N->M (M>N) transitions
- `should_notify()` returns False on same count, decrease, or no updates
- `maybe_defer()` queues notifications during quiet hours
- `exit_quiet_hours()` returns all deferred notifications
- `Tray` uses `NotificationEngine` in `_on_check_done()`
- `mypy src/topgrade_update/core/notification_engine.py` passes
</acceptance_criteria>
</task>
```

#### Task 1.3: Quiet hours detection and deferred batching

```xml
<task>
<id>1.3</id>
<title>Quiet hours detection and batch summary</title>
<read_first>
- src/topgrade_update/core/config.py
- src/topgrade_update/core/models.py
- src/topgrade_update/gui/tray.py
</read_first>
<action>
1. Update `Config` dataclass in `models.py` to include `quiet_hours_start` and `quiet_hours_end` (already present but verify):
   ```python
   @dataclass
   class NotificationConfig:
       enabled: bool = True
       quiet_hours_start: int | None = None  # 0-23
       quiet_hours_end: int | None = None    # 0-23
   ```

2. Create `src/topgrade_update/core/quiet_hours.py`:
   ```python
   from datetime import datetime
   
   def is_quiet_hours(start: int | None, end: int | None) -> bool:
       """Return True if current time is within quiet hours window.
       
       Handles wrap-around (e.g., start=23, end=8 means 23:00-08:00).
       """
       if start is None or end is None:
           return False
       now = datetime.now().hour
       if start < end:
           return start <= now < end
       return now >= start or now < end
   ```

3. Update `Tray._on_check_done()`:
   - Check `is_quiet_hours(cfg.notifications.quiet_hours_start, cfg.notifications.quiet_hours_end)`
   - If in quiet hours: `engine.maybe_defer(results)` + do NOT call `send_notification()`
   - If not in quiet hours but `exit_quiet_hours()` returns deferred items: batch them into a single summary notification

4. Batch summary format:
   - Title: "Updates available after quiet hours"
   - Body: sum all deferred result totals with source breakdown
</action>
<acceptance_criteria>
- `src/topgrade_update/core/quiet_hours.py` exists with `is_quiet_hours()`
- `is_quiet_hours(23, 8)` returns True at 02:00 and False at 12:00
- `is_quiet_hours(9, 17)` returns True at 12:00 and False at 20:00
- Tray defers notifications during quiet hours
- Tray sends batched summary when quiet hours end
- `mypy src/topgrade_update/core/quiet_hours.py` passes
- `ruff check src/` passes after all changes
</acceptance_criteria>
</task>
```

---

## Plan 2: Tray Enhancements

**Wave:** 2
**Depends on:** Plan 1
**Autonomous:** Yes
**Requirements addressed:** TRAY-04 (configurable), TRAY-08 (timestamp), TRAY-10 (snooze)

### Objective
Enhance the existing tray with configurable click behavior, last-check timestamp display, and snooze functionality.

### Tasks

#### Task 2.1: Configurable tray click behavior

```xml
<task>
<id>2.1</id>
<title>Configurable tray click action</title>
<read_first>
- src/topgrade_update/gui/tray.py
- src/topgrade_update/core/config.py
- src/topgrade_update/core/models.py
- .planning/phases/03-user-experience/03-CONTEXT.md §"Tray Click Behavior"
</read_first>
<action>
1. Update `Config` dataclass to include tray settings:
   ```python
   @dataclass
   class TrayConfig:
       click_action: str = "default"  # "default", "show_updates", "run_topgrade"
   
   @dataclass
   class Config:
       # ... existing fields ...
       tray: TrayConfig = field(default_factory=TrayConfig)
   ```

2. Update `Tray._on_activated()` to respect `click_action`:
   ```python
   def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
       if reason != QSystemTrayIcon.ActivationReason.Trigger:
           return
       action = self._cfg.tray.click_action
       if action == "default":
           # Current behavior: show if updates, run if none
           if total_updates(self._results) > 0:
               self._show_updates()
           else:
               self._run_topgrade()
       elif action == "show_updates":
           self._show_updates()
       elif action == "run_topgrade":
           self._run_topgrade()
   ```

3. Update config TOML loader/saver to handle `[tray]` section:
   ```toml
   [tray]
   click_action = "default"
   ```
</action>
<acceptance_criteria>
- `Config` dataclass has `tray: TrayConfig` field with `click_action: str`
- `Tray._on_activated()` reads `cfg.tray.click_action` and behaves accordingly
- `"default"` shows updates dialog if updates exist, runs topgrade if none
- `"show_updates"` always opens updates dialog
- `"run_topgrade"` always launches topgrade
- TOML config can set `[tray] click_action = "..."`
- `mypy src/topgrade_update/core/models.py` passes after changes
</acceptance_criteria>
</task>
```

#### Task 2.2: Last check timestamp in tooltip

```xml
<task>
<id>2.2</id>
<title>Last check timestamp display</title>
<read_first>
- src/topgrade_update/gui/tray.py
</read_first>
<action>
1. `Tray` already has `_last_check: datetime | None`. Update the tooltip to include it:
   ```python
   def _update_tooltip(self) -> None:
       lines = [APP_NAME]
       if self._last_check:
           lines.append(f"Last check: {self._last_check.strftime('%H:%M')}")
       total = total_updates(self._results)
       if total > 0:
           lines.append(f"{total} update(s) available")
       else:
           lines.append("System is up to date")
       self.setToolTip("\n".join(lines))
   ```

2. Call `_update_tooltip()` from `_on_check_done()` after setting results.
3. Also add "Last check: HH:MM" to the status menu action text when menu is opened (optional but nice).
</action>
<acceptance_criteria>
- Tray tooltip shows "Last check: HH:MM" after a check completes
- Tooltip format is multi-line: app name, last check time, status
- `mypy src/topgrade_update/gui/tray.py` passes
</acceptance_criteria>
</task>
```

#### Task 2.3: Snooze support in tray menu

```xml
<task>
<id>2.3</id>
<title>Snooze functionality in tray menu</title>
<read_first>
- src/topgrade_update/gui/tray.py
- .planning/phases/03-user-experience/03-CONTEXT.md §"Notification Actions"
</read_first>
<action>
1. Add snooze state to `Tray`:
   ```python
   self._snooze_until: datetime | None = None
   ```

2. Add "Snooze" submenu to context menu with options:
   - "Snooze 1 hour"
   - "Snooze 4 hours" (default)
   - "Snooze until tomorrow"
   - "Cancel snooze"

3. Implement `Tray._snooze(hours: int | None)`:
   - Sets `_snooze_until = datetime.now() + timedelta(hours=hours)` if hours given
   - Clears `_snooze_until` if hours is None (cancel)
   - Updates status action to show snooze state

4. In `_start_check()`, skip the check if snoozed:
   ```python
   if self._snooze_until and datetime.now() < self._snooze_until:
       self._action_status.setText("Snoozed")
       return
   ```

5. In `_on_check_done()`, if snoozed, do NOT send notifications (but still update icon/tooltip).
</action>
<acceptance_criteria>
- Tray context menu has Snooze submenu with 1h, 4h, until tomorrow, cancel options
- During snooze, periodic checks are skipped
- During snooze, no notifications are sent
- Status action shows "Snoozed until HH:MM" when active
- Cancel snooze restores normal behavior
- `mypy src/topgrade_update/gui/tray.py` passes
</acceptance_criteria>
</task>
```

---

## Plan 3: Topgrade Integration

**Wave:** 3
**Depends on:** Plan 2
**Autonomous:** Yes
**Requirements addressed:** TG-01, TG-02, TG-03

### Objective
Parse `topgrade.toml` to respect disabled steps, and ensure terminal detection and topgrade launching work seamlessly.

### Tasks

#### Task 3.1: topgrade.toml parser

```xml
<task>
<id>3.1</id>
<title>Parse topgrade.toml for disabled steps</title>
<read_first>
- src/topgrade_update/core/config.py
- src/topgrade_update/core/models.py
- .planning/phases/03-user-experience/03-CONTEXT.md §"topgrade.toml Integration"
</read_first>
<action>
1. Create `src/topgrade_update/core/topgrade_config.py`:
   ```python
   from __future__ import annotations
   
   import os
   from pathlib import Path
   from typing import Any
   
   def find_topgrade_toml() -> Path | None:
       """Find topgrade.toml in standard locations."""
       paths = [
           Path.home() / ".config" / "topgrade" / "topgrade.toml",
           Path.home() / ".topgrade.toml",
       ]
       for p in paths:
           if p.exists():
               return p
       return None
   
   def load_topgrade_config(path: Path | None = None) -> dict[str, Any]:
       """Load topgrade.toml and return parsed dict."""
       if path is None:
           path = find_topgrade_toml()
       if path is None:
           return {}
       try:
           import tomllib
       except ImportError:
           import tomli as tomllib  # type: ignore
       with path.open("rb") as f:
           return tomllib.load(f)
   
   def get_disabled_steps(config: dict[str, Any]) -> set[str]:
       """Extract disabled step names from topgrade config."""
       disabled = set()
       for key, value in config.items():
           if isinstance(value, dict):
               continue
           if value is False:
               disabled.add(key.lower())
       return disabled
   
   def get_disabled_categories(config: dict[str, Any]) -> set[str]:
       """Extract disabled category names."""
       disabled = set()
       # Handle nested categories if present
       for key, value in config.items():
           if isinstance(value, dict) and value.get("disabled", False):
               disabled.add(key.lower())
       return disabled
   ```

2. Define mapping from topgrade step names to our checker names:
   ```python
   TOPGRADE_STEP_MAP = {
       "pacman": {"pacman"},
       "yay": {"aur"},
       "paru": {"aur"},
       "flatpak": {"flatpak"},
       "linux": {"pacman", "aur"},  # category-level
   }
   ```
</action>
<acceptance_criteria>
- `src/topgrade_update/core/topgrade_config.py` exists with `find_topgrade_toml()`, `load_topgrade_config()`, `get_disabled_steps()`, `get_disabled_categories()`
- `find_topgrade_toml()` finds `~/.config/topgrade/topgrade.toml` or `~/.topgrade.toml`
- `get_disabled_steps()` returns set of disabled step names (lowercased)
- `TOPGRADE_STEP_MAP` maps topgrade steps to our checker names
- `mypy src/topgrade_update/core/topgrade_config.py` passes
- `python -c "from topgrade_update.core.topgrade_config import load_topgrade_config; print(load_topgrade_config)"` works
</acceptance_criteria>
</task>
```

#### Task 3.2: Disable checkers based on topgrade.toml

```xml
<task>
<id>3.2</id>
<title>Wire topgrade.toml into UpdateEngine</title>
<read_first>
- src/topgrade_update/core/engine.py
- src/topgrade_update/core/topgrade_config.py (from Task 3.1)
- src/topgrade_update/core/checkers/facade.py
- .planning/phases/03-user-experience/03-CONTEXT.md §"topgrade.toml Integration"
</read_first>
<action>
1. Update `UpdateEngine.check_all()` to accept topgrade config:
   ```python
   def check_all(
       self,
       cfg: Config | None = None,
       topgrade_disabled: set[str] | None = None,
   ) -> list[CheckResult]:
   ```

2. Filter out checkers whose names are in `topgrade_disabled`:
   ```python
   for checker in self.available():
       if topgrade_disabled and checker.name in topgrade_disabled:
           continue
       # ... existing check logic ...
   ```

3. Update `_get_engine()` in `facade.py` to load topgrade config:
   ```python
   def _get_engine() -> UpdateEngine:
       from topgrade_update.core.topgrade_config import (
           load_topgrade_config, get_disabled_steps, TOPGRADE_STEP_MAP,
       )
       engine = UpdateEngine()
       engine.discover_builtin()
       engine.discover_entry_points()
       
       tg_cfg = load_topgrade_config()
       disabled_steps = get_disabled_steps(tg_cfg)
       disabled_cats = get_disabled_categories(tg_cfg)
       
       # Map to our checker names
       topgrade_disabled: set[str] = set()
       for step in disabled_steps | disabled_cats:
           if step in TOPGRADE_STEP_MAP:
               topgrade_disabled |= TOPGRADE_STEP_MAP[step]
       
       return engine, topgrade_disabled
   ```

4. Update `check_all()` facade:
   ```python
   def check_all(cfg: Config | None = None) -> list[CheckResult]:
       engine, tg_disabled = _get_engine()
       return engine.check_all(cfg, topgrade_disabled=tg_disabled)
   ```
</action>
<acceptance_criteria>
- `UpdateEngine.check_all()` accepts optional `topgrade_disabled` parameter
- Checkers in `topgrade_disabled` set are skipped
- `facade.check_all()` loads topgrade.toml and passes disabled steps to engine
- If topgrade.toml doesn't exist, all checkers run normally
- `mypy src/topgrade_update/core/engine.py src/topgrade_update/core/checkers/facade.py` passes
- `topgrade-update --list` still works (no errors if topgrade.toml missing)
</acceptance_criteria>
</task>
```

#### Task 3.3: End-to-end verification

```xml
<task>
<id>3.3</id>
<title>Verify end-to-end integration</title>
<read_first>
- src/topgrade_update/cli/main.py
- src/topgrade_update/gui/tray.py
</read_first>
<action>
Run the following verification commands in order:

1. `mypy src/` — must pass with no errors
2. `ruff check src/` — must pass with no errors
3. `topgrade-update --list` — must show updates with source breakdown
4. `topgrade-update --check` — must return exit code 1 if updates exist
5. Create a test `~/.config/topgrade/topgrade.toml` with `flatpak = false`, then run `topgrade-update --list` and verify flatpak is not checked. Then remove the test file.

If any command fails, fix the issue and re-run.
</action>
<acceptance_criteria>
- `mypy src/` exits with code 0
- `ruff check src/` exits with code 0
- `topgrade-update --list` produces source breakdown
- `topgrade-update --check` returns correct exit code
- With `topgrade.toml` containing `flatpak = false`, flatpak updates are not listed
- All changes committed
</acceptance_criteria>
</task>
```

---

## Plan Summary

| Plan | Wave | Objective | Requirements |
|------|------|-----------|-------------|
| 1 | 1 | Smart notifications (DBus, dedup, quiet hours) | NOTIFY-01..05 |
| 2 | 2 | Tray enhancements (configurable click, timestamp, snooze) | TRAY-04, TRAY-08, TRAY-10 |
| 3 | 3 | Topgrade integration (topgrade.toml parsing) | TG-01..03 |

## Must-Haves for Phase Success

1. DBus notifications with action buttons work when `jeepney` is installed
2. Notifications fall back to `notify-send` when DBus unavailable
3. No notification spam — only notify on 0→N and count increase
4. Quiet hours defer notifications, batch on exit
5. Tray click is configurable via config TOML
6. Last check timestamp shown in tooltip
7. Snooze pauses checks and notifications
8. topgrade.toml disabled steps are respected
9. `mypy` and `ruff` pass on all modified files
10. CLI `--list` and `--check` continue to work correctly
