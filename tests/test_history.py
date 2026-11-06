"""Tests for pacman.log upgrade-session parsing."""

from __future__ import annotations

from topgrade_update.core.history import parse_pacman_log

_SAMPLE_LOG = """\
[2026-11-01T09:00:00+0000] [PACMAN] Running 'pacman -Syu'
[2026-11-01T09:00:01+0000] [ALPM] transaction started
[2026-11-01T09:00:02+0000] [ALPM] upgraded firefox (130.0-1 -> 130.0-2)
[2026-11-01T09:00:02+0000] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
[2026-11-01T09:00:03+0000] [ALPM] installed newpackage (1.0-1)
[2026-11-01T09:00:04+0000] [ALPM] transaction completed
[2026-11-03T18:30:00+0000] [PACMAN] Running 'pacman -R oldpackage'
[2026-11-03T18:30:01+0000] [ALPM] transaction started
[2026-11-03T18:30:02+0000] [ALPM] removed oldpackage (2.0-1)
[2026-11-03T18:30:03+0000] [ALPM] transaction completed
[2026-11-05T08:00:00+0000] [ALPM] transaction started
[2026-11-05T08:00:01+0000] [ALPM] transaction completed
"""


def test_parse_groups_sessions_with_changes(tmp_path) -> None:  # noqa: ANN001
    log = tmp_path / "pacman.log"
    log.write_text(_SAMPLE_LOG, encoding="utf-8")

    sessions = parse_pacman_log(log)

    assert len(sessions) == 2
    first = sessions[0]
    assert first.counts() == {"upgraded": 2, "installed": 1, "removed": 0}
    assert first.changes[0].name == "firefox"
    assert first.changes[0].old_version == "130.0-1"
    assert first.finished is not None
    second = sessions[1]
    assert second.counts() == {"upgraded": 0, "installed": 0, "removed": 1}


def test_empty_transactions_are_skipped(tmp_path) -> None:  # noqa: ANN001
    log = tmp_path / "pacman.log"
    log.write_text(_SAMPLE_LOG, encoding="utf-8")

    sessions = parse_pacman_log(log)

    assert all(session.changes for session in sessions)


def test_missing_log_returns_empty(tmp_path) -> None:  # noqa: ANN001
    assert parse_pacman_log(tmp_path / "missing.log") == []


def test_malformed_lines_are_ignored(tmp_path) -> None:  # noqa: ANN001
    log = tmp_path / "pacman.log"
    log.write_text(
        "\n".join(
            [
                "garbage line",
                "[not-a-date] [ALPM] transaction started",
                "[2026-11-05T08:00:00+0000] [ALPM] upgraded we ird (1 -> 2)",
                "[2026-11-05T08:00:00+0000] [PACMAN] unrelated",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert parse_pacman_log(log) == []


def test_max_sessions_trims_oldest(tmp_path) -> None:  # noqa: ANN001
    log = tmp_path / "pacman.log"
    lines = []
    for i in range(5):
        ts = f"2026-11-0{i + 1}T10:00:00+0000"
        lines.extend(
            [
                f"[{ts}] [ALPM] transaction started",
                f"[{ts}] [ALPM] installed pkg{i} (1.0)",
                f"[{ts}] [ALPM] transaction completed",
            ]
        )
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    sessions = parse_pacman_log(log, max_sessions=2)

    assert [s.changes[0].name for s in sessions] == ["pkg3", "pkg4"]
