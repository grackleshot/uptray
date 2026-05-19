# Phase 3: User Experience - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Rich tray applet, smart notifications, and seamless topgrade integration. Enhances the existing PySide6 tray and notification system with deduplication, quiet hours, configurable interactions, and topgrade config awareness. Does NOT add new checkers or change the plugin architecture — works with the UpdateEngine from Phase 2.

</domain>

<decisions>
## Implementation Decisions

### Notification Deduplication
- **D-01:** Notify on 0→N transitions (first updates appear) AND on count increase (N→M where M > N)
- **D-02:** Do NOT notify on count decrease, no change, or repeated checks with same count
- **D-03:** Engine tracks previous result set; notification decision is based on total count comparison

### Quiet Hours
- **D-04:** Checks continue to run on schedule during quiet hours
- **D-05:** Notifications are deferred/queued during quiet hours, not suppressed permanently
- **D-06:** When quiet hours end, all queued notifications are batched into a single summary notification
- **D-07:** Tray icon and menu still update during quiet hours (user can check manually)

### Tray Click Behavior
- **D-08:** Configurable via `tray.click_action` in config TOML
- **D-09:** Supported values: `"show_updates"` (open dialog) or `"run_topgrade"` (launch terminal)
- **D-10:** Default behavior remains context-aware: show dialog if updates exist, run topgrade if none

### topgrade.toml Integration
- **D-11:** Parse `topgrade.toml` for disabled steps and categories
- **D-12:** Map topgrade step names to checker sources (e.g., `yay = false` → disable AUR checker)
- **D-13:** Handle category-level disables (e.g., `linux = false` disables all Linux checkers)
- **D-14:** Respect `assume_yes`, `no_retry`, and other execution flags where relevant
- **D-15:** Config precedence: topgrade.toml overrides → our config file → defaults

### Notification Actions
- **D-16:** Hybrid approach: try DBus library first (`dbus-next` or `jeepney`), fall back to `notify-send`
- **D-17:** Action buttons when DBus is available: "Run Topgrade", "Dismiss", "Snooze"
- **D-18:** Snooze duration configurable (default 4 hours)
- **D-19:** If DBus library unavailable or actions unsupported by DE, fall back to plain `notify-send`

### the agent's Discretion
- Exact DBus library choice (jeepney vs dbus-next vs dasbus)
- Notification queue implementation details
- topgrade.toml parsing strategy (tomllib vs tomli)
- Snooze persistence mechanism
- Exact mapping table from topgrade steps to checker names

</decisions>

<canonical_refs>
## Canonical References

### Notification System
- `.planning/research/FEATURES.md` §"Anti-features" — guidance on avoiding notification spam
- `.planning/research/PITFALLS.md` §"4.1 Notification Spam & Fatigue" — cooldown and batching requirements

### Tray Applet
- `src/topgrade_update/gui/tray.py` — existing tray implementation to enhance
- `src/topgrade_update/gui/icons.py` — existing icon caching system
- `src/topgrade_update/gui/dialog.py` — existing updates dialog

### Topgrade Integration
- `src/topgrade_update/core/checkers/facade.py` — check_all() entry point
- `src/topgrade_update/core/engine.py` — UpdateEngine with config filtering
- `src/topgrade_update/core/config.py` — TOML config loading

### Requirements
- `.planning/REQUIREMENTS.md` — NOTIFY-01 through NOTIFY-05, TRAY-01 through TRAY-09, TG-01 through TG-03

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Tray` class in `tray.py` — QSystemTrayIcon with timer, menu, click handlers
- `CheckThread` — QThread for background checks, emits Signal(list[CheckResult])
- `IconCache` — Pre-generated icons for idle/checking/uptodate/updates states
- `UpdatesDialog` — Dialog showing per-source update breakdown
- `send_notification()` — notify-send wrapper in `core/notifications.py`
- `load_config()` / `Config` dataclass — TOML config with intervals, sources, terminals

### Established Patterns
- PySide6 signals/slots for UI updates from background thread
- Subprocess calls via `run_checked()` with process-group cleanup
- Dataclass-based config with TOML serialization
- Error isolation: exceptions caught, surfaced as `CheckResult.error`

### Integration Points
- `check_all(cfg)` in facade → `UpdateEngine.check_all(cfg)` → returns `list[CheckResult]`
- `Tray._on_check_done()` receives results, updates icon/tooltip/menu, triggers notifications
- `launch_topgrade_in_terminal(cfg)` uses `find_terminal(cfg)` from facade
- Config loaded once at startup via `load_config()`

</code_context>

<specifics>
## Specific Ideas

- "I want notifications to feel like Android — silent during DND, then a batch summary when it ends"
- Tray click should be customizable because some users always want to run topgrade, others want to see details first
- topgrade.toml integration should be transparent — if I disable flatpak in topgrade, the tray shouldn't check it either

</specifics>

<deferred>
## Deferred Ideas

- Firmware update checker (`fwupdmgr`) — v2, new checker plugin
- Post-update maintenance helpers (orphans, pacnew) — v2
- Kernel/reboot required detection — v2
- Internationalization (gettext) — v2
- Scheduled backup/rotation of logs — Phase 4

</deferred>

---

*Phase: 03-user-experience*
*Context gathered: 2026-05-19*
