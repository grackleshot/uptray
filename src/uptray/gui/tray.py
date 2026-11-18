"""System tray applet implementation."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from PySide6.QtCore import QFileSystemWatcher, QSocketNotifier, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QSystemTrayIcon

from uptray.core.arch_news import NewsItem, fetch_news, new_items, newest_marker
from uptray.core.checkers import check_all, find_terminal, has_package_sources, total_updates
from uptray.core.config import load_config, save_config
from uptray.core.history import parse_pacman_log
from uptray.core.links import upstream_url
from uptray.core.logging import get_logger
from uptray.core.maintenance import maintenance_summary
from uptray.core.models import CheckResult, Config
from uptray.core.network import is_online
from uptray.core.notification_engine import NotificationEngine
from uptray.core.notifications import (
    NotificationClient,
    format_source_counts,
    send_message,
    send_notification,
)
from uptray.core.quiet_hours import is_quiet_hours
from uptray.core.state import (
    AppState,
    format_snooze,
    load_state,
    parse_snooze,
    save_state,
)
from uptray.gui.dialog import (
    HistoryDialog,
    MaintenanceDialog,
    UpdatesDialog,
    open_url,
)
from uptray.gui.icons import IconCache
from uptray.gui.run_window import RunWindow
from uptray.gui.settings import SettingsDialog
from uptray.gui.style import apply_app_theme, apply_theme
from uptray.gui.tray_logic import (
    OFFLINE_RETRY_MS,
    PACMAN_DEBOUNCE_MS,
    PACMAN_LOCAL_DB_DIR,
    RESUME_CHECK_DELAY_MS,
    _acquire_instance_lock,
    _watch_resume,
    is_reboot_pending,
    is_snoozed,
    local_now,
    next_local_midnight,
    pacman_watch_dir,
    remaining_ms,
    snooze_label,
)

APP_NAME = "Uptray"
APP_ID = "uptray"
_ICON_NAME = "uptray"
_MAX_MENU_PACKAGES = 15
_MAX_NEWS_ITEMS = 8
_CHECK_SHUTDOWN_TIMEOUT_MS = 10_000


class CheckThread(QThread):
    """Background thread for non-blocking update checks and news fetches."""

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self.results: list[CheckResult] = []
        self.news: list[NewsItem] | None = None

    def run(self) -> None:
        try:
            self.results = check_all(self._cfg)
        except Exception as exc:
            self.results = [CheckResult(source="update check", error=str(exc))]
        try:
            self.news = fetch_news(timeout=10.0)
        except Exception as exc:
            get_logger("tray").debug("Arch news fetch skipped: %s", exc)


def launch_topgrade_in_terminal(
    cfg: Config | None = None,
    extra_args: list[str] | None = None,
) -> None:
    """Launch topgrade (optionally with extra arguments) in a terminal."""
    topgrade = shutil.which("topgrade")
    if topgrade is None:
        send_message("Topgrade not found", "Install topgrade before trying to run it.")
        return
    term, args = find_terminal(cfg)
    if term is None:
        send_message("Error", "No terminal emulator found.")
        return
    try:
        subprocess.Popen([term] + args + [topgrade] + (extra_args or []))
    except OSError as exc:
        get_logger("tray").exception("Could not launch topgrade terminal")
        send_message("Could not launch Topgrade", str(exc))


class Tray(QSystemTrayIcon):
    """System tray icon with periodic update checking."""

    notification_action = Signal(str)
    resume_detected = Signal()

    def __init__(
        self,
        cfg: Config,
        pacman_db_dir: Path = PACMAN_LOCAL_DB_DIR,
        debounce_ms: int = PACMAN_DEBOUNCE_MS,
        state_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._cfg = cfg
        self._state_path = state_path
        self._results: list[CheckResult] = []
        self._last_check: datetime | None = None
        self._snooze_until: datetime | None = None
        self._notification_engine = NotificationEngine()
        self._notification_client = NotificationClient()
        self.notification_action.connect(self._on_notification_action)
        self._notification_client.start_action_listener(self.notification_action.emit)
        self._icon_cache = IconCache(cfg.tray.icon_style)
        self._check_thread: CheckThread | None = None
        self._check_superseded = False
        self._verifying = False
        self._offline = False
        self._closing = False
        self._run_window: RunWindow | None = None

        # Persistent state: restore snooze and notification dedup count.
        self._state: AppState = load_state(state_path)
        restored_snooze = parse_snooze(self._state.snooze_until)
        if restored_snooze is not None and is_snoozed(restored_snooze):
            self._snooze_until = restored_snooze
        self._notification_engine.prev_total = self._state.prev_total

        self._snooze_timer = QTimer()
        self._snooze_timer.setSingleShot(True)
        self._snooze_timer.timeout.connect(self._on_snooze_expired)
        if self._snooze_until is not None:
            self._snooze_timer.start(remaining_ms(self._snooze_until))

        # Arch news state.
        self._news_items: list[NewsItem] = []
        self._news_new_count = 0

        self.setToolTip(APP_NAME)

        # Context menu
        self._menu = QMenu()
        self._build_menu()
        self.setContextMenu(self._menu)

        self.activated.connect(self._on_activated)

        # Periodic check timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._start_check)
        self._timer.start(cfg.check_interval * 1000)

        # Offline retry loop (started only while offline).
        self._offline_retry = QTimer()
        self._offline_retry.setSingleShot(True)
        self._offline_retry.timeout.connect(self._start_check)

        # pacman database watcher: re-check shortly after packages change.
        self._db_debounce = QTimer()
        self._db_debounce.setSingleShot(True)
        self._db_debounce.setInterval(debounce_ms)
        self._db_debounce.timeout.connect(self._on_pacman_db_changed)
        self._fs_watcher = QFileSystemWatcher()
        watch_dir = pacman_watch_dir(pacman_db_dir)
        if watch_dir is not None:
            self._fs_watcher.addPath(str(watch_dir))
            self._fs_watcher.directoryChanged.connect(self._on_db_changed_signal)

        # Resume-from-suspend watcher (logind PrepareForSleep via jeepney).
        self.resume_detected.connect(self._on_resume_detected)
        self._resume_stop = Event()
        self._resume_thread = Thread(
            target=_watch_resume,
            args=(self.resume_detected.emit, self._resume_stop),
            name="topgrade-resume-watcher",
            daemon=True,
        )
        self._resume_thread.start()

        # Restore snooze visibility; keep the tooltip clean until first check.
        if self._snooze_until is not None:
            self._update_status_action()
            self._update_tooltip()
        self.setIcon(self._icon_cache.idle())

        # Initial check after 3 seconds
        QTimer.singleShot(3000, self._start_check)

    # ------------------------------------------------------------------
    # Menu construction

    def _build_menu(self) -> None:
        apply_theme(self._menu)
        self._menu.clear()
        self._action_status = self._menu.addAction("Idle")
        self._action_status.setEnabled(False)
        status_font = self._action_status.font()
        status_font.setBold(True)
        self._action_status.setFont(status_font)
        self._menu.addSeparator()
        self._add_action("Check Now", "view-refresh", self._check_now)
        self._add_action("View Updates", "software-updates-available", self._show_updates)
        package_total = self._package_total()
        if package_total > 0 and not self._verifying:
            self._add_action(
                "Preview Updates (Dry Run)", "document-print-preview", self._preview_topgrade
            )
            self._menu.addSeparator()
            for result in self._results:
                if result.updates and result.source != "reboot":
                    self._add_source_menu(result)

        if self._news_items:
            self._menu.addSeparator()
            self._add_news_menu()

        self._menu.addSeparator()
        self._action_open_run = self._add_action(
            "Open current run", "window-restore", self._open_current_run
        )
        self._action_open_run.setVisible(self._active_run() is not None)
        run_action = self._add_action("Run Topgrade", "system-run", self._run_topgrade)
        run_font = run_action.font()
        run_font.setBold(True)
        run_action.setFont(run_font)
        self._add_action("Run in Terminal", "utilities-terminal", self._run_topgrade_terminal)
        self._menu.addSeparator()
        self._add_action("Update History…", "document-open-recent", self._show_history)
        self._add_action("Maintenance…", "user-trash", self._check_maintenance)
        self._add_action("Settings…", "preferences-system", self._open_settings)
        self._menu.addSeparator()
        snooze_menu = self._menu.addMenu("Snooze")
        snooze_menu.addAction("Snooze 1 hour", lambda: self._snooze(1))
        snooze_menu.addAction(
            f"Snooze {self._cfg.tray.snooze_hours} hours",
            lambda: self._snooze(self._cfg.tray.snooze_hours),
        )
        snooze_menu.addAction("Snooze until tomorrow", self._snooze_until_tomorrow)
        snooze_menu.addAction("Cancel snooze", lambda: self._snooze(None))
        self._menu.addSeparator()
        self._add_action("Quit", "application-exit", self._quit)

    def _add_action(self, label: str, icon_name: str, slot: Callable[[], object]) -> QAction:
        """Add a menu action with a themed icon when the platform provides one."""
        action = QAction(label, self._menu)
        action.setIcon(QIcon.fromTheme(icon_name))
        action.triggered.connect(slot)
        self._menu.addAction(action)
        return action

    def _add_source_menu(self, result: CheckResult) -> None:
        submenu = self._menu.addMenu(f"{result.source} ({len(result.updates)})")
        for update in result.updates[:_MAX_MENU_PACKAGES]:
            branch = f" ({update.branch})" if update.branch else ""
            submenu.addAction(
                f"{update.name}{branch}",
                self._package_opener(update.name, result.source),
            )
        hidden = len(result.updates) - _MAX_MENU_PACKAGES
        if hidden > 0:
            more = submenu.addAction(f"…and {hidden} more")
            more.setEnabled(False)

    def _package_opener(self, name: str, source: str) -> Callable[[], None]:
        def _open() -> None:
            open_url(upstream_url(name, source))

        return _open

    def _add_news_menu(self) -> None:
        label = "Arch News"
        if self._news_new_count:
            label = f"Arch News ({self._news_new_count} new)"
        news_menu = self._menu.addMenu(label)
        for item in self._news_items[:_MAX_NEWS_ITEMS]:
            prefix = "[NEW] " if self._is_news_new(item) else ""
            news_menu.addAction(f"{prefix}{item.title}", self._news_opener(item))
        news_menu.addSeparator()
        news_menu.addAction("Mark all news as read", self._mark_news_read)

    def _news_opener(self, item: NewsItem) -> Callable[[], None]:
        def _open() -> None:
            self._open_news_item(item)

        return _open

    # ------------------------------------------------------------------
    # Aggregation helpers

    def _updates_by_source(self) -> dict[str, int]:
        """Update counts per source for the latest results."""
        return {result.source: len(result.updates) for result in self._results}

    def _package_total(self) -> int:
        """Total updates excluding the reboot source (a state, not a package)."""
        return total_updates(self._results)

    # ------------------------------------------------------------------
    # Check lifecycle

    def _start_check(self, *, force: bool = False) -> None:
        # A stopped thread may still have its finished signal queued on the GUI thread.
        if self._closing or self._check_thread is not None:
            return
        if self._is_snoozed() and not (force or self._verifying):
            self._update_status_surfaces()
            return
        if not is_online():
            self._offline = True
            if not self._offline_retry.isActive():
                self._offline_retry.start(OFFLINE_RETRY_MS)
            self._update_status_surfaces()
            return
        self._offline = False
        self._offline_retry.stop()
        self.setIcon(self._icon_cache.checking())
        self._check_thread = CheckThread(self._cfg)
        self._check_thread.finished.connect(self._on_check_thread_finished)
        self._update_status_surfaces()
        self._check_thread.start()

    @Slot()
    def _on_check_thread_finished(self) -> None:
        thread = self._check_thread
        self._check_thread = None
        if thread is None or self._closing:
            return
        if self._active_run() is not None:
            # Completion of the active run will request a fresh scan.
            self._check_superseded = False
            self._update_status_surfaces()
            return
        if self._check_superseded:
            self._check_superseded = False
            self._start_check()
            return
        self._verifying = False
        self._on_check_done(thread.results, thread.news)

    def _on_run_finished(self, _returncode: int) -> None:
        if self._closing:
            return
        self._verifying = True
        self._check_superseded = self._check_thread is not None
        self._db_debounce.stop()
        self.setIcon(self._icon_cache.checking())
        self._build_menu()
        self._update_status_surfaces()
        self._start_check()

    def _on_check_done(self, results: list[CheckResult], news: object = None) -> None:
        previous_package_total = self._package_total()
        self._results = results
        self._last_check = local_now()
        counts = {result.source: len(result.updates) for result in results}
        package_total = total_updates(results)
        snoozed = self._is_snoozed()
        # Always advance dedup state so restarts/disabled periods don't re-notify.
        changed = self._notification_engine.should_notify(results)
        notifications_allowed = self._cfg.notifications.enabled and not snoozed

        if isinstance(news, list):
            self._news_items = [item for item in news if isinstance(item, NewsItem)]
            self._news_new_count = len(new_items(self._news_items, self._state.last_seen_news))

        quiet = is_quiet_hours(
            self._cfg.notifications.quiet_hours_start,
            self._cfg.notifications.quiet_hours_end,
        )

        if quiet and notifications_allowed:
            self._notification_engine.enter_quiet_hours()
            if changed:
                self._notification_engine.maybe_defer(results)
        else:
            deferred = self._notification_engine.exit_quiet_hours()
            if notifications_allowed and package_total > 0:
                if deferred:
                    self._send_deferred_notification(results, package_total)
                elif changed:
                    self._send_update_notification(results)

        reboot_pending = is_reboot_pending(counts)
        self._handle_reboot_notification(reboot_pending, snoozed=snoozed, quiet=quiet)

        self._refresh_icon(package_total, reboot_pending, results)
        if notifications_allowed and not quiet:
            self._maybe_maintenance_reminder(previous_package_total, package_total, results)

        self._persist_state()
        self._build_menu()
        self._update_status_surfaces()

    def _refresh_icon(
        self,
        total: int,
        reboot_pending: bool,
        results: list[CheckResult],
    ) -> None:
        if self._verifying or self._check_thread is not None or self._active_run() is not None:
            self.setIcon(self._icon_cache.checking())
        elif total > 0:
            self.setIcon(self._icon_cache.updates(total))
        elif reboot_pending:
            self.setIcon(self._icon_cache.reboot())
        elif any(result.error is not None for result in results):
            self.setIcon(self._icon_cache.error())
        elif not has_package_sources(results):
            self.setIcon(self._icon_cache.idle())
        else:
            self.setIcon(self._icon_cache.uptodate())

    # ------------------------------------------------------------------
    # Reboot / maintenance / news

    def _handle_reboot_notification(
        self, reboot_pending: bool, *, snoozed: bool, quiet: bool
    ) -> None:
        if not reboot_pending:
            self._state.reboot_notified = False
        elif (
            not self._state.reboot_notified
            and self._cfg.notifications.enabled
            and not snoozed
            and not quiet
        ):
            send_message(
                "Reboot required",
                "A kernel or system update needs a reboot to take effect.",
                urgency="critical",
                sound=self._cfg.notifications.sound,
            )
            self._state.reboot_notified = True

    def _maybe_maintenance_reminder(
        self,
        previous_total: int,
        total: int,
        results: list[CheckResult],
    ) -> None:
        """After an update session ends (N -> 0), remind once per day."""
        if previous_total <= 0 or total != 0 or not has_package_sources(results):
            return
        if any(result.error is not None for result in results):
            return
        if self._state.maintenance_check_date == date.today().isoformat():
            return
        try:
            findings = maintenance_summary()
        except Exception:
            get_logger("tray").exception("Maintenance check failed")
            return
        self._state.maintenance_check_date = date.today().isoformat()
        if findings:
            body = "\n".join(f"• {finding.summary}" for finding in findings)
            send_message(
                "Post-update maintenance",
                body,
                urgency="normal",
                sound=self._cfg.notifications.sound,
            )

    def _is_news_new(self, item: NewsItem) -> bool:
        """Match the feed-level rule: with no read marker nothing is new."""
        if self._state.last_seen_news is None:
            return False
        marker = parse_snooze(self._state.last_seen_news)
        return marker is not None and item.published > marker

    def _open_news_item(self, item: NewsItem) -> None:
        open_url(item.link)
        self._mark_news_read()

    def _mark_news_read(self) -> None:
        marker = newest_marker(self._news_items)
        if marker is not None:
            self._state.last_seen_news = marker
        self._news_new_count = 0
        self._persist_state()
        self._build_menu()
        self._update_status_surfaces()

    # ------------------------------------------------------------------
    # Status surfaces

    def _update_status_surfaces(self) -> None:
        self._action_open_run.setVisible(self._active_run() is not None)
        self._update_status_action()
        self._update_tooltip()

    def _check_status(self) -> str | None:
        if self._verifying:
            if self._offline:
                return "Verifying updates — waiting for network"
            return "Verifying updates…"
        if self._offline:
            return "Offline — waiting for network"
        if self._check_thread is not None:
            return "Checking…"
        return None

    def _package_status(self) -> str:
        package_total = self._package_total()
        if package_total > 0:
            return f"{package_total} update(s) available"
        failed = any(result.error is not None for result in self._results)
        if has_package_sources(self._results):
            return "Update check failed" if failed else "System is up to date"
        if failed:
            return "No package sources checked; update check failed"
        return "No package sources checked"

    def _update_tooltip(self) -> None:
        lines = [APP_NAME]
        run = self._active_run()
        if run is not None:
            lines.append(run.monitor_status)
        checking = self._check_status()
        if checking is not None:
            lines.append(checking)
        if self._last_check:
            lines.append(f"Last check: {self._last_check.strftime('%H:%M')}")
        if self._is_snoozed() and self._snooze_until is not None:
            lines.append(snooze_label(self._snooze_until))
        if run is None and checking is None and self._last_check is not None:
            lines.append(self._package_status())
            failed_sources = sum(result.error is not None for result in self._results)
            if self._package_total() > 0 and failed_sources:
                lines.append(f"{failed_sources} source check(s) failed")
            if is_reboot_pending(self._updates_by_source()):
                lines.append("Reboot required")
            counts = format_source_counts(self._results)
            if counts:
                lines.append(counts)
        if self._news_new_count:
            lines.append(f"{self._news_new_count} new Arch news item(s)")
        self.setToolTip("\n".join(lines))

    def _send_deferred_notification(self, results: list[CheckResult], total: int) -> None:
        self._send_update_notification(
            results,
            summary="Updates available after quiet hours",
            body=f"{total} update(s) currently available\n{format_source_counts(results)}",
        )

    def _send_update_notification(
        self,
        results: list[CheckResult],
        *,
        summary: str | None = None,
        body: str | None = None,
    ) -> None:
        """Send an update notification with actions when the desktop supports them."""
        send_notification(
            results,
            actions=[
                ("run_topgrade", "Run Topgrade"),
                ("snooze", "Snooze"),
                ("dismiss", "Dismiss"),
            ],
            summary=summary,
            body=body,
            on_action=self.notification_action.emit,
            client=self._notification_client,
            sound=self._cfg.notifications.sound,
        )

    def _on_notification_action(self, action_id: str) -> None:
        """Handle action buttons selected from a desktop notification."""
        if action_id == "run_topgrade":
            self._run_topgrade()
        elif action_id == "snooze":
            self._snooze(self._cfg.tray.snooze_hours)

    def _update_status_action(self) -> None:
        run = self._active_run()
        if run is not None:
            self._action_status.setText(run.monitor_status)
            return
        checking = self._check_status()
        if self._verifying and checking is not None:
            self._action_status.setText(checking)
            return
        if self._is_snoozed() and self._snooze_until is not None:
            self._action_status.setText(snooze_label(self._snooze_until))
            return
        if checking is not None:
            self._action_status.setText(checking)
            return
        if self._last_check is None:
            self._action_status.setText("Idle")
            return
        status = self._package_status()
        failed_sources = sum(result.error is not None for result in self._results)
        if self._package_total() > 0 and failed_sources:
            status += f"; {failed_sources} source(s) failed"
        if is_reboot_pending(self._updates_by_source()):
            status += " · Reboot required"
        status = f"{status} — Last check {self._last_check.strftime('%H:%M')}"
        self._action_status.setText(status)

    # ------------------------------------------------------------------
    # Snooze and state

    def _is_snoozed(self) -> bool:
        if not is_snoozed(self._snooze_until):
            self._snooze_until = None
            return False
        return True

    def _snooze(self, hours: int | None) -> None:
        if hours is None:
            self._apply_snooze(None)
            return
        self._apply_snooze(
            local_now() + timedelta(hours=hours),
            interval_ms=hours * 60 * 60 * 1000,
        )

    def _snooze_until_tomorrow(self) -> None:
        """Snooze until the next local midnight, not 24 hours from now."""
        self._apply_snooze(next_local_midnight())

    def _apply_snooze(self, until: datetime | None, *, interval_ms: int | None = None) -> None:
        self._snooze_until = until
        if until is None:
            self._snooze_timer.stop()
            self._notification_engine.reset_deduplication()
        else:
            self._notification_engine.exit_quiet_hours()
            delay = remaining_ms(until) if interval_ms is None else interval_ms
            self._snooze_timer.start(max(1, delay))
        self._persist_state()
        self._update_status_surfaces()
        if until is None:
            self._start_check()

    def _persist_state(self) -> None:
        self._state.snooze_until = format_snooze(self._snooze_until)
        self._state.prev_total = self._notification_engine.prev_total
        save_state(self._state, self._state_path)

    def _check_now(self) -> None:
        if self._is_snoozed():
            self._snooze_until = None
            self._snooze_timer.stop()
            self._notification_engine.reset_deduplication()
        self._start_check()

    def _on_snooze_expired(self) -> None:
        self._snooze_until = None
        self._notification_engine.reset_deduplication()
        self._persist_state()
        self._start_check()

    # ------------------------------------------------------------------
    # pacman watcher / resume

    def _on_db_changed_signal(self, _path: str) -> None:
        self._db_debounce.start()  # restarting the timer debounces bursts

    def _on_pacman_db_changed(self) -> None:
        self._start_check(force=True)

    def _on_resume_detected(self) -> None:
        """Re-check shortly after the system resumes from suspend."""
        QTimer.singleShot(RESUME_CHECK_DELAY_MS, self._start_check)

    # ------------------------------------------------------------------
    # Windows and actions

    def _show_updates(self) -> None:
        if self._verifying:
            send_message(
                "Verifying updates", "Package results will be available after the check."
            )
            return
        has_errors = any(result.error is not None for result in self._results)
        reboot_pending = is_reboot_pending(self._updates_by_source())
        if not (total_updates(self._results) or has_errors or reboot_pending):
            if self._last_check is None:
                send_message("No results yet", "Choose Check Now to check for package updates.")
            elif not has_package_sources(self._results):
                send_message("No package sources checked", "Check your update source settings.")
            else:
                send_message("No updates", "Your system is up to date.")
            return
        dlg = UpdatesDialog(self._results)
        dlg.set_on_run(self._run_topgrade)
        dlg.set_on_preview(self._preview_topgrade)
        dlg.set_on_run_only(self._run_topgrade)
        dlg.exec()

    def _show_history(self) -> None:
        try:
            sessions = parse_pacman_log()
        except OSError:
            sessions = []  # no pacman.log: the Runs tab is still useful
        HistoryDialog(sessions).exec()

    def _check_maintenance(self) -> None:
        try:
            findings = maintenance_summary()
        except Exception as exc:
            send_message("Maintenance check failed", str(exc))
            return
        if findings:
            self._state.maintenance_check_date = date.today().isoformat()
            self._persist_state()
            MaintenanceDialog(findings).exec()
        else:
            send_message("No maintenance needed", "Your system looks clean.")

    def _open_settings(self) -> None:
        # Reload so a run-window mode toggle (or other writer) is not overwritten.
        try:
            self._cfg = load_config()
        except (OSError, ValueError) as exc:
            get_logger("tray").warning("Could not reload configuration: %s", exc)
        dialog = SettingsDialog(self._cfg)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_config(dialog.get_config())

    def _apply_config(self, cfg: Config) -> None:
        self._cfg = cfg
        if not cfg.notifications.enabled:
            self._notification_engine.exit_quiet_hours()
        try:
            save_config(cfg)
        except OSError as exc:
            get_logger("tray").warning("Could not save configuration: %s", exc)
            QMessageBox.warning(None, APP_NAME, f"Could not save the configuration: {exc}")
        self._timer.setInterval(cfg.check_interval * 1000)
        if not self._timer.isActive():
            self._timer.start()
        if cfg.tray.icon_style != self._icon_cache.style:
            self._icon_cache = IconCache(cfg.tray.icon_style)
        self._refresh_icon(
            self._package_total(), is_reboot_pending(self._updates_by_source()), self._results
        )
        self._build_menu()
        self._update_status_surfaces()

    def _run_topgrade(self, extra_args: list[str] | None = None) -> None:
        self._open_run_window(list(extra_args or []), explain_if_running=True)

    def _preview_topgrade(self) -> None:
        self._open_run_window(["--dry-run"], title="Uptray — Dry Run", explain_if_running=True)

    def _run_topgrade_terminal(self) -> None:
        if not self._open_current_run():
            launch_topgrade_in_terminal(self._cfg)

    def _active_run(self) -> RunWindow | None:
        window = self._run_window
        return window if window is not None and window.is_active else None

    def _open_current_run(self) -> bool:
        window = self._active_run()
        if window is None:
            return False
        window.showNormal()
        window.raise_()
        window.activateWindow()
        window.focus_pending_input()
        return True

    def _explain_running_window(self) -> None:
        """Tell the user a new preview or update was not started."""
        window = self._active_run()
        if window is None:
            return
        kind = "preview" if getattr(window, "_is_dry_run", False) else "update"
        QMessageBox.information(
            window,
            APP_NAME,
            f"A {kind} is already running. This window shows that run.",
        )

    @Slot(str)
    def _on_monitor_status_changed(self, _status: str) -> None:
        self._update_status_surfaces()

    def _on_run_window_closed(self, window: RunWindow) -> None:
        # close() never frees this parentless window: Qt holds lambdas wired to its own
        # buttons, and they capture it. Each leaked window kept two WebEngine renderers.
        window.deleteLater()
        if self._run_window is window:
            self._run_window = None

    def _open_run_window(
        self,
        extra_args: list[str] | None = None,
        *,
        title: str | None = None,
        explain_if_running: bool = False,
    ) -> None:
        # Keep a strong reference so the non-modal window is not garbage-collected.
        # Reuse only while a session is still running; finished windows must not
        # block a new dry-run/update request.
        if self._open_current_run():
            if explain_if_running:
                self._explain_running_window()
            return
        if self._run_window is not None:
            self._run_window.close()  # finished, so it really closes and is deleted
        on_run_for_real: Callable[[], None] | None = None
        if extra_args and "--dry-run" in extra_args:
            update_args = [arg for arg in extra_args if arg != "--dry-run"]
            on_run_for_real = (
                partial(self._run_topgrade, update_args) if update_args else self._run_topgrade
            )
        window = RunWindow(
            self._cfg,
            extra_args=extra_args,
            title=title,
            on_finished=self._on_run_finished,
            on_run_for_real=on_run_for_real,
        )
        self._run_window = window
        window.monitor_status_changed.connect(self._on_monitor_status_changed)
        window.closed.connect(partial(self._on_run_window_closed, window))
        if window.is_active:
            self.setIcon(self._icon_cache.checking())
        self._update_status_surfaces()
        window.show()

    def _stop_run_window(self) -> None:
        window = self._run_window
        if window is not None:
            window.shutdown()

    def _quit(self) -> None:
        window = self._run_window
        if window is not None and not window.confirm_stop():
            return
        # Qt 6 aborts quit() when a window ignores its close event, and a
        # running RunWindow does; stop it explicitly first.
        self._closing = True
        self._stop_run_window()
        QApplication.quit()

    def shutdown(self) -> None:
        """Release background threads and the notification DBus connection."""
        self._closing = True
        self._stop_run_window()
        # Qt aborts the process if a running QThread is destroyed at exit, but a stuck
        # check must not hang quitting (and with it logout) forever.
        thread = self._check_thread
        if (
            thread is not None
            and thread.isRunning()
            and not thread.wait(_CHECK_SHUTDOWN_TIMEOUT_MS)
        ):
            get_logger("tray").warning("Update check still running at quit")
        self._persist_state()
        self._resume_stop.set()
        if self._resume_thread.is_alive():
            self._resume_thread.join(timeout=1)
        self._notification_client.shutdown()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger and not self._open_current_run():
            if self._cfg.tray.click_action == "run_topgrade":
                self._run_topgrade()
            else:
                self._show_updates()


def install_termination_handler(app: QApplication) -> None:
    """Quit the Qt event loop on SIGTERM so tray.shutdown() still runs.

    Python only runs signal handlers when the main thread is executing
    bytecode, and app.exec() sits in Qt. The wakeup fd makes the signal
    visible to a QSocketNotifier, which then quits on the GUI thread.
    """
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    os.set_blocking(write_fd, False)
    signal.set_wakeup_fd(write_fd)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: None)
    notifier = QSocketNotifier(read_fd, QSocketNotifier.Type.Read, app)

    def _drain(_socket: int) -> None:
        try:
            data = os.read(read_fd, 64)
        except OSError:
            return
        if signal.SIGTERM in data:
            app.quit()

    notifier.activated.connect(_drain)
    # Keep the notifier and the write end alive for the life of the app.
    app._uptray_sigterm_notifier = notifier  # type: ignore[attr-defined]
    app._uptray_sigterm_write_fd = write_fd  # type: ignore[attr-defined]


def run_tray(cfg: Config | None = None) -> int:
    """Launch the PySide6 system tray applet (single instance)."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        instance_lock = _acquire_instance_lock()
    except OSError as exc:
        print(f"Error: could not create the tray lock: {exc}", file=sys.stderr)
        return 2
    if instance_lock is None:
        print("Error: uptray tray is already running.", file=sys.stderr)
        return 3

    app = QApplication(sys.argv)
    install_termination_handler(app)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)
    apply_app_theme(app)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("Error: No system tray available.", file=sys.stderr)
        return 1

    if cfg is None:
        try:
            cfg = load_config()
        except (OSError, TypeError, ValueError) as exc:
            print(f"Error loading configuration: {exc}", file=sys.stderr)
            send_message(APP_NAME, f"Could not load the configuration: {exc}", urgency="critical")
            return 2
    tray = Tray(cfg)
    try:
        tray.show()
        return int(app.exec())
    finally:
        tray.shutdown()
        instance_lock.close()
