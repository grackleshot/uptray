"""Tests for the system tray applet."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from uptray.core.models import CheckResult, Config, NotificationConfig, TrayConfig, Update

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytestqt.qtbot import QtBot

pytest.importorskip("PySide6")

from uptray.gui.tray import APP_NAME, CheckThread, Tray  # noqa: E402


@pytest.fixture
def mock_cfg() -> Config:
    """Build a small configuration for tray tests."""
    return Config(
        tray=TrayConfig(click_action="show_updates", snooze_hours=1),
        notifications=NotificationConfig(enabled=True),
    )


@pytest.fixture
def tray(mock_cfg: Config, qapp, tmp_path) -> Tray:  # noqa: ANN001
    """Tray isolated from the real pacman dir and user state file."""
    return Tray(
        mock_cfg,
        pacman_db_dir=tmp_path / "no-pacman",
        debounce_ms=50,
        state_path=tmp_path / "state.json",
    )


def test_tray_initialization(tray: Tray) -> None:
    """Build real Qt tray objects and expose the expected menu actions."""
    assert tray.toolTip() == APP_NAME
    assert tray.contextMenu() is not None
    action_labels = [action.text() for action in tray.contextMenu().actions()]
    assert "Idle" in action_labels
    assert "Check Now" in action_labels
    assert "View Updates" in action_labels
    assert "Run Topgrade" in action_labels
    assert "Run in Terminal" in action_labels
    assert "Quit" in action_labels


def test_snooze_logic_updates_status_and_timer(tray: Tray) -> None:
    """Snoozing records a target time, updates the menu, and arms its timer."""
    started = datetime.now().astimezone()

    tray._snooze(2)

    assert tray._snooze_until is not None
    assert started + timedelta(hours=2) <= tray._snooze_until
    assert abs((tray._snooze_until - datetime.now().astimezone()).total_seconds() - 7200) < 1
    assert tray._action_status.text().startswith("Snoozed until ")
    assert tray._snooze_timer.isActive()
    assert tray._snooze_timer.interval() == 7_200_000


def test_snooze_persists_and_restores(mock_cfg: Config, qapp, tmp_path) -> None:  # noqa: ANN001
    """Snooze and dedup state survive tray restarts via the state file."""
    state_path = tmp_path / "state.json"
    first = Tray(mock_cfg, pacman_db_dir=tmp_path / "db", state_path=state_path)
    first._notification_engine.prev_total = 5
    first._snooze(3)
    snooze_target = first._snooze_until

    second = Tray(mock_cfg, pacman_db_dir=tmp_path / "db", state_path=state_path)

    assert second._snooze_until == snooze_target
    assert second._snooze_timer.isActive()
    assert second._notification_engine.prev_total == 5


def test_is_snoozed_clears_expired_target(tray: Tray) -> None:
    """The tray recognizes active snoozes and clears expired targets."""
    assert tray._is_snoozed() is False
    tray._snooze(1)
    assert tray._is_snoozed() is True

    tray._snooze_until = datetime.now().astimezone() - timedelta(seconds=1)
    assert tray._is_snoozed() is False
    assert tray._snooze_until is None


def test_partial_check_failure_is_visible_in_status_and_tooltip(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tray reports source failures even when another source found updates."""
    sent_notifications: list[dict[str, object]] = []

    def capture_notification(_results: list[CheckResult], **kwargs: object) -> None:
        sent_notifications.append(kwargs)

    monkeypatch.setattr("uptray.gui.tray.send_notification", capture_notification)
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    results = [
        CheckResult(
            source="pacman",
            updates=[Update("package", "1", "2", "pacman")],
        ),
        CheckResult(source="flatpak", error="remote unavailable"),
    ]

    tray._on_check_done(results)

    assert tray._action_status.text().startswith("1 update(s) available; 1 source(s) failed")
    assert "1 source check(s) failed" in tray.toolTip()
    assert [label for _, label in sent_notifications[0]["actions"]] == [
        "Run Topgrade",
        "Snooze",
        "Dismiss",
    ]


def test_notification_actions_dispatch_to_tray_commands(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setattr(tray, "_run_topgrade", lambda: called.append("run"))
    monkeypatch.setattr(tray, "_snooze", lambda hours: called.append(f"snooze:{hours}"))

    tray._on_notification_action("run_topgrade")
    tray._on_notification_action("snooze")
    tray._on_notification_action("dismiss")

    assert called == ["run", "snooze:1"]


def test_reboot_sends_critical_notification_once(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str, str]] = []

    def capture_message(summary: str, body: str, **kwargs: object) -> None:
        urgency = str(kwargs.get("urgency"))
        messages.append((summary, body, urgency))

    monkeypatch.setattr("uptray.gui.tray.send_message", capture_message)
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    reboot_result = CheckResult(
        source="reboot",
        updates=[Update("kernel", "6.6", "reboot required", "reboot")],
    )

    tray._on_check_done([reboot_result])
    tray._on_check_done([reboot_result])

    assert len(messages) == 1
    assert messages[0][0] == "Reboot required"
    assert messages[0][2] == "critical"
    # Icon reflects the reboot state with no package updates
    # (QImage cache keys are content-based).
    shown = tray.icon().pixmap(64, 64).toImage().cacheKey()
    expected = tray._icon_cache.reboot().pixmap(64, 64).toImage().cacheKey()
    assert shown == expected
    assert "No package sources checked" in tray._action_status.text()
    assert "No package sources checked" in tray.toolTip()
    assert "Reboot required" in tray._action_status.text()
    assert "Reboot required" in tray.toolTip()


def test_reboot_check_without_packages_keeps_idle_icon(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[str] = []
    monkeypatch.setattr("uptray.gui.tray.send_message", lambda title, *_a: messages.append(title))

    tray._on_check_done([CheckResult(source="reboot")])
    tray._show_updates()

    assert messages == ["No package sources checked"]
    assert "No package sources checked" in tray.toolTip()
    assert "System is up to date" not in tray.toolTip()
    assert tray.icon().cacheKey() == tray._icon_cache.idle().cacheKey()


def test_reboot_flag_resets_when_no_longer_pending(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("uptray.gui.tray.send_message", lambda *a, **k: None)
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    reboot_result = CheckResult(
        source="reboot",
        updates=[Update("kernel", "6.6", "reboot required", "reboot")],
    )
    ok_result = CheckResult(source="pacman", updates=[])

    tray._on_check_done([reboot_result])
    assert tray._state.reboot_notified is True

    tray._on_check_done([ok_result])
    assert tray._state.reboot_notified is False


def test_maintenance_reminder_fires_after_updates_clear(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str]] = []

    def capture_message(summary: str, body: str, **_kwargs: object) -> None:
        messages.append((summary, body))

    monkeypatch.setattr("uptray.gui.tray.send_message", capture_message)

    from uptray.core.maintenance import MaintenanceFinding

    def fake_summary(**_kwargs: object) -> list[MaintenanceFinding]:
        return [MaintenanceFinding("orphans", "2 orphan package(s)", ["a", "b"])]

    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", fake_summary)

    with_updates = CheckResult(source="pacman", updates=[Update("pkg", "1", "2", "pacman")])
    done = CheckResult(source="pacman", updates=[])
    tray._on_check_done([with_updates])
    tray._on_check_done([done])

    assert len(messages) == 1
    assert messages[0][0] == "Post-update maintenance"
    assert "orphan" in messages[0][1]

    # Once per day: another cycle does not re-notify.
    tray._on_check_done([with_updates])
    tray._on_check_done([done])
    assert len(messages) == 1


@pytest.mark.parametrize("restriction", ["disabled", "quiet hours", "snoozed"])
def test_automatic_maintenance_respects_notifications(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    restriction: str,
) -> None:
    messages: list[str] = []
    maintenance_checks: list[int] = []
    monkeypatch.setattr("uptray.gui.tray.send_message", lambda title, *_a: messages.append(title))
    monkeypatch.setattr("uptray.gui.tray.send_notification", lambda *_a, **_kw: None)
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: maintenance_checks.append(1))
    monkeypatch.setattr("uptray.gui.tray.is_quiet_hours", lambda *_a: restriction == "quiet hours")
    if restriction == "disabled":
        tray._cfg.notifications.enabled = False
    if restriction == "snoozed":
        tray._snooze(1)

    tray._on_check_done([CheckResult("pacman", [Update("pkg", "1", "2", "pacman")])])
    tray._on_check_done([CheckResult("pacman")])

    assert maintenance_checks == []
    assert messages == []
    assert tray._state.maintenance_check_date is None


@pytest.mark.parametrize("current_total", [0, 2])
def test_deferred_alert_uses_current_results(
    tray: Tray, monkeypatch: pytest.MonkeyPatch, current_total: int
) -> None:
    quiet = True
    notifications: list[tuple[list[CheckResult], str]] = []

    def capture(results: list[CheckResult], *, body: str = "", **_kw: object) -> None:
        notifications.append((results, body))

    monkeypatch.setattr("uptray.gui.tray.is_quiet_hours", lambda *_a: quiet)
    monkeypatch.setattr("uptray.gui.tray.send_notification", capture)
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    tray._on_check_done([CheckResult("pacman", [Update("old", "1", "2", "pacman")])])
    assert notifications == []

    quiet = False
    updates = [Update(f"pkg-{i}", "1", "2", "flatpak") for i in range(current_total)]
    results = [CheckResult("flatpak", updates)]
    tray._on_check_done(results)

    if current_total:
        assert notifications == [(results, "2 update(s) currently available\n  flatpak: 2")]
    else:
        assert notifications == []
        assert "System is up to date" in tray.toolTip()


def test_news_menu_and_mark_read(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from uptray.core.arch_news import NewsItem

    opened: list[str] = []
    monkeypatch.setattr("uptray.gui.tray.open_url", lambda url: opened.append(url))

    fresh = NewsItem(
        "Fresh news", "https://archlinux.org/news/fresh/", datetime.now() + timedelta(hours=1)
    )
    stale = NewsItem(
        "Old news", "https://archlinux.org/news/old/", datetime.now() - timedelta(days=30)
    )

    # First run with no marker: nothing is new.
    tray._on_check_done([], news=[fresh, stale])
    assert tray._news_new_count == 0

    # Mark read, then publish something newer: one new item.
    tray._news_items = [fresh, stale]
    tray._mark_news_read()
    newer = NewsItem(
        "Newer news", "https://archlinux.org/news/newer/", datetime.now() + timedelta(hours=2)
    )
    tray._on_check_done([], news=[newer, fresh, stale])

    assert tray._news_new_count == 1
    menu_labels = [action.text() for action in tray.contextMenu().actions()]
    assert "Arch News (1 new)" in menu_labels


def test_pacman_db_change_triggers_debounced_check(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    qapp,  # noqa: ANN001
) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    checks: list[int] = []
    monkeypatch.setattr(tray, "_start_check", lambda **_kw: checks.append(1))

    # Simulate the directoryChanged signal firing in bursts.
    tray._on_db_changed_signal("/var/lib/pacman/local")
    tray._on_db_changed_signal("/var/lib/pacman/local")

    loop = QEventLoop()
    QTimer.singleShot(150, loop.quit)
    loop.exec()

    assert checks == [1]  # debounced to a single check


def test_offline_check_defers_and_retries(
    mock_cfg: Config,
    qapp,  # noqa: ANN001
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray = Tray(
        mock_cfg,
        pacman_db_dir=tmp_path / "no-pacman",
        state_path=tmp_path / "state.json",
        debounce_ms=10,
    )
    monkeypatch.setattr("uptray.gui.tray.is_online", lambda: False)

    tray._start_check()

    assert tray._action_status.text() == "Offline — waiting for network"
    assert tray._offline_retry.isActive()


def test_open_run_window_starts_new_run_after_finished(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class FakeWindow:
        def shutdown(self) -> None: ...

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.is_active = False
            self.monitor_status_changed = type("S", (), {"connect": lambda *_a: None})()
            self.closed = type("S", (), {"connect": lambda *_a: None})()
            created.append(self)

        def isVisible(self) -> bool:  # noqa: N802
            return True

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:  # noqa: N802
            return None

        def close(self) -> None:
            return None

        def deleteLater(self) -> None:  # noqa: N802
            return None

        def show(self) -> None:
            return None

    monkeypatch.setattr("uptray.gui.tray.RunWindow", FakeWindow)
    tray._run_window = FakeWindow()
    tray._open_run_window([])
    assert len(created) == 2


def _use_real_run_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make the tray open real run windows that run a short script instead of topgrade."""
    from uptray.gui.run_window import RunWindow

    script = tmp_path / "done.sh"
    script.write_text("#!/bin/sh\necho done\n", encoding="utf-8")
    monkeypatch.setattr(
        "uptray.gui.tray.RunWindow",
        lambda cfg, **kw: RunWindow(
            cfg, command=["/bin/sh", str(script)], runs_dir=tmp_path / "runs", **kw
        ),
    )
    monkeypatch.setattr("uptray.gui.tray.is_online", lambda: False)


def _destroyed_count(*objects: object) -> list[bool]:
    destroyed: list[bool] = []
    for obj in objects:
        obj.destroyed.connect(lambda *_: destroyed.append(True))  # type: ignore[attr-defined]
    return destroyed


def _flush_deletes() -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_replaced_run_window_is_destroyed_with_its_web_views(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    """Qt holds lambdas that capture the window; each leaked one kept two renderers."""
    from uptray.gui.terminal_widget import webengine_available

    _use_real_run_windows(monkeypatch, tmp_path)
    tray._open_run_window([])
    first = tray._run_window
    assert first is not None
    qtbot.waitUntil(lambda: not first.is_active, timeout=5000)
    views: list[object] = []
    if webengine_available():
        from PySide6.QtWebEngineWidgets import QWebEngineView

        views = list(first.findChildren(QWebEngineView))
        assert views
    destroyed = _destroyed_count(first, *views)

    tray._open_run_window([])
    _flush_deletes()

    assert tray._run_window is not first
    assert len(destroyed) == 1 + len(views)


def test_closing_a_finished_run_window_frees_it_without_another_run(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    _use_real_run_windows(monkeypatch, tmp_path)
    tray._open_run_window([])
    window = tray._run_window
    assert window is not None
    qtbot.waitUntil(lambda: not window.is_active, timeout=5000)
    destroyed = _destroyed_count(window)

    window.close()
    _flush_deletes()

    assert destroyed
    assert tray._run_window is None


def test_run_for_real_replaces_the_preview_from_its_own_button(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    qtbot,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    """The preview's own click handler starts the run that deletes the preview."""
    _use_real_run_windows(monkeypatch, tmp_path)
    tray._preview_topgrade()
    preview = tray._run_window
    assert preview is not None
    qtbot.waitUntil(lambda: preview._btn_run_real.isVisible(), timeout=5000)
    destroyed = _destroyed_count(preview)

    preview._btn_run_real.click()
    _flush_deletes()

    run = tray._run_window
    assert destroyed
    assert run is not None and run is not preview
    assert run._scope == "Full update"
    qtbot.waitUntil(lambda: not run.is_active, timeout=5000)
    assert run._returncode == 0


@pytest.mark.parametrize("apply_fails", [False, True])
def test_closed_settings_dialog_is_destroyed(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    apply_fails: bool,
) -> None:
    import gc

    from PySide6.QtWidgets import QDialog

    from uptray.gui.settings import SettingsDialog

    destroyed: list[bool] = []

    def exec_and_watch(dialog: SettingsDialog) -> int:
        dialog.destroyed.connect(lambda *_: destroyed.append(True))
        return QDialog.DialogCode.Accepted.value

    def fail(_cfg: object) -> None:
        raise RuntimeError("could not save")

    monkeypatch.setattr(SettingsDialog, "exec", exec_and_watch)
    monkeypatch.setattr("uptray.gui.tray.save_config", lambda _cfg: None)
    if apply_fails:
        monkeypatch.setattr(tray, "_apply_config", fail)
        with pytest.raises(RuntimeError):
            tray._open_settings()
    else:
        tray._open_settings()
    gc.collect()
    _flush_deletes()

    assert destroyed


def test_open_run_window_reshows_hidden_running_window(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class FakeWindow:
        def shutdown(self) -> None: ...

        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.is_active = True
            self.reshown = False
            created.append(self)

        def showNormal(self) -> None:  # noqa: N802
            self.reshown = True

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:  # noqa: N802
            return None

        def focus_pending_input(self) -> None:
            return None

    monkeypatch.setattr("uptray.gui.tray.RunWindow", FakeWindow)
    monkeypatch.setattr("uptray.gui.tray.QMessageBox.information", lambda *_a, **_k: None)
    tray._run_window = FakeWindow()

    tray._open_run_window([])

    assert len(created) == 1
    assert created[0].reshown  # type: ignore[attr-defined]


def test_active_run_is_visible_and_all_launch_actions_refocus_it(
    tray: Tray, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QSystemTrayIcon

    calls: list[str] = []

    class FakeWindow(QObject):
        def shutdown(self) -> None: ...

        monitor_status_changed = Signal(str)
        closed = Signal()
        monitor_status = "Preparing update"
        is_active = True

        def __init__(self, *_a: object, **_kw: object) -> None:
            super().__init__()

        def show(self) -> None: ...

        def showNormal(self) -> None:  # noqa: N802
            calls.append("show")

        def raise_(self) -> None: ...

        def activateWindow(self) -> None: ...  # noqa: N802

        def focus_pending_input(self) -> None:
            calls.append("focus")

    monkeypatch.setattr("uptray.gui.tray.RunWindow", FakeWindow)
    monkeypatch.setattr(
        "uptray.gui.tray.launch_topgrade_in_terminal", lambda *_a: calls.append("launch")
    )
    monkeypatch.setattr(tray, "_show_updates", lambda: calls.append("updates"))
    assert not tray._action_open_run.isVisible()

    tray._run_topgrade()
    window = tray._run_window
    assert isinstance(window, FakeWindow)
    assert tray._action_open_run.isVisible()
    assert "Preparing update" in tray.toolTip()
    window.monitor_status = "Waiting for your answer"
    window.monitor_status_changed.emit(window.monitor_status)

    assert tray._action_status.text() == "Waiting for your answer"
    assert "Waiting for your answer" in tray.toolTip()
    tray._action_open_run.trigger()
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
    tray._run_topgrade_terminal()
    assert calls == ["show", "focus"] * 3
    assert tray.icon().cacheKey() == tray._icon_cache.checking().cacheKey()


@pytest.mark.parametrize(
    ("preview_args", "accepted_args"),
    [(["--dry-run"], ()), (["--only", "flatpak", "--dry-run"], (["--only", "flatpak"],))],
)
def test_run_after_preview_preserves_scope(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
    preview_args: list[str],
    accepted_args: tuple[object, ...],
) -> None:
    updates: list[tuple[object, ...]] = []
    callbacks: list[Callable[[], None]] = []

    class FakeWindow:
        def shutdown(self) -> None: ...

        is_active = False
        monitor_status_changed = type("S", (), {"connect": lambda *_a: None})()
        closed = type("S", (), {"connect": lambda *_a: None})()

        def __init__(self, *_a: object, on_run_for_real: Callable[[], None], **_kw: object) -> None:
            callbacks.append(on_run_for_real)

        def show(self) -> None: ...

    monkeypatch.setattr("uptray.gui.tray.RunWindow", FakeWindow)
    monkeypatch.setattr(tray, "_run_topgrade", lambda *args: updates.append(args))

    tray._open_run_window(preview_args)
    callbacks[0]()

    assert updates == [accepted_args]


def test_quit_stops_running_window_before_quitting(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeWindow:
        def __init__(self, *, allow: bool = True) -> None:
            self.allow = allow

        def confirm_stop(self) -> bool:
            calls.append("ask")
            return self.allow

        def shutdown(self) -> None:
            calls.append("window")

    monkeypatch.setattr("uptray.gui.tray.QApplication.quit", lambda: calls.append("quit"))
    tray._run_window = FakeWindow()

    tray._quit()
    assert calls == ["ask", "window", "quit"]

    calls.clear()
    tray._run_window = FakeWindow(allow=False)
    tray._quit()
    assert calls == ["ask"]  # declined: the update keeps running, app stays up


def _patch_check_thread(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    started: list[int] = []

    class FakeThread:
        def __init__(self, *_a: object) -> None:
            self.finished = type("S", (), {"connect": lambda *_a: None})()

        def isRunning(self) -> bool:  # noqa: N802
            return False

        def start(self) -> None:
            started.append(1)

    monkeypatch.setattr("uptray.gui.tray.CheckThread", FakeThread)
    monkeypatch.setattr("uptray.gui.tray.is_online", lambda: True)
    return started


def test_forced_check_runs_while_snoozed(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> None:
    started = _patch_check_thread(tray, monkeypatch)
    tray._snooze(1)

    tray._start_check()
    assert started == []
    tray._start_check(force=True)
    assert started == [1]


def test_reboot_flag_stays_false_while_snoozed(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr("uptray.gui.tray.send_message", lambda s, *a, **k: sent.append(s))
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    tray._snooze(1)
    reboot = CheckResult(
        source="reboot", updates=[Update("kernel", "", "reboot required", "reboot")]
    )

    tray._on_check_done([reboot])

    assert sent == []
    assert tray._state.reboot_notified is False


def test_default_left_click_shows_updates(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> None:
    from PySide6.QtWidgets import QSystemTrayIcon

    tray._cfg.tray.click_action = "default"
    shown: list[int] = []
    monkeypatch.setattr(tray, "_show_updates", lambda: shown.append(1))

    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)

    assert shown == [1]


def test_show_updates_opens_dialog_on_errors(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[object] = []

    class FakeDialog:
        def __init__(self, results: object) -> None:
            opened.append(results)

        def set_on_run(self, _cb: object) -> None: ...

        def set_on_preview(self, _cb: object) -> None: ...

        def set_on_run_only(self, _cb: object) -> None: ...

        def exec(self) -> int:
            return 0

    monkeypatch.setattr("uptray.gui.tray.UpdatesDialog", FakeDialog)
    tray._results = [CheckResult(source="pacman", error="boom")]

    tray._show_updates()

    assert len(opened) == 1


def test_shutdown_waits_a_bounded_time_for_a_running_check(tray: Tray) -> None:
    waited: list[tuple[object, ...]] = []

    class RunningThread:
        def isRunning(self) -> bool:  # noqa: N802
            return True

        def wait(self, *timeout: object) -> bool:
            waited.append(timeout)
            return True

    tray._check_thread = RunningThread()  # type: ignore[assignment]

    tray.shutdown()

    # Destroying a running QThread aborts the process, but a stuck check must not hang quit.
    assert waited and waited[0] and 0 < waited[0][0] <= 30_000  # type: ignore[operator]


def test_preview_while_running_explains_why(tray: Tray, monkeypatch) -> None:  # noqa: ANN001
    from PySide6.QtWidgets import QMessageBox, QWidget

    window = QWidget()
    window.is_active = True  # type: ignore[attr-defined]
    window._is_dry_run = False  # type: ignore[attr-defined]
    shown: list[str] = []
    window.showNormal = lambda: shown.append("show")  # type: ignore[method-assign]
    window.raise_ = lambda: None  # type: ignore[method-assign]
    window.activateWindow = lambda: None  # type: ignore[method-assign]
    window.focus_pending_input = lambda: None  # type: ignore[method-assign]
    tray._run_window = window  # type: ignore[assignment]
    messages: list[tuple[object, ...]] = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **_k: messages.append(args))

    tray._preview_topgrade()

    assert shown == ["show"]
    assert any("already running" in str(arg) for arg in messages[0])

    messages.clear()
    shown.clear()
    tray._open_current_run()

    assert shown == ["show"]
    assert messages == []
    tray._run_window = None


def test_snooze_until_tomorrow_ends_at_local_midnight(tray: Tray) -> None:
    from uptray.gui.tray_logic import next_local_midnight

    tray._snooze_until_tomorrow()

    assert tray._snooze_until == next_local_midnight()
    assert tray._action_status.text().startswith("Snoozed until ")
    assert tray._snooze_until.strftime("%Y-%m-%d") in tray._action_status.text()


def test_run_tray_reports_a_lock_error(monkeypatch, capsys) -> None:  # noqa: ANN001
    from uptray.gui.tray import run_tray

    def boom() -> None:
        raise PermissionError("denied")

    monkeypatch.setattr("uptray.gui.tray._acquire_instance_lock", boom)

    assert run_tray(Config()) == 2
    assert "could not create the tray lock" in capsys.readouterr().err


def test_sigterm_quits_the_event_loop() -> None:
    import os
    import subprocess
    import sys

    script = """
import os
import signal
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from uptray.gui.tray import install_termination_handler

app = QApplication([])
install_termination_handler(app)
QTimer.singleShot(200, lambda: os.kill(os.getpid(), signal.SIGTERM))
QTimer.singleShot(5000, lambda: os._exit(2))
raise SystemExit(app.exec())
"""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        check=False,
        timeout=15,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("offline", [False, True])
def test_run_completion_supersedes_queued_check_results(
    tray: Tray, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch, offline: bool
) -> None:
    from threading import Event

    online = True
    scans: list[CheckThread] = []
    notifications: list[object] = []
    pending_update = Update("old", "1", "2", "pacman")
    stale_results = [CheckResult("pacman", [pending_update, pending_update])]
    fresh_results = [CheckResult("pacman", error="mirror failed" if offline else None)]
    release_stale = Event()

    def check(worker: CheckThread) -> None:
        scans.append(worker)
        if len(scans) == 1:
            release_stale.wait(timeout=2)
            worker.results = stale_results
        else:
            worker.results = fresh_results

    monkeypatch.setattr("uptray.gui.tray.is_online", lambda: online)
    monkeypatch.setattr(
        "uptray.gui.tray.send_notification", lambda r, **_kw: notifications.append(r)
    )
    monkeypatch.setattr("uptray.gui.tray.maintenance_summary", lambda: [])
    monkeypatch.setattr(CheckThread, "run", check)
    tray._on_check_done([CheckResult("pacman", [pending_update])])
    notifications.clear()
    tray._start_check()
    stale = tray._check_thread
    assert stale is not None

    try:
        # Cover both signal-orderings without delivering the queued finished callback yet.
        if offline:
            release_stale.set()
            assert stale.wait(1000)
            online = False
        tray._on_run_finished(0)
        assert tray._check_thread is stale
        assert tray._action_status.text() == "Verifying updates…"
        assert "Verifying updates" in tray.toolTip()
        assert "update(s) available" not in tray.toolTip()
        assert "pacman (1)" not in [action.text() for action in tray.contextMenu().actions()]
        assert tray.icon().cacheKey() == tray._icon_cache.checking().cacheKey()
    finally:
        release_stale.set()

    if offline:
        qtbot.waitUntil(tray._offline_retry.isActive)
        assert tray._action_status.text() == "Verifying updates — waiting for network"
        assert len(scans) == 1
        assert notifications == []
        online = True
        tray._offline_retry.timeout.emit()

    qtbot.waitUntil(lambda: tray._results == fresh_results)
    assert len(scans) == 2
    assert notifications == []
    assert "Verifying updates" not in tray.toolTip()
    if offline:
        assert "Update check failed" in tray.toolTip()
        assert tray.icon().cacheKey() == tray._icon_cache.error().cacheKey()
    else:
        assert "System is up to date" in tray.toolTip()
        assert tray.icon().cacheKey() == tray._icon_cache.uptodate().cacheKey()
