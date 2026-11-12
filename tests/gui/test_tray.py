"""Tests for the system tray applet."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from topgrade_update.core.models import CheckResult, Config, NotificationConfig, TrayConfig, Update

pytest.importorskip("PySide6")

from topgrade_update.gui.tray import APP_NAME, Tray  # noqa: E402


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
    started = datetime.now()

    tray._snooze(2)

    assert tray._snooze_until is not None
    assert started + timedelta(hours=2) <= tray._snooze_until
    assert abs((tray._snooze_until - datetime.now()).total_seconds() - 7200) < 1
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

    tray._snooze_until = datetime.now() - timedelta(seconds=1)
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

    monkeypatch.setattr("topgrade_update.gui.tray.send_notification", capture_notification)
    monkeypatch.setattr("topgrade_update.gui.tray.maintenance_summary", lambda: [])
    results = [
        CheckResult(
            source="pacman",
            updates=[Update("package", "1", "2", "pacman")],
        ),
        CheckResult(source="flatpak", error="remote unavailable"),
    ]

    tray._on_check_done(results)

    assert tray._action_status.text().startswith(
        "1 update(s) available; 1 source(s) failed"
    )
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

    monkeypatch.setattr("topgrade_update.gui.tray.send_message", capture_message)
    monkeypatch.setattr("topgrade_update.gui.tray.maintenance_summary", lambda: [])
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


def test_reboot_flag_resets_when_no_longer_pending(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("topgrade_update.gui.tray.send_message", lambda *a, **k: None)
    monkeypatch.setattr("topgrade_update.gui.tray.maintenance_summary", lambda: [])
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

    monkeypatch.setattr("topgrade_update.gui.tray.send_message", capture_message)

    from topgrade_update.core.maintenance import MaintenanceFinding

    def fake_summary(**_kwargs: object) -> list[MaintenanceFinding]:
        return [MaintenanceFinding("orphans", "2 orphan package(s)", ["a", "b"])]

    monkeypatch.setattr("topgrade_update.gui.tray.maintenance_summary", fake_summary)

    with_updates = CheckResult(
        source="pacman", updates=[Update("pkg", "1", "2", "pacman")]
    )
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


def test_news_menu_and_mark_read(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from topgrade_update.core.arch_news import NewsItem

    opened: list[str] = []
    monkeypatch.setattr("topgrade_update.gui.tray.open_url", lambda url: opened.append(url))

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
    monkeypatch.setattr("topgrade_update.gui.tray.is_online", lambda: False)

    tray._start_check()

    assert tray._action_status.text() == "Offline — waiting for network"
    assert tray._offline_retry.isActive()


def test_open_run_window_starts_new_run_after_finished(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class FakeWindow:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.is_active = False
            created.append(self)

        def isVisible(self) -> bool:  # noqa: N802
            return True

        def raise_(self) -> None:
            return None

        def activateWindow(self) -> None:  # noqa: N802
            return None

        def close(self) -> None:
            return None

        def show(self) -> None:
            return None

    monkeypatch.setattr("topgrade_update.gui.tray.RunWindow", FakeWindow)
    tray._run_window = FakeWindow()
    tray._open_run_window([])
    assert len(created) == 2


def test_open_run_window_reshows_hidden_running_window(
    tray: Tray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class FakeWindow:
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

    monkeypatch.setattr("topgrade_update.gui.tray.RunWindow", FakeWindow)
    tray._run_window = FakeWindow()

    tray._open_run_window([])

    assert len(created) == 1
    assert created[0].reshown  # type: ignore[attr-defined]


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

    monkeypatch.setattr(
        "topgrade_update.gui.tray.QApplication.quit", lambda: calls.append("quit")
    )
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
            self.result = type("S", (), {"connect": lambda *_a: None})()

        def isRunning(self) -> bool:  # noqa: N802
            return False

        def start(self) -> None:
            started.append(1)

    monkeypatch.setattr("topgrade_update.gui.tray.CheckThread", FakeThread)
    monkeypatch.setattr("topgrade_update.gui.tray.is_online", lambda: True)
    return started


def test_forced_check_runs_while_snoozed(tray: Tray, monkeypatch: pytest.MonkeyPatch) -> None:
    started = _patch_check_thread(tray, monkeypatch)
    tray._snooze(1)

    tray._start_check()
    assert started == []
    tray._start_check(force=True)
    assert started == [1]


def test_reboot_flag_stays_false_while_snoozed(
    tray: Tray, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setattr("topgrade_update.gui.tray.send_message", lambda s, *a, **k: sent.append(s))
    monkeypatch.setattr("topgrade_update.gui.tray.maintenance_summary", lambda: [])
    tray._snooze(1)
    reboot = CheckResult(
        source="reboot", updates=[Update("kernel", "", "reboot required", "reboot")]
    )

    tray._on_check_done([reboot])

    assert sent == []
    assert tray._state.reboot_notified is False


def test_default_left_click_shows_updates(
    tray: Tray, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QSystemTrayIcon

    tray._cfg.tray.click_action = "default"
    shown: list[int] = []
    monkeypatch.setattr(tray, "_show_updates", lambda: shown.append(1))

    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)

    assert shown == [1]


def test_show_updates_opens_dialog_on_errors(
    tray: Tray, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[object] = []

    class FakeDialog:
        def __init__(self, results: object) -> None:
            opened.append(results)

        def set_on_run(self, _cb: object) -> None: ...

        def set_on_preview(self, _cb: object) -> None: ...

        def set_on_run_only(self, _cb: object) -> None: ...

        def exec(self) -> int:
            return 0

    monkeypatch.setattr("topgrade_update.gui.tray.UpdatesDialog", FakeDialog)
    tray._results = [CheckResult(source="pacman", error="boom")]

    tray._show_updates()

    assert len(opened) == 1


def test_shutdown_waits_for_a_running_check(tray: Tray) -> None:
    waited: list[int] = []

    class RunningThread:
        def isRunning(self) -> bool:  # noqa: N802
            return True

        def wait(self, ms: int) -> bool:
            waited.append(ms)
            return True

    tray._check_thread = RunningThread()  # type: ignore[assignment]

    tray.shutdown()

    assert waited  # destroying a running QThread aborts the process
