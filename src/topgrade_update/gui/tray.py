"""System tray applet implementation."""

from __future__ import annotations

import signal
import subprocess
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from topgrade_update.core.checkers import check_all, find_terminal, total_updates
from topgrade_update.core.config import load_config
from topgrade_update.core.models import Config
from topgrade_update.core.notifications import send_notification
from topgrade_update.gui.dialog import UpdatesDialog
from topgrade_update.gui.icons import IconCache

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"
APP_ID = "topgrade-update"
_ICON_NAME = "topgrade-update"


class CheckThread(QThread):  # type: ignore[misc]
    """Background thread for non-blocking update checks."""

    result = Signal(list)

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg

    def run(self) -> None:
        results: list[CheckResult] = check_all(self._cfg)
        self.result.emit(results)


def launch_topgrade_in_terminal(cfg: Config | None = None) -> None:
    """Launch topgrade in the user's preferred terminal."""
    term, args = find_terminal(cfg)
    if term is None:
        subprocess.Popen(
            ["notify-send", "-a", APP_NAME, "Error", "No terminal emulator found."]
        )
        return
    subprocess.Popen([term] + args + ["topgrade"])


class Tray(QSystemTrayIcon):  # type: ignore[misc]
    """System tray icon with periodic update checking."""

    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self._cfg = cfg
        self._results: list[CheckResult] = []
        self._prev_total = -1
        self._last_check: datetime | None = None
        self._icon_cache = IconCache()
        self._check_thread: CheckThread | None = None

        self.setIcon(self._icon_cache.idle())
        self.setToolTip(APP_NAME)

        # Context menu
        self._menu = QMenu()
        self._action_status = self._menu.addAction("Idle")
        self._action_status.setEnabled(False)
        self._menu.addSeparator()
        self._menu.addAction("Check Now", self._start_check)
        self._menu.addAction("View Updates", self._show_updates)
        self._menu.addSeparator()
        self._menu.addAction("Run Topgrade", self._run_topgrade)
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

        if total > 0:
            self.setIcon(self._icon_cache.updates(total))
            self.setToolTip(f"{APP_NAME} — {total} update(s) available")
            self._action_status.setText(f"{total} update(s) available")
            if total != self._prev_total:
                send_notification(results)
        else:
            self.setIcon(self._icon_cache.uptodate())
            self.setToolTip(f"{APP_NAME} — System is up to date")
            self._action_status.setText("System is up to date")

        self._prev_total = total

    def _show_updates(self) -> None:
        if not self._results or total_updates(self._results) == 0:
            subprocess.Popen(
                [
                    "notify-send",
                    "-a",
                    APP_NAME,
                    "-i",
                    _ICON_NAME,
                    "No updates",
                    "Your system is up to date.",
                ]
            )
            return
        dlg = UpdatesDialog(self._results)
        dlg.set_on_run(self._run_topgrade)
        dlg.exec()

    def _run_topgrade(self) -> None:
        launch_topgrade_in_terminal(self._cfg)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if total_updates(self._results) > 0:
                self._show_updates()
            else:
                self._run_topgrade()


def run_tray() -> int:
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

    cfg = load_config()
    tray = Tray(cfg)
    tray.show()
    return int(app.exec())
