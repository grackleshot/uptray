from __future__ import annotations

from datetime import datetime, timedelta

from uptray.gui.tray_logic import is_snoozed, snooze_label


def test_is_snoozed_only_when_until_time_is_in_future() -> None:
    now = datetime(2026, 5, 20, 12, 0)

    assert is_snoozed(None, now) is False
    assert is_snoozed(now - timedelta(minutes=1), now) is False
    assert is_snoozed(now + timedelta(minutes=1), now) is True


def test_snooze_label_shows_target_time() -> None:
    until = datetime(2026, 5, 20, 16, 30)

    assert snooze_label(until) == "Snoozed until 16:30"
