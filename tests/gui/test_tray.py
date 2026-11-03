"""Tests for the system tray applet."""

from __future__ import annotations

from datetime import datetime, timedelta

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


def test_tray_initialization(mock_cfg: Config, qapp) -> None:  # noqa: ANN001
    """Build real Qt tray objects and expose the expected menu actions."""
    tray = Tray(mock_cfg)

    assert tray.toolTip() == APP_NAME
    assert tray.contextMenu() is not None
    action_labels = [action.text() for action in tray.contextMenu().actions()]
    assert "Idle" in action_labels
    assert "Check Now" in action_labels
    assert "View Updates" in action_labels
    assert "Run Topgrade" in action_labels
    assert "Quit" in action_labels


def test_snooze_logic_updates_status_and_timer(mock_cfg: Config, qapp) -> None:  # noqa: ANN001
    """Snoozing records a target time, updates the menu, and arms its timer."""
    tray = Tray(mock_cfg)
    started = datetime.now()

    tray._snooze(2)

    assert tray._snooze_until is not None
    assert started + timedelta(hours=2) <= tray._snooze_until
    assert abs((tray._snooze_until - datetime.now()).total_seconds() - 7200) < 1
    assert tray._action_status.text().startswith("Snoozed until ")
    assert tray._snooze_timer.isActive()
    assert tray._snooze_timer.interval() == 7_200_000


def test_is_snoozed_clears_expired_target(mock_cfg: Config, qapp) -> None:  # noqa: ANN001
    """The tray recognizes active snoozes and clears expired targets."""
    tray = Tray(mock_cfg)

    assert tray._is_snoozed() is False
    tray._snooze(1)
    assert tray._is_snoozed() is True

    tray._snooze_until = datetime.now() - timedelta(seconds=1)
    assert tray._is_snoozed() is False
    assert tray._snooze_until is None


def test_partial_check_failure_is_visible_in_status_and_tooltip(
    mock_cfg: Config,
    qapp,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The tray reports source failures even when another source found updates."""
    tray = Tray(mock_cfg)
    sent_notifications: list[dict[str, object]] = []

    def capture_notification(_results: list[CheckResult], **kwargs: object) -> None:
        sent_notifications.append(kwargs)

    monkeypatch.setattr("topgrade_update.gui.tray.send_notification", capture_notification)
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
    mock_cfg: Config,
    qapp,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tray = Tray(mock_cfg)
    called: list[str] = []
    monkeypatch.setattr(tray, "_run_topgrade", lambda: called.append("run"))
    monkeypatch.setattr(tray, "_snooze", lambda hours: called.append(f"snooze:{hours}"))

    tray._on_notification_action("run_topgrade")
    tray._on_notification_action("snooze")
    tray._on_notification_action("dismiss")

    assert called == ["run", "snooze:1"]
