from __future__ import annotations

from datetime import datetime, timedelta

from uptray.gui.tray_logic import is_snoozed, next_local_midnight, snooze_label


def test_is_snoozed_only_when_until_time_is_in_future() -> None:
    now = datetime(2026, 5, 20, 12, 0)

    assert is_snoozed(None, now) is False
    assert is_snoozed(now - timedelta(minutes=1), now) is False
    assert is_snoozed(now + timedelta(minutes=1), now) is True


def test_snooze_label_shows_target_time() -> None:
    until = datetime(2026, 5, 20, 16, 30)
    now = datetime(2026, 5, 20, 12, 0)

    assert snooze_label(until, now) == "Snoozed until 16:30"


def test_snooze_label_includes_the_date_when_it_is_not_today() -> None:
    until = datetime(2026, 5, 21, 0, 0)
    now = datetime(2026, 5, 20, 18, 0)

    assert snooze_label(until, now) == "Snoozed until 2026-05-21 00:00"


def test_next_local_midnight_is_tomorrow() -> None:
    now = datetime(2026, 5, 20, 23, 30).astimezone()

    midnight = next_local_midnight(now)

    assert midnight.date() == now.date() + timedelta(days=1)
    assert midnight.hour == 0
    assert midnight.minute == 0
    assert midnight.tzinfo is not None
