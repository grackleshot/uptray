"""System tray applet implementation."""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import signal
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from PySide6.QtCore import QFileSystemWatcher, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from topgrade_update.core.arch_news import NewsItem, fetch_news, new_items, newest_marker
from topgrade_update.core.checkers import check_all, find_terminal, total_updates
from topgrade_update.core.config import load_config, save_config
from topgrade_update.core.history import parse_pacman_log
from topgrade_update.core.links import upstream_url
from topgrade_update.core.logging import get_logger
from topgrade_update.core.maintenance import maintenance_summary
from topgrade_update.core.models import CheckResult, Config
from topgrade_update.core.network import is_online
from topgrade_update.core.notification_engine import DeferredNotification, NotificationEngine
from topgrade_update.core.notifications import NotificationClient, send_message, send_notification
from topgrade_update.core.quiet_hours import is_quiet_hours
from topgrade_update.core.state import (
    AppState,
    format_snooze,
    load_state,
    parse_snooze,
    save_state,
)
from topgrade_update.gui.dialog import (
    HistoryDialog,
    MaintenanceDialog,
    UpdatesDialog,
    open_url,
)
from topgrade_update.gui.icons import IconCache
from topgrade_update.gui.run_window import RunWindow
from topgrade_update.gui.settings import SettingsDialog
from topgrade_update.gui.style import apply_app_theme, apply_theme
from topgrade_update.gui.tray_logic import (
    OFFLINE_RETRY_MS,
    PACMAN_DEBOUNCE_MS,
    PACMAN_LOCAL_DB_DIR,
    RESUME_CHECK_DELAY_MS,
    is_reboot_pending,
    is_snoozed,
    pacman_watch_dir,
    remaining_ms,
    snooze_label,
)

APP_NAME = "Topgrade Update"
APP_ID = "topgrade-update"
_ICON_NAME = "topgrade-update"
_MAX_MENU_PACKAGES = 15
_MAX_NEWS_ITEMS = 8


class CheckThread(QThread):
    """Background thread for non-blocking update checks and news fetches."""

    result = Signal(list, object)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg

    def run(self) -> None:
        try:
            results = check_all(self._cfg)
        except Exception as exc:
            results = [CheckResult(source="update check", error=str(exc))]
        news: list[NewsItem] | None = None
        try:
            news = fetch_news(timeout=10.0)
        except Exception as exc:
            get_logger("tray").debug("Arch news fetch skipped: %s", exc)
        self.result.emit(results, news)


def _watch_resume(emit: Callable[[], None], stop: Event) -> None:
    """Watch logind PrepareForSleep on the system bus and emit on wake.

    Runs in a daemon thread; failures are non-fatal (no resume detection).
    """
    try:
        from jeepney import MatchRule
        from jeepney.bus_messages import message_bus
        from jeepney.io.blocking import open_dbus_connection

        bus = open_dbus_connection(bus="SYSTEM")
    except Exception:
        return
    rule = MatchRule(
        type="signal",
        sender="org.freedesktop.login1",
        interface="org.freedesktop.login1.Manager",
        member="PrepareForSleep",
        path="/org/freedesktop/login1",
    )
    try:
        bus.send_and_get_reply(message_bus.AddMatch(rule), timeout=3)
        with bus.filter(rule) as matches:
            while not stop.is_set():
                try:
                    message = bus.recv_until_filtered(matches, timeout=0.25)
                except TimeoutError:
                    continue
                body = getattr(message, "body", ())
                if body and body[0] is False:  # False = resuming
                    emit()
    except Exception as exc:
        get_logger("tray").debug("Resume watcher stopped: %s", exc)
    finally:
        with contextlib.suppress(Exception):
            bus.close()


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


def _acquire_instance_lock() -> IO[str] | None:
    """Take an exclusive single-instance lock, or None when already held."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        lock_path = Path(runtime) / "topgrade-update.lock"
    else:
        lock_path = Path(f"/tmp/topgrade-update-{os.getuid()}.lock")
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("w")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    handle.truncate(0)
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    return handle


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

        # Persistent state: restore snooze and notification dedup count.
        self._state: AppState = load_state(state_path)
        restored_snooze = parse_snooze(self._state.snooze_until)
        if restored_snooze is not None and restored_snooze > datetime.now():
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
        if package_total > 0:
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
        snooze_menu.addAction("Snooze until tomorrow", lambda: self._snooze(24))
        snooze_menu.addAction("Cancel snooze", lambda: self._snooze(None))
        self._menu.addSeparator()
        self._add_action("Quit", "application-exit", self._quit)

    def _add_action(self, label: str, icon_name: str, slot: Callable[[], None]) -> QAction:
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
        counts = self._updates_by_source()
        return sum(counts.values()) - counts.get("reboot", 0)

    # ------------------------------------------------------------------
    # Check lifecycle

    def _start_check(self) -> None:
        if self._is_snoozed():
            if self._snooze_until is not None:
                self._action_status.setText(snooze_label(self._snooze_until))
            self._update_tooltip()
            return
        if not is_online():
            self._action_status.setText("Offline — waiting for network")
            self._update_tooltip()
            if not self._offline_retry.isActive():
                self._offline_retry.start(OFFLINE_RETRY_MS)
            return
        self._offline_retry.stop()
        if self._check_thread is not None and self._check_thread.isRunning():
            return
        self.setIcon(self._icon_cache.checking())
        self.setToolTip(f"{APP_NAME} — Checking for updates…")
        self._action_status.setText("Checking…")
        self._check_thread = CheckThread(self._cfg)
        self._check_thread.result.connect(self._on_check_done)
        self._check_thread.start()

    def _on_check_done(self, results: list[CheckResult], news: object = None) -> None:
        previous_package_total = self._package_total()
        self._results = results
        self._last_check = datetime.now()
        counts = {result.source: len(result.updates) for result in results}
        package_total = sum(counts.values()) - counts.get("reboot", 0)
        snoozed = self._is_snoozed()
        # Always advance dedup state so restarts/disabled periods don't re-notify.
        changed = self._notification_engine.should_notify(results)
        notify = self._cfg.notifications.enabled and not snoozed and changed

        if isinstance(news, list):
            self._news_items = [item for item in news if isinstance(item, NewsItem)]
            self._news_new_count = len(new_items(self._news_items, self._state.last_seen_news))

        quiet = is_quiet_hours(
            self._cfg.notifications.quiet_hours_start,
            self._cfg.notifications.quiet_hours_end,
        )

        if quiet:
            self._notification_engine.enter_quiet_hours()
        else:
            deferred = self._notification_engine.exit_quiet_hours()
            if deferred and self._cfg.notifications.enabled and not snoozed:
                self._send_deferred_notifications(deferred)

        reboot_pending = is_reboot_pending(counts)
        self._handle_reboot_notification(reboot_pending, snoozed=snoozed, quiet=quiet)

        self._refresh_icon(package_total, reboot_pending, results)
        if (
            package_total > 0
            and not snoozed
            and notify
            and not self._notification_engine.maybe_defer(results)
        ):
            self._send_update_notification(results)

        self._maybe_maintenance_reminder(previous_package_total, package_total, results)

        self._persist_state()
        self._build_menu()
        self._update_status_action()
        self._update_tooltip()

    def _refresh_icon(
        self,
        total: int,
        reboot_pending: bool,
        results: list[CheckResult],
    ) -> None:
        if total > 0:
            self.setIcon(self._icon_cache.updates(total))
        elif reboot_pending:
            self.setIcon(self._icon_cache.reboot())
        elif not results or any(result.error is not None for result in results):
            self.setIcon(self._icon_cache.idle())
        else:
            self.setIcon(self._icon_cache.uptodate())

    # ------------------------------------------------------------------
    # Reboot / maintenance / news

    def _handle_reboot_notification(
        self, reboot_pending: bool, *, snoozed: bool, quiet: bool
    ) -> None:
        if (
            reboot_pending
            and not self._state.reboot_notified
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
        if reboot_pending != self._state.reboot_notified:
            self._state.reboot_notified = reboot_pending

    def _maybe_maintenance_reminder(
        self,
        previous_total: int,
        total: int,
        results: list[CheckResult],
    ) -> None:
        """After an update session ends (N -> 0), remind once per day."""
        if previous_total <= 0 or total != 0 or not results:
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
        self._update_tooltip()
        self._build_menu()

    # ------------------------------------------------------------------
    # Status surfaces

    def _update_tooltip(self) -> None:
        lines = [APP_NAME]
        if self._last_check:
            lines.append(f"Last check: {self._last_check.strftime('%H:%M')}")
        if self._is_snoozed() and self._snooze_until is not None:
            lines.append(snooze_label(self._snooze_until))
        package_total = self._package_total()
        reboot_pending = is_reboot_pending(self._updates_by_source())
        failed_sources = sum(result.error is not None for result in self._results)
        if package_total > 0:
            lines.append(f"{package_total} update(s) available")
            if failed_sources:
                lines.append(f"{failed_sources} source check(s) failed")
        elif any(result.error is not None for result in self._results):
            lines.append("Update check failed")
        elif not self._results:
            lines.append("No update checkers available")
        else:
            lines.append("System is up to date")
        if reboot_pending:
            lines.append("Reboot required")
        if self._news_new_count:
            lines.append(f"{self._news_new_count} new Arch news item(s)")
        self.setToolTip("\n".join(lines))

    def _send_deferred_notifications(self, deferred: list[DeferredNotification]) -> None:
        latest_results = deferred[-1]["results"]
        total = total_updates(latest_results)
        if total == 0:
            return
        source_counts = {
            result.source: len(result.updates)
            for result in latest_results
            if result.updates
        }
        body = "\n".join(f"  {source}: {count}" for source, count in source_counts.items())
        self._send_update_notification(
            latest_results,
            summary="Updates available after quiet hours",
            body=f"{total} update(s) currently available\n{body}",
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
        if self._is_snoozed() and self._snooze_until is not None:
            self._action_status.setText(snooze_label(self._snooze_until))
            return
        package_total = self._package_total()
        failed_sources = sum(result.error is not None for result in self._results)
        if package_total > 0:
            status = f"{package_total} update(s) available"
            if failed_sources:
                status += f"; {failed_sources} source(s) failed"
        elif any(result.error is not None for result in self._results):
            status = "Update check failed"
        elif not self._results:
            status = "No update checkers available"
        else:
            status = "System is up to date"
        if self._last_check:
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
            self._snooze_until = None
            self._snooze_timer.stop()
            self._notification_engine.reset_deduplication()
        else:
            self._snooze_until = datetime.now() + timedelta(hours=hours)
            self._snooze_timer.start(hours * 60 * 60 * 1000)
        self._persist_state()
        self._update_status_action()
        self._update_tooltip()
        if hours is None:
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
        if not self._is_snoozed():
            self._start_check()

    def _on_resume_detected(self) -> None:
        """Re-check shortly after the system resumes from suspend."""
        QTimer.singleShot(RESUME_CHECK_DELAY_MS, self._start_check)

    # ------------------------------------------------------------------
    # Windows and actions

    def _show_updates(self) -> None:
        if not self._results or total_updates(self._results) == 0:
            if not self._results:
                send_message("No update checkers", "No supported update source is available.")
            elif any(result.error is not None for result in self._results):
                send_message(
                    "Update check failed",
                    "One or more update sources could not be checked.",
                )
            else:
                send_message("No updates", "Your system is up to date.")
            return
        dlg = UpdatesDialog(self._results)
        dlg.set_on_run(self._run_topgrade)
        dlg.set_on_preview(self._preview_topgrade)
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
        try:
            save_config(cfg)
        except OSError as exc:
            get_logger("tray").warning("Could not save configuration: %s", exc)
        self._timer.setInterval(cfg.check_interval * 1000)
        if not self._timer.isActive():
            self._timer.start()
        if cfg.tray.icon_style != self._icon_cache.style:
            self._icon_cache = IconCache(cfg.tray.icon_style)
        self._refresh_icon(
            self._package_total(), is_reboot_pending(self._updates_by_source()), self._results
        )
        self._build_menu()
        self._update_status_action()
        self._update_tooltip()

    def _run_topgrade(self, extra_args: list[str] | None = None) -> None:
        self._open_run_window(list(extra_args or []))

    def _preview_topgrade(self) -> None:
        self._open_run_window(["--dry-run"], title="Topgrade Update — Dry Run")

    def _run_topgrade_terminal(self) -> None:
        launch_topgrade_in_terminal(self._cfg)

    def _open_run_window(
        self,
        extra_args: list[str] | None = None,
        *,
        title: str | None = None,
    ) -> None:
        # Keep a strong reference so the non-modal window is not garbage-collected.
        # Reuse only while a session is still running; finished windows must not
        # block a new dry-run/update request.
        existing = getattr(self, "_run_window", None)
        if existing is not None and existing.is_active:
            # A running window may be hidden (closed mid-run); bring it back.
            existing.showNormal()
            existing.raise_()
            existing.activateWindow()
            return
        if existing is not None:
            existing.close()
        window = RunWindow(
            self._cfg,
            extra_args=extra_args,
            title=title,
            on_finished=lambda _code: QTimer.singleShot(500, self._start_check),
        )
        self._run_window = window
        window.show()

    def _stop_run_window(self) -> None:
        window = getattr(self, "_run_window", None)
        if window is not None:
            window.shutdown()

    def _quit(self) -> None:
        # Qt 6 aborts quit() when a window ignores its close event, and a
        # running RunWindow does; stop it explicitly first.
        self._stop_run_window()
        QApplication.quit()

    def shutdown(self) -> None:
        """Release background threads and the notification DBus connection."""
        self._stop_run_window()
        self._persist_state()
        self._resume_stop.set()
        if self._resume_thread.is_alive():
            self._resume_thread.join(timeout=1)
        self._notification_client.shutdown()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self._cfg.tray.click_action == "show_updates":
                self._show_updates()
            elif self._cfg.tray.click_action == "run_topgrade":
                self._run_topgrade()
            elif total_updates(self._results) > 0:
                self._show_updates()
            else:
                self._run_topgrade()


def run_tray(cfg: Config | None = None) -> int:
    """Launch the PySide6 system tray applet (single instance)."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    instance_lock = _acquire_instance_lock()
    if instance_lock is None:
        print("Error: topgrade-update tray is already running.", file=sys.stderr)
        return 3

    app = QApplication(sys.argv)
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
            return 2
    tray = Tray(cfg)
    try:
        tray.show()
        return int(app.exec())
    finally:
        tray.shutdown()
        instance_lock.close()
