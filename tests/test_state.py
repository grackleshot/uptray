"""Tests for persistent application state."""

from __future__ import annotations

from datetime import datetime, timedelta

from uptray.core.state import (
    AppState,
    format_snooze,
    load_state,
    parse_snooze,
    save_state,
)


def test_load_returns_defaults_for_missing_file(tmp_path) -> None:  # noqa: ANN001
    state = load_state(tmp_path / "state.json")

    assert state == AppState()


def test_save_and_load_roundtrip(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "state.json"
    state = AppState(
        snooze_until="2026-11-05T18:00:00",
        prev_total=7,
        last_seen_news="2026-11-01",
        reboot_notified=True,
        maintenance_check_date="2026-11-05",
    )

    save_state(state, path)
    loaded = load_state(path)

    assert loaded == state


def test_load_ignores_corrupt_json(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")

    assert load_state(path) == AppState()


def test_load_ignores_wrong_types(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / "state.json"
    path.write_text(
        '{"snooze_until": 5, "prev_total": true, "reboot_notified": "yes", "junk": 1}',
        encoding="utf-8",
    )

    state = load_state(path)

    assert state.snooze_until is None
    assert state.prev_total == -1
    assert state.reboot_notified is False


def test_parse_and_format_snooze_roundtrip() -> None:
    target = datetime.now() + timedelta(hours=3)

    formatted = format_snooze(target)

    assert formatted is not None
    parsed = parse_snooze(formatted)
    assert parsed is not None
    assert abs((parsed - target).total_seconds()) < 1


def test_parse_snooze_handles_invalid_input() -> None:
    assert parse_snooze(None) is None
    assert parse_snooze("") is None
    assert parse_snooze("not-a-date") is None


def test_save_state_swallows_unwritable_paths(tmp_path) -> None:  # noqa: ANN001
    # A path whose parent is a regular file cannot be created; save must not raise.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")

    save_state(AppState(), blocker / "nested" / "state.json")
