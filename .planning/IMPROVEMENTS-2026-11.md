# Improvement Round: 2026-11-11 — "Wears Well"

**Basis:** findings from the 2026-11-10 live validation run (23 real topgrade
steps monitored end-to-end on the host) plus the 2026-11-10 UI redesign review.
Previous round: 2026-11-05 plan (implemented; see STATE.md sessions).

**Theme:** the app now works under real conditions; this round makes it wear
well — clean step naming, honest state, deeper prompt handling, persisted
layout, and closing the test-isolation debt we hit twice.

---

## P1 — Correctness & cleanliness (evidence-backed)

### 1. Strip timestamps from step names
The checklist shows "22:52:35 - Sudo — Done". `_SEPARATOR_BOX_RE` already
captures the time group separately, but `_SEPARATOR_PLAIN_RE` (``―― name ――``)
does not, so plain separators yield "22:52:35 - Sudo" as the step name. Add the
optional time group to the plain regex; keep identity stable by parsing, not
display-trimming.
**Tests:** parser fixtures with both separator styles + timestamps.

### 2. Injectable runs directory
`TopgradeSession` always writes transcripts to `default_runs_dir()`; RunWindow
tests and screenshot harnesses polluted the real `~/.local/share/topgrade-
update/runs/` twice. Add `runs_dir: Path | None = None` through TopgradeSession
→ RunWindow; tests/harnesses pass tmp dirs. `list_run_logs` is already
parameterized.
**Tests:** session writes to the injected dir; default unchanged.

### 3. Terminal overlap artifact
During the live run, topgrade's red "Cursor extensions failed" block was
overprinted by a later step header in the xterm.js pane. Determine whether
topgrade genuinely redraws (then document, no fix) or xterm.js mishandles an
escape (fix in `gui/assets/xterm/terminal.html`). Repro: replay the saved
transcript chunk through TerminalWidget.write() offscreen and diff against a
real terminal.
**Outcome:** fix or an evidence note in this file.

### 4. Failure detail beyond exit code
The failure hero says "'Cursor extensions' failed · Exit code 1". StepEvent
already carries `reason` (from the summary table's `NAME: FAILED: reason`) —
surface it in the header subtitle and failure hero, truncated to one line with
the full text in the Diagnose prompt.

### 5. Unify sudo/askpass UX with the prompt bar
Askpass currently opens a modal QInputDialog unannounced. Keep the secure
input, but announce it in the prompt-bar strip ("Password required for step X")
and parent-center the dialog, so Simple-mode users aren't surprised.

---

## P2 — UX depth

### 6. Prompt bar v2: free-text answers
Bracket-detection covers y/n. pacdiff-style numbered menus and other text
answers need an inline QLineEdit in the prompt bar (submit → write + newline).
Keep Yes/No shortcuts; keep "Answer in terminal" as the escape hatch.
**Tests:** parser for menu-style prompts; UI submit path.

### 7. Dry-run → real-run handoff
After a successful `--dry-run` RunWindow finishes, show a primary
"Run for real" button (spawn a normal RunWindow). The preview loop currently
dead-ends at "All done!".

### 8. Run history from transcripts
HistoryDialog gains a "Runs" tab: past RunWindow transcripts (timestamp,
duration, outcome, failed step) parsed from `runs/*.log` — pacman.log sessions
stay as the first tab. Rewind: `list_run_logs` + summary-table regex already
provide the data.

### 9. Persist geometry & splitter positions
QSettings (`org/topgrade-update`): run-window size, step-list split, diagnose
split, updates-dialog size. Clamp to the current screen on restore.

### 10. Keyboard pass
Esc closes the run window only when finished (never mid-run);
Ctrl+F focuses the updates filter; Ctrl+1/2 toggle Simple/Verbose. Tooltip
hints for each.

### 11. Per-source "update only this"
Source header action in the updates dialog → RunWindow with
`topgrade --only <step>`. First verify topgrade's `--only` names map cleanly
(pacman→"System update", aur→?); if the mapping is brittle, drop this item.

---

## P3 — Larger bets

### 12. i18n/gettext (carried from 2026-11-05, still active)
Wrap strings LAST in this round — new strings (prompt bar, heroes) are still
appearing; wrapping now means re-wrapping.

### 13. Tray detail surface
Tooltip per-source counts (today: total + failures only); notification actions
deep-linking "View" to the specific source's packages.

### 14. "No output for…" liveness hint
The npm step sat silent ~7 minutes (spinner covered it). If the current step
has produced no output for >2 min, append "no output for 2:34" to the
subtitle — distinguishes slow-but-alive from hung without changing the design.

### 15. Housekeeping
- Verify autostart on this machine: `~/.config/autostart/` had no
  topgrade-update entry; run the install script flow or confirm the user
  declined autostart.
- Keep rebase-before-push discipline (bot/CI commits land on origin/main).
- Consider CI: run the offscreen screenshot harness as a smoke check.

---

## Verification protocol for this round

1. One monitored real run per major item (recipe in memory:
   run window in background, poll `runs/` newest transcript, raise window via
   KWin script, capture with `spectacle -a`).
2. Prompt bar exercised against a real `paru -c` / `pacdiff`.
3. Every touched surface screenshot-verified light + dark.
4. `ruff`, `mypy --strict` (src), `pytest` green; no test writes outside tmp.

**Suggested order:** 1 → 2 → 4 → 5 → 3 → 6 → 9 → 10 → 7 → 8 → 11 → 14 → 13 → 15 → 12.

---

## Status (2026-11-12)

| # | Item | Status |
|---|------|--------|
| 1 | Strip timestamps from step names | done (df89086) |
| 2 | Injectable runs directory | done (df89086) |
| 3 | Terminal overlap artifact | not done (deliberately left for later) |
| 4 | Failure detail beyond exit code | done (a7d6c84) |
| 5 | Unify sudo/askpass UX with prompt bar | done (f56a5ef) |
| 6 | Prompt bar v2: free-text answers | done (a7d6c84) |
| 7 | Dry-run to real-run handoff | done (a7d6c84) |
| 8 | Run history from transcripts | done (52ef899) |
| 9 | Persist geometry and splitter positions | done (d07c42f) |
| 10 | Keyboard pass | done (f56a5ef Esc, Ctrl+1/2; d07c42f Ctrl+F) |
| 11 | Per-source "update only this" | done (d07c42f) |
| 12 | i18n / gettext | not done (deliberately left for later) |
| 13 | Tray detail surface | partial: per-source tooltip counts done (06ccc90); per-source "View" notification deep-link not done |
| 14 | "No output for..." liveness hint | done (a7d6c84) |
| 15 | Housekeeping | partial: test isolation done (df89086); autostart verification and CI screenshot smoke check not done |

### Added beyond the 15

- Reboot is a state, not an update: excluded from counts and the notification engine (06ccc90)
- Forced re-check while snoozed (run finished, pacman db change) (06ccc90)
- Missing `pacman-contrib` surfaced as a clear checker error (06ccc90)
- Safe default left-click: shows updates instead of launching topgrade (06ccc90)
- Error icon and Updates dialog opening for check errors / pending reboot (06ccc90, cb79511)
- Notifications replace each other instead of stacking (06ccc90)
- Settings and CLI tidy: every source listed, interval in minutes, autostart toggle, Restore Defaults, `--version`, exit-code epilog (6e53adc)
- Test isolation fix: XDG dirs and QSettings isolated per test; the run-mode test no longer overwrites the real config.toml (df89086)
- Closing the run window keeps the update running; Cancel asks first; desktop notification when a hidden run finishes or needs an answer (f56a5ef)

