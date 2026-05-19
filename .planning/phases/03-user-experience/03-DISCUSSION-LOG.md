# Phase 3: User Experience - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 03-user-experience
**Areas discussed:** Notification deduplication, Quiet hours, Tray click behavior, topgrade.toml integration, Notification actions

---

## Notification Deduplication

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — 0→N only | Notify only when first updates appear, never re-notify | |
| B — 0→N and increase | Notify on first appearance AND when count grows | ✓ |
| C — Any change | Keep current behavior, notify on any count change | |

**User's choice:** B — 0→N and increase
**Notes:** Chose to notify when new updates are detected (count goes up), but not on decrease or repeated checks. Prevents spam while still surfacing new available updates.

---

## Quiet Hours

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Suppress only | Checks run, notifications silently dropped | |
| B — Skip checks | Timer pauses, no checking during quiet hours | |
| C — Defer and batch | Checks run, notifications queued and batched when quiet hours end | ✓ |

**User's choice:** C — Defer and batch
**Notes:** Chose the richest UX — checks continue silently, but notifications are held and delivered as a single batch summary when quiet hours end. Matches Android DND behavior user referenced.

---

## Tray Click Behavior

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Fixed | Current behavior hardcoded, no config | |
| B — Configurable | `tray.click_action` config option | ✓ |
| C — Context-aware with modifier | Default + Shift to invert | |

**User's choice:** B — Configurable
**Notes:** User wants explicit control over left-click behavior via config file. Default remains current behavior for backwards compatibility.

---

## topgrade.toml Integration

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — Source-level only | Map topgrade steps to our checkers only | |
| B — Full step awareness | Handle categories, granular steps, execution flags | ✓ |
| C — Minimal | Log warnings only, don't change behavior | |

**User's choice:** B — Full step awareness
**Notes:** User wants deep integration with topgrade config. If a step is disabled in topgrade.toml, our checker should respect that.

---

## Notification Actions

| Option | Description | Selected |
| ------ | ----------- | -------- |
| A — notify-send only | Simple, no action buttons | |
| B — DBus library only | Rich actions, but new dependency | |
| C — Hybrid | Try DBus first, fall back to notify-send | ✓ |

**User's choice:** C — Hybrid
**Notes:** Best of both worlds — action buttons when available, graceful fallback everywhere else. User explicitly mentioned wanting "Run Topgrade" and "Snooze" actions.

---

## the agent's Discretion

- Exact DBus library choice
- Notification queue implementation
- topgrade.toml parsing strategy
- Snooze persistence mechanism
- Topgrade step-to-checker mapping table

## Deferred Ideas

- Firmware update checker (fwupdmgr) — v2
- Post-update maintenance helpers — v2
- Kernel/reboot detection — v2
- Internationalization — v2
