from __future__ import annotations

from datetime import datetime

from uptray.core.models import CheckResult, Update
from uptray.core.notification_engine import NotificationEngine
from uptray.core.quiet_hours import is_quiet_hours


def _result(source: str, count: int) -> CheckResult:
    return CheckResult(
        source=source,
        updates=[
            Update(
                name=f"{source}-{idx}",
                old_version="1.0",
                new_version="2.0",
                source=source,
            )
            for idx in range(count)
        ],
    )


def test_should_notify_when_updates_first_appear() -> None:
    engine = NotificationEngine()

    assert engine.should_notify([]) is False
    assert engine.should_notify([_result("pacman", 2)]) is True


def test_should_notify_only_when_total_count_increases() -> None:
    engine = NotificationEngine()

    assert engine.should_notify([_result("pacman", 2)]) is True
    assert engine.should_notify([_result("pacman", 2)]) is False
    assert engine.should_notify([_result("pacman", 1)]) is False
    assert engine.should_notify([_result("pacman", 3)]) is True


def test_maybe_defer_queues_only_during_quiet_hours() -> None:
    engine = NotificationEngine()
    results = [_result("flatpak", 1)]

    assert engine.maybe_defer(results) is False

    engine.enter_quiet_hours()

    assert engine.maybe_defer(results) is True
    assert engine.maybe_defer([_result("aur", 2)]) is True

    deferred = engine.exit_quiet_hours()

    assert [item["results"] for item in deferred] == [results, [_result("aur", 2)]]
    assert engine.exit_quiet_hours() == []


def test_deferred_notification_records_total_and_sources() -> None:
    engine = NotificationEngine()
    results = [_result("pacman", 1), _result("aur", 2)]

    engine.enter_quiet_hours()
    assert engine.maybe_defer(results) is True

    [deferred] = engine.exit_quiet_hours()

    assert deferred["total"] == 3
    assert deferred["sources"] == {"pacman": 1, "aur": 2}
    assert deferred["results"] == results


def test_is_quiet_hours_supports_normal_windows() -> None:
    assert is_quiet_hours(9, 17, datetime(2026, 5, 20, 12)) is True
    assert is_quiet_hours(9, 17, datetime(2026, 5, 20, 20)) is False


def test_is_quiet_hours_supports_wraparound_windows() -> None:
    assert is_quiet_hours(23, 8, datetime(2026, 5, 20, 2)) is True
    assert is_quiet_hours(23, 8, datetime(2026, 5, 20, 12)) is False


def test_is_quiet_hours_is_disabled_when_unset_or_equal() -> None:
    assert is_quiet_hours(None, 8, datetime(2026, 5, 20, 2)) is False
    assert is_quiet_hours(23, None, datetime(2026, 5, 20, 2)) is False
    assert is_quiet_hours(8, 8, datetime(2026, 5, 20, 8)) is False


def test_reboot_is_not_counted_as_an_update() -> None:
    from uptray.core.checkers import total_updates

    results = [_result("pacman", 1), _result("reboot", 1)]
    engine = NotificationEngine()

    assert total_updates(results) == 1
    assert engine.should_notify([_result("reboot", 1)]) is False
    engine.enter_quiet_hours()
    engine.maybe_defer(results)
    assert engine.exit_quiet_hours()[0]["sources"] == {"pacman": 1}
