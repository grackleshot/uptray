# Progress

## Status
In Progress

## Tasks
- [x] Research features and capabilities for Linux system update notifier applications
- [x] Write findings to `.planning/research/FEATURES.md`

## Files Changed
- `.planning/research/FEATURES.md` — Comprehensive research brief covering table stakes, differentiators, anti-features, complexity notes, and feature dependencies.

## Notes
- Research examined Arch-Update, pactrack, apdatifier, kalu, nudge, paf-notify, Mint Update Manager, DNF Automatic, and upstream bug trackers.
- Key finding: notification state machines (deduplication, deferral, DND, count transitions) are the hardest UX problem.
- Anti-features identified: auto-install, auto-reboot, modal blocking dialogs, unsuppressible repeat notifications, root-required checking, nagware.
- Recommended config approach: simple flat file (INI or TOML) at `~/.config/<app>/<app>.conf`, with optional GUI settings dialog.
