---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 03 of 4 (user experience)
status: Executing Phase 03
last_updated: "2026-06-17T00:00:00Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 12
  completed_plans: 3
---

# Project State: Topgrade Update

**Initialized:** 2026-05-19
**Current Phase:** 03 — User Experience (in progress)
**Phase Status:** Executing

## Progress

| Phase | Status | Plans | Progress |
|-------|--------|-------|----------|
| 1 — Foundation | ✓ | 3/3 | 100% |
| 2 — Core Engine | ✓ | 3/3 | 100% |
| 3 — User Experience | ● | 3/3 | 100% |
| 4 — Polish & Quality | ○ | 0/3 | 0% |

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-06-17)

**Core value:** Users never miss available system updates because the tray applet silently checks and clearly surfaces them.
**Current focus:** Phase 3 — tray enhancements, logging, desktop integration, new checkers

## Active Decisions

| Decision | Status |
|----------|--------|
| PySide6 over PyQt6 | ✓ Good |
| hatchling build backend | ✓ Good |
| Hybrid plugin discovery (built-in + entry_points) | ✓ Good |
| Process-group killing on timeout | ✓ Good |
| Sequential checker execution | ✓ Good |
| TOML for config | ✓ Good |
| Rotating file logging | ✓ Good |
| SVG icon for desktop integration | ✓ Good |

## Blockers

None.

## Notes

- Phase 2 complete: plugin ABC, UpdateEngine, process-group subprocess cleanup, built-in checkers ported
- All CHECK-01 through CHECK-07 requirements satisfied
- Backwards compatibility verified: `--list` and `--check` produce identical output
- Phase 3 Plan 1 (notification system) complete: NotificationClient with jeepney DBus + notify-send fallback
- Phase 3 Plan 2 (tray applet) complete: full tray applet with badge, snooze, per-source breakdown
- Phase 3 Plan 3 (topgrade integration) complete: terminal detection, topgrade.toml parsing
- **New in this session:**
  - Logging system (LOG-01 through LOG-03): rotating file log, per-checker timing, `--verbose` flag
  - Firmware checker (CHECK-08): fwupdmgr integration
  - Custom command checker (CHECK-09): user-defined update scripts
  - Reboot detection: Arch kernel update detection + Debian /run/reboot-required
  - CLI improvements: `--verbose`, `--json` output for `--list`
  - Desktop integration: SVG icon, .desktop file, install script
  - CI/CD: GitHub Actions workflow (ruff, mypy, pytest, build)
  - Comprehensive README with architecture docs
  - LICENSE file (MIT)
  - Test suite: 72 tests (up from 58)
  - Quality: ruff + mypy strict pass on all 25 source files

## Session 2026-11-10: UI/UX redesign (top to bottom)

- New `gui/style.py`: token-based theme (light+dark, palette-detected), global QSS,
  `apply_theme`/`apply_app_theme`, `set_primary`/`set_danger` helpers. AA contrast;
  dark-theme accent_text switched to dark ink on light-blue accent.
- Tray icons (`gui/icons.py`): distinct glyph per state (idle=disc, checking=clock,
  uptodate=check, updates=arrow+badge, reboot=restart) — readable without color.
  Public `status_pixmap(kind, size)` shared by dialogs/run window.
- UpdatesDialog: big title + per-source subtitle, reboot banner (not a fake package
  row), package filter box, bold source groups, amber error rows ("⚠ " prefix,
  format otherwise unchanged), "Update Now" primary, double-click hint. Reboot no
  longer counted in header total.
- RunWindow: Simple mode = big plain-language hero ("Updating your computer…" /
  "All done!" / "Something went wrong"), step checklist with icon+word per status,
  progress bar, single muted activity line. Verbose = full terminal + same checklist
  sidebar. Segmented Simple/Verbose control, retry strip restyled, diagnose drawer
  carded; Diagnose becomes primary on failure, Close on success. Elapsed as M:SS.
- SettingsDialog: three cards (Checking / Running / Tray&&notifications), plain-
  language source labels, helper captions under technical fields, "Save" primary.
  Notif checkboxes flattened into form rows (nesting caused overlap).
- HistoryDialog/MaintenanceDialog/ReviewLogDialog: themed headers, colored action
  lines (HTML; pinned substrings survive toPlainText), fixed-font detail panes.
- Tray menu: themed, icons via QIcon.fromTheme, "Run in Terminal" title case, bold
  Run Topgrade + status row. run_tray applies app-wide theme.
- Tests: label assertion updated to "Run in Terminal" (168 pass). ruff + mypy src clean.
- Gotcha: QSS-in-Python needs f-strings with doubled braces on EVERY segment; mixed
  plain/f-string concatenation silently emits `{{`.

## Session 2026-11-10 (evening): live-run findings + fixes

Replaced the running tray with the new build and ran a REAL topgrade session
(23 steps, 15+ minutes: pacman, firmware, npm, containers, GitHub CLI, Claude
Code, Ollama, Hermes Agent...). The redesigned UI tracked it correctly in dark
theme (KDE palette detection worked). Real-usage findings, all fixed:

- Spinner flicker: the 1s tick rebuilt the header and reset the icon to the
  static clock, fighting the 120ms spinner. Fix: `_state_kind` guard — icons
  only change on state transitions.
- Fake step totals: header read "Step N of N" because topgrade discovers steps
  lazily. Fix: "Step N · <current> · elapsed" (no denominator); progress bar
  stays a busy pulse during the run, fills on success, hides on failure.
- Stale "Running…" steps at exit (e.g. pacdiff died mid-step): `_finish` now
  sweeps pending/running steps to "— Ended".
- Diagnose drawer was a layout-squeezed sliver: now the bottom pane of a
  resizable vertical QSplitter (62% default on open, min 200px).
- NEW FEATURE — prompt surfacing: session parser detects `[Y/n]`-style
  questions (PromptRequest/PromptCleared; echo-on-same-line counts as an
  answer; trailing colon is decoration). RunWindow shows an amber prompt bar
  with Yes / No / Answer-in-terminal. Verified E2E with interactive fake
  commands over a real PTY.

Monitoring artifacts: run transcripts in ~/.local/share/topgrade-update/runs/
(test harness runs used to pollute it — no injectable runs dir yet; consider
adding one for tests). Tray checker vs topgrade mismatch investigated: paru's
"marked out of date" list does NOT mean updates exist (paru said "nothing to
do"); the aur checker was right. 172 tests pass; ruff + mypy strict clean.

## Next round planned (2026-11-11)

- Plan written to `.planning/IMPROVEMENTS-2026-11.md` — 15 items in three
  priority tiers, grounded in the 2026-11-10 live-run findings (step-name
  timestamps, injectable runs dir, terminal overlap repro, failure reasons,
  askpass unification, prompt-bar v2, dry-run handoff, run history, persisted
  geometry, keyboard pass, per-source updates, i18n last, tray detail,
  liveness hint, housekeeping). Suggested order inside the file.

## Session 2026-11-12: polish & QoL round

Worked through .planning/IMPROVEMENTS-2026-11.md (status table there). Shipped:
step-name cleanup, injectable runs dir, failure reasons, typed prompt answers,
dry run -> "Run for real", silence hint, Runs tab in History, persisted
geometry, "Update only this source", keyboard shortcuts (Esc / Ctrl+1 / Ctrl+2 /
Ctrl+F), closing the run window keeps the update running, honest counts
(reboot is not an update), re-check during snooze, missing pacman-contrib
surfaced, safe left-click, error icon/dialog, replacing notifications, and
settings/CLI tidy (autostart toggle, minutes, Restore Defaults, --version,
exit-code epilog). Deliberately left for later: #3 terminal overlap
investigation, #12 i18n; #15 housekeeping is partial. Large modules split
(DiagnosePanel, run_simple_page, tray_logic helpers) to stay under 800 lines.

Gotchas:
- Qt 6 `QApplication.quit()` aborts when a window ignores its close event, so
  Tray Quit shuts the run window down explicitly first (`RunWindow.shutdown`).
- Offscreen windows are never active, so every finished run would send a real
  notification; GUI tests patch `run_window.send_message` (and
  `diagnose_panel.send_message`) via tests/gui/conftest.py.
- QSettings path is isolated in tests/conftest.py (with XDG dirs).
- The old run-mode toggle test overwrote the real ~/.config config.toml; the
  isolation fix closes that.
- An intermittent crash dump at pytest exit was seen once (not reproduced in 10
  reruns).

Review pass (code-reviewer) fixes: tray Quit now asks before stopping a
running update; a prompt re-shows a hidden run window; menu-style prompts are
raised only once output pauses (`parse_idle`, so a PTY read ending at "==>"
is not a prompt); transcript parsing is linear (7 MB in ~0.1 s, was ~7 s);
hand-edited non-minute intervals survive Save; a window closed before its
queued start never launches.

Offscreen screenshot pass (light + dark) found: Settings ~1050px tall was
squeezed on the 1536x864 display (checkboxes clipped) -> cards now scroll;
"Flatpak apps & runtimes" lost "&" to the mnemonic; Runs list too narrow.

Live check (2026-11-12, real tray restarted on the new build): user confirmed
the reboot banner + 1-update count, dry run -> "Run for real", closing
mid-run hides and the tray brings the window back, and the History Runs tab.
Still unverified live: Cancel/Quit "Stop the update?" confirmation (covered
by tests only), a real pacdiff / paru prompt via the text box, Update only
this source, xterm.js behavior in a long hidden run.

Tests: 231 passing; ruff and mypy clean.
