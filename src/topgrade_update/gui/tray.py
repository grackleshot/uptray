"""System tray applet implementation."""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
from datetime import datetime, timedelta

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from topgrade_update.core.checkers import check_all, find_terminal, total_updates
from topgrade_update.core.config import load_config
from topgrade_update.core.logging import get_logger
from topgrade_update.core.models import CheckResult, Config
from topgrade_update.core.notification_engine import DeferredNotification, NotificationEngine
from topgrade_update.core.notifications import NotificationClient, send_message, send_notification
from topgrade_update.core.quiet_hours import is_quiet_hours
from topgrade_update.gui.dialog import UpdatesDialog
from topgrade_update.gui.icons import IconCache
from topgrade_update.gui.tray_logic import is_snoozed, snooze_label

APP_NAME = "Topgrade Update"
APP_ID = "topgrade-update"
_ICON_NAME = "topgrade-update"


class CheckThread(QThread):
    """Background thread for non-blocking update checks."""

    result = Signal(list)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg

    def run(self) -> None:
        try:
            results = check_all(self._cfg)
        except Exception as exc:
            results = [CheckResult(source="update check", error=str(exc))]
        self.result.emit(results)


def launch_topgrade_in_terminal(cfg: Config | None = None) -> None:
    """Launch topgrade in the user's preferred terminal."""
    topgrade = shutil.which("topgrade")
    if topgrade is None:
        send_message("Topgrade not found", "Install topgrade before trying to run it.")
        return
    term, args = find_terminal(cfg)
    if term is None:
        send_message("Error", "No terminal emulator found.")
        return
    try:
        subprocess.Popen([term] + args + [topgrade])
    except OSError as exc:
        get_logger("tray").exception("Could not launch topgrade terminal")
        send_message("Could not launch Topgrade", str(exc))


class Tray(QSystemTrayIcon):
    """System tray icon with periodic update checking."""

    notification_action = Signal(str)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self._results: list[CheckResult] = []
        self._last_check: datetime | None = None
        self._snooze_until: datetime | None = None
        self._notification_engine = NotificationEngine()
        self._notification_client = NotificationClient()
        self.notification_action.connect(self._on_notification_action)
        self._notification_client.start_action_listener(self.notification_action.emit)
        self._icon_cache = IconCache()
        self._check_thread: CheckThread | None = None
        self._snooze_timer = QTimer()
        self._snooze_timer.setSingleShot(True)
        self._snooze_timer.timeout.connect(self._on_snooze_expired)

        self.setIcon(self._icon_cache.idle())
        self.setToolTip(APP_NAME)

        # Context menu
        self._menu = QMenu()
        self._action_status = self._menu.addAction("Idle")
        self._action_status.setEnabled(False)
        self._menu.addSeparator()
        self._menu.addAction("Check Now", self._check_now)
        self._menu.addAction("View Updates", self._show_updates)
        self._menu.addSeparator()
        self._menu.addAction("Run Topgrade", self._run_topgrade)
        self._menu.addSeparator()
        snooze_menu = self._menu.addMenu("Snooze")
        snooze_menu.addAction("Snooze 1 hour", lambda: self._snooze(1))
        snooze_menu.addAction(
            f"Snooze {cfg.tray.snooze_hours} hours",
            lambda: self._snooze(cfg.tray.snooze_hours),
        )
        snooze_menu.addAction("Snooze until tomorrow", lambda: self._snooze(24))
        snooze_menu.addAction("Cancel snooze", lambda: self._snooze(None))
        self._menu.addSeparator()
        self._menu.addAction("Quit", QApplication.quit)
        self.setContextMenu(self._menu)

        self.activated.connect(self._on_activated)

        # Periodic check timer
        self._timer = QTimer()
        self._timer.timeout.connect(self._start_check)
        self._timer.start(cfg.check_interval * 1000)

        # Initial check after 3 seconds
        QTimer.singleShot(3000, self._start_check)

    def _start_check(self) -> None:
        if self._is_snoozed():
            if self._snooze_until is not None:
                self._action_status.setText(snooze_label(self._snooze_until))
            self._update_tooltip()
            return
        if self._check_thread is not None and self._check_thread.isRunning():
            return
        self.setIcon(self._icon_cache.checking())
        self.setToolTip(f"{APP_NAME} — Checking for updates…")
        self._action_status.setText("Checking…")
        self._check_thread = CheckThread(self._cfg)
        self._check_thread.result.connect(self._on_check_done)
        self._check_thread.start()

    def _on_check_done(self, results: list[CheckResult]) -> None:
        self._results = results
        self._last_check = datetime.now()
        total = total_updates(results)
        snoozed = self._is_snoozed()
        notify = (
            self._cfg.notifications.enabled
            and not snoozed
            and self._notification_engine.should_notify(results)
        )
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

        if total > 0:
            self.setIcon(self._icon_cache.updates(total))
            self._update_status_action()
            if (
                not snoozed
                and notify
                and not self._notification_engine.maybe_defer(results)
            ):
                self._send_update_notification(results)
        else:
            if not results or any(result.error is not None for result in results):
                self.setIcon(self._icon_cache.idle())
            else:
                self.setIcon(self._icon_cache.uptodate())
            self._update_status_action()

        self._update_tooltip()

    def _update_tooltip(self) -> None:
        lines = [APP_NAME]
        if self._last_check:
            lines.append(f"Last check: {self._last_check.strftime('%H:%M')}")
        if self._is_snoozed() and self._snooze_until is not None:
            lines.append(snooze_label(self._snooze_until))
        total = total_updates(self._results)
        failed_sources = sum(result.error is not None for result in self._results)
        if total > 0:
            lines.append(f"{total} update(s) available")
            if failed_sources:
                lines.append(f"{failed_sources} source check(s) failed")
        elif any(result.error is not None for result in self._results):
            lines.append("Update check failed")
        elif not self._results:
            lines.append("No update checkers available")
        else:
            lines.append("System is up to date")
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
        total = total_updates(self._results)
        failed_sources = sum(result.error is not None for result in self._results)
        if total > 0:
            status = f"{total} update(s) available"
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
        self._update_status_action()
        self._update_tooltip()
        if hours is None:
            self._start_check()

    def _check_now(self) -> None:
        if self._is_snoozed():
            self._snooze_until = None
            self._snooze_timer.stop()
            self._notification_engine.reset_deduplication()
        self._start_check()

    def _on_snooze_expired(self) -> None:
        self._snooze_until = None
        self._notification_engine.reset_deduplication()
        self._start_check()

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
        dlg.exec()

    def _run_topgrade(self) -> None:
        launch_topgrade_in_terminal(self._cfg)

    def shutdown(self) -> None:
        """Release the notification DBus connection and action listener."""
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
    """Launch the PySide6 system tray applet."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName(APP_ID)
    app.setQuitOnLastWindowClosed(False)

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
