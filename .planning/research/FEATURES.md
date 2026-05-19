# Research: Linux Update Notifier Features & Capabilities

Date: 2026-05-19
Sources: Arch-Update, pactrack, apdatifier, kalu, nudge, paf-notify, package-update-indicator, Mint Update Manager, GNOME Software, DNF Automatic, plus bug trackers and UX discussions.

---

## Table Stakes (must have or users leave)

These are baseline expectations. Missing any of these causes users to uninstall or seek alternatives immediately.

1. **Tray icon with state indication** — At minimum: "up to date" vs "updates available". Users expect an icon change (color, badge, or overlay) so they can see status at a glance without opening anything. [Arch-Update](https://github.com/Antiz96/arch-update), [pactrack](https://github.com/greasycat/pactrack), [apdatifier](https://github.com/exequtic/apdatifier).

2. **Badge / count display** — Show the number of pending updates on or near the tray icon. This is the most common reason users install a notifier instead of relying on manual checks. [apdatifier](https://github.com/exequtic/apdatifier), [pactrack](https://github.com/greasycat/pactrack), [Arch-Update](https://github.com/Antiz96/arch-update).

3. **Desktop notification on new updates** — A transient OS notification (libnotify/DBus) when the pending update count changes from 0 to >0. Must include the count and ideally a source breakdown (e.g., "5 packages, 2 AUR, 1 Flatpak"). [Arch-Update](https://github.com/Antiz96/arch-update), [pactrack](https://github.com/greasycat/pactrack), [kalu](https://jjacky.com/kalu/).

4. **Click-to-update action** — Left-clicking the tray icon should open the update mechanism (terminal, dialog, or package manager). Right-click should expose a context menu with Refresh, Open Details, and Quit. [Arch-Update](https://github.com/Antiz96/arch-update), [pactrack](https://github.com/greasycat/pactrack), [paf-notify](https://github.com/JakubCzarnota/paf-notify).

5. **Periodic background checking** — Users expect checks to happen automatically without manual refreshes. Common defaults: 15–60 minutes. Implementation is almost always a systemd user timer or cron job. [Arch-Update timer](https://github.com/Antiz96/arch-update), [pactrack](https://github.com/greasycat/pactrack), [DNF Automatic](https://dnf.readthedocs.io/en/latest/automatic.html).

6. **Multi-source support (pacman + AUR + Flatpak)** — On Arch-based systems, supporting only pacman is insufficient. AUR and Flatpak are expected. Auto-detect presence of helpers (`paru`, `yay`) and `flatpak` rather than requiring explicit configuration. [Arch-Update](https://github.com/Antiz96/arch-update), [apdatifier](https://github.com/exequtic/apdatifier), [kalu](https://jjacky.com/kalu/).

7. **Distinguish sources in UI** — Show which updates come from official repos vs AUR vs Flatpak. Users treat these very differently (trust level, build time, breakage risk). [Arch-Update tray menu](https://github.com/Antiz96/arch-update), [apdatifier](https://github.com/exequtic/apdatifier).

8. **Last check timestamp** — Show when the last check occurred in the tray menu or dialog. Users need to know if the count is stale. [Arch-Update](https://github.com/Antiz96/arch-update), [pactrack](https://github.com/greasycat/pactrack).

---

## Differentiators (competitive advantage)

These features separate good notifiers from basic ones and drive user loyalty.

1. **Arch Linux News integration** — Check for news items published since the last update run and offer to display them before updating. This is highly valued by Arch users because news often contains mandatory manual interventions. [Arch-Update](https://github.com/Antiz96/arch-update), [apdatifier](https://github.com/exequtic/apdatifier).

2. **Post-update maintenance helpers** — Offer to check for and handle orphans, old cached packages, pacnew/pacsave files, and services needing restart. These are standard Arch maintenance steps; automating the reminders is a major differentiator. [Arch-Update](https://github.com/Antiz96/arch-update).

3. **Kernel/reboot required detection** — Detect if a kernel or critical system package was updated and prompt the user to reboot. Some tools (e.g., `needrestart`, `checkrestart`) can detect services needing restart without a full reboot. [Arch-Update](https://github.com/Antiz96/arch-update), [systemd reboot-needed discussions](https://github.com/systemd/systemd/issues/26200).

4. **Configurable check interval with sensible bounds** — Allow users to tune the polling interval (e.g., 5 min to 24 h). Clamp to reasonable bounds to avoid abuse. Expose this in a GUI preferences dialog, not just a config file. [pactrack](https://github.com/greasycat/pactrack) (TOML), [Linux Mint](https://www.howtogeek.com/739177/how-to-configure-or-disable-linux-mint-update-notifications/) (GUI), [nudge](https://github.com/otmof-ops/nudge) (scheduling + deferral).

5. **Notification quiet hours / Do Not Disturb awareness** — Respect the desktop environment's DND mode (e.g., KDE Plasma's global DND, GNOME's notification settings). On KDE, check `org.freedesktop.Notifications` inhibition or Plasma DND state. On GNOME, notifications can be marked with urgency. [KDE System Notification Settings](https://docs.kde.org/stable_kf6/en/plasma-workspace/kcontrol/notifications/).

6. **Update list preview in tray menu** — A right-click dropdown showing the actual package names and versions for each source, not just counts. Clicking a package opens its upstream URL in the browser. This saves users from opening a terminal just to see what's new. [Arch-Update tray menu](https://github.com/Antiz96/arch-update).

7. **Consent-first / non-intrusive philosophy** — Tools like [nudge](https://github.com/otmof-ops/nudge) explicitly frame themselves as "ask before acting." Features: deferral ("remind me in X hours"), skip this version, schedule updates for a later time. Reduces notification fatigue and builds trust.

8. **Firmware update awareness** — Integrate `fwupdmgr` to show firmware updates alongside package updates. This is increasingly expected on modern laptops. [apdatifier](https://github.com/exequtic/apdatifier), [GNOME Software](https://github.com/GNOME/gnome-software).

9. **Terminal emulator auto-detection** — When launching an upgrade, detect and use the user's preferred terminal (via `xdg-terminal-exec`, `$TERMINAL`, or a ranked fallback list). Do not hardcode one terminal. [Arch-Update terminal handling](https://github.com/Antiz96/arch-update).

10. **Colorblind-friendly icon variants** — Provide tray icon styles that do not rely solely on red/green discrimination (e.g., blue + shape variants). [Arch-Update icon variants](https://github.com/Antiz96/arch-update/tree/main/res/icons).

11. **Internationalization (i18n)** — Translate the UI and notifications. Even basic gettext support dramatically broadens the user base. [Arch-Update translations](https://github.com/Antiz96/arch-update/tree/main/po), [apdatifier translations](https://github.com/exequtic/apdatifier/tree/main/package/translate).

12. **One-shot / diagnostic CLI mode** — Allow running a single check from the terminal (`--once`) for scripting or debugging. Useful for CI, dotfiles, and troubleshooting. [pactrack](https://github.com/greasycat/pactrack), [Arch-Update `--check`](https://github.com/Antiz96/arch-update).

---

## Anti-features (things to deliberately NOT build)

Features that seem helpful but generate user hostility, support burden, or security risk.

1. **Automatic installation of updates** — Do not install updates without explicit user confirmation. On Arch, automatic updates can break the system (partial upgrades, AUR build failures, manual interventions). Even on stable distros, users distrust silent updates. [Firefox update design principles](https://firefox-source-docs.mozilla.org/toolkit/mozapps/update/docs/DesignPrinciples.html), [nudge consent-first philosophy](https://github.com/otmof-ops/nudge).

2. **Auto-reboot after updates** — Never reboot without explicit user consent. Rebooting interrupts work and can cause data loss. At most, *notify* that a reboot is needed. [systemd reboot-needed discussions](https://github.com/systemd/systemd/issues/26200).

3. **Forced / modal blocking dialogs** — Do not steal focus or present a dialog that blocks the entire desktop until the user acts. Use tray indicators and transient notifications instead. Modal update dialogs are a top complaint against Windows/macOS updaters and some Linux notifiers. [Sparkle gentle reminders](https://sparkle-project.github.io/documentation/gentle-reminders).

4. **Unsuppressible repeated notifications** — If the user dismisses a notification, do not re-notify on every check cycle unless the *set* of available updates has changed. Re-notifying every 15 minutes for the same 5 packages is the #1 complaint in bug trackers. [Ubuntu bug 1582510](https://bugs.launchpad.net/ubuntu/+source/update-notifier/+bug/1582510), [Ubuntu bug 2008212](https://bugs.launchpad.net/bugs/2008212).

5. **Hard dependency on root privileges for checking** — Checking for available updates should not require root. Use `fakeroot`, temporary sync DB copies, or non-root helpers (e.g., `checkupdates` from `pacman-contrib`). Requiring root just to *check* reduces security and prevents the tray app from running as a normal user process. [kalu](https://jjacky.com/kalu/) explicitly avoids root for checking.

6. **Bundled/package manager lock-in** — Do not force a specific AUR helper or terminal emulator. Auto-detect and allow override. Hardcoding `yay` or `konsole` alienates users of `paru` or `alacritty`. [Arch-Update auto-detection](https://github.com/Antiz96/arch-update).

7. **Phased / esm nagware** — Avoid showing upsell messages or subscription nags (e.g., "Enable ESM for more updates"). These are widely reported as anti-features. [Ubuntu bug 2015420](https://bugs.launchpad.net/bugs/2015420), [Ubuntu bug 1926990](https://bugs.launchpad.net/bugs/1926990).

8. **Singleton package manager UI replacement** — Do not attempt to replace `pamac`, `octopi`, or the terminal entirely. Users who want a full package manager GUI already have one. A notifier that tries to do too much becomes bloated and competes with mature tools. Stay focused on *notification* and *launching* the user's preferred upgrader.

9. **Network polling without timeout** — Never issue blocking network requests without a timeout. AUR and Flatpak servers can be slow or down; hanging the tray app or check timer is a critical UX failure. [Arch-Update added 30s default timeout after Flatpak downtime issues](https://github.com/Antiz96/arch-update/commit/28d7d4ebdccc93c8c7cb733be3c4c76ad5dc692a).

10. **Heavy runtime dependency** — Avoid requiring a web engine, full GTK/Qt app framework beyond what the tray needs, or a database server. Lightweight tools win in the Arch community. `paf-notify` and `nudge` advertise "zero compiled dependencies" as a feature.

---

## Complexity Notes for Each Feature

| Feature | Complexity | Notes |
|---------|-----------|-------|
| Tray icon with badge | Low | PyQt6 `QSystemTrayIcon` + `setIcon()` with dynamically generated badge overlay. Or use pre-generated icon states. |
| Desktop notification | Low | `notify2` or direct DBus `org.freedesktop.Notifications`. Must handle notification actions (buttons) if supported by the DE. |
| Periodic checking | Low-Medium | systemd user timer is the modern standard. Need to ship `.timer` and `.service` units. Alternative: internal QTimer (runs only while tray is active; loses checks if tray crashes). |
| Multi-source support | Medium | Spawn `checkupdates`, `paru -Qu`, `flatpak remote-ls` (or `flatpak update --appstream` + `flatpak update --dry-run`). Parse text output. Need to handle missing helpers gracefully. |
| Source breakdown in UI | Low | Maintain separate lists; render grouped menu or tabbed dialog. |
| Arch News check | Medium | Scrape or RSS-parse `archlinux.org/news`. Need to persist "last seen news ID/date" to avoid re-showing. |
| Post-update helpers | Medium-High | Orphans: `pacman -Qdt`. Cache: `paccache`. Pacnew: `pacdiff`. Services: `needrestart` or `checkrestart`. Each requires privilege escalation and interactive confirmation. |
| Kernel/reboot detection | Low-Medium | Compare running kernel (`uname -r`) against newest installed (`pacman -Q linux`). Or use `needrestart`/`checkrestart`. |
| Configurable interval | Low | Store integer minutes in config. Apply to systemd timer (requires timer reload) or internal scheduler. |
| DND awareness | Medium | KDE: check `org.kde.PlasmaShell` or notification inhibition. GNOME: rely on urgency levels (`low`/`normal`/`critical`). Full cross-DE DND is inconsistent. |
| Update list preview | Medium | Parse package lists into menu items. Dynamic `QMenu` generation. Link click to `xdg-open` for upstream URL. |
| Consent/deferral | Medium | Add "Remind me in X" and "Skip until next version" state. Requires persisting deferral timestamps and ignored versions. |
| Firmware awareness | Low-Medium | Shell out to `fwupdmgr get-updates`. Parse JSON or text output. Optional dependency. |
| Terminal auto-detection | Medium | Try `xdg-terminal-exec`, then `$TERMINAL`, then ranked fallbacks. Edge cases: Wayland, terminal in container/flatpak. |
| Colorblind icons | Low | Ship 2–3 SVG icon sets; config switch. |
| i18n | Low-Medium | Wrap strings in `gettext()` early. Provide `.pot` template. Community will contribute translations if infrastructure exists. |
| One-shot CLI mode | Low | Refactor check logic so it can run headless and print to stdout, then exit. |

---

## Dependencies Between Features

```
Multi-source support
  → Source breakdown in UI
  → Update list preview
  → Badge / count display

Periodic checking
  → Desktop notification (only notify on transition 0→N or N→M change)
  → Last check timestamp

Desktop notification
  → DND awareness (notifications should respect DND)
  → Consent/deferral (notification actions for "Later" / "Details")

Tray icon with state
  → Click-to-update action
  → Update list preview (right-click menu)

Arch News check
  → Click-to-update action (show news before running upgrade)

Kernel/reboot detection
  → Post-update helpers (often shown together in maintenance flow)

Post-update helpers
  → Terminal auto-detection (helpers run in terminal with sudo)
  → Configurable privilege elevation (sudo/doas/run0)

i18n
  → All user-visible strings (should be wrapped from day 1)
```

Key insight from the research: **notification state machines are the hardest part**. The simple check-notify loop quickly becomes complex when you add:
- Deduplication (don't re-notify for the same packages)
- Deferral ("remind me in 4 hours")
- Count transitions (notify on 0→5, but not on every 5→5 check)
- DND / quiet hours
- Multiple sources with different check latencies

Plan the notification state machine early; the rest is mostly shelling out to existing tools and rendering results.

---

## Sources

### Kept
- **Arch-Update** (https://github.com/Antiz96/arch-update) — Most similar existing tool: PyQt6 tray, pacman+AUR+Flatpak, systemd timer, news check, post-update helpers. Primary reference.
- **pactrack** (https://github.com/greasycat/pactrack) — Rust-based tray notifier with clean TOML config, auto-detected helpers, notification-on-change logic.
- **apdatifier** (https://github.com/exequtic/apdatifier) — KDE Plasma widget with compact/extended list views, firmware support, terminal multiplexer integration.
- **kalu** (https://jjacky.com/kalu/) — Classic Arch notifier; important for "no root for checking" pattern and watched-packages feature.
- **nudge** (https://github.com/otmof-ops/nudge) — Consent-first philosophy, scheduling/deferral, multi-distro bash implementation.
- **Ubuntu update-notifier bugs** (Launchpad) — Primary source for anti-features: nag frequency, ESM nagware, phased update bugs.
- **systemd reboot-needed issue** (https://github.com/systemd/systemd/issues/26200) — Design discussion for reboot notification standards.
- **Sparkle gentle reminders** (https://sparkle-project.github.io/documentation/gentle-reminders) — Cross-platform UX best practices for non-intrusive update reminders.
- **KDE System Notification Settings** (https://docs.kde.org/stable_kf6/en/plasma-workspace/kcontrol/notifications/) — DND mode and notification behavior reference.

### Dropped
- **GNOME Software / PackageKit** — Too high-level; focuses on app store UX rather than tray notifier patterns. Not directly comparable to a lightweight Arch notifier.
- **Generic DE comparison articles** — KDE vs GNOME philosophy pieces; not actionable for feature design.
- **yumex / up2date** — Legacy Fedora tools; no longer relevant.
- **Electron auto-updater discussions** — macOS/Windows-centric; Linux package managers work differently.

---

## Gaps

- **Exact DBus API for KDE Plasma DND state** — Could not find a definitive spec. Likely requires querying `org.kde.PlasmaShell` or `org.freedesktop.Notifications` properties. A follow-up query against KDE source or KWin docs would help.
- **Wayland tray icon portability** — `QSystemTrayIcon` on Wayland is inconsistent across compositors. Need to test on sway/Hyprland/GNOME Wayland. Some users rely on `libappindicator` or `libayatana-appindicator` bridges.
- **Notification action button support across DEs** — "Update now" / "Later" buttons in notifications work well in GNOME/KDE but may silently fail or show plain text in dunst/mako. Need compatibility testing.
- **Flatpak dry-run / listing performance** — `flatpak update --dry-run` can be slow. Arch-Update uses `flatpak remote-ls --cached` after an `update --appstream`. Need to benchmark this vs other approaches.
- **AUR RPC rate limits** — Tools that query AUR directly (rather than via helper) may hit rate limits. Our current approach likely uses `paru`/`yay` which handle this internally, but worth documenting.
