"""Tests for run transcript summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING

from topgrade_update.core.run_history import list_runs, summarize_run

if TYPE_CHECKING:
    from pathlib import Path

_OK = "── 12:00:00 - Flatpak ────\nwork\nFlatpak: OK\n── 12:00:05 - Summary ────\nFlatpak: OK\n"
_FAILED = "── 12:00:00 - Pacman ────\nboom\nPacman: FAILED\n── 12:00:05 - Summary ────\n"
_PARTIAL = "── 12:00:00 - Flatpak ────\nworking\n"


def _write(directory: Path, name: str, text: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text)
    return path


def test_ok_run(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _OK))
    assert run.outcome == "ok"
    assert run.failed_steps == ()
    assert run.started.strftime("%Y-%m-%d %H:%M") == "2026-11-05 09:00"


def test_failed_run(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _FAILED))
    assert run.outcome == "failed"
    assert run.failed_steps == ("Pacman",)


def test_run_without_summary_is_incomplete(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _PARTIAL))
    assert run.outcome == "incomplete"


def test_list_runs_skips_empty_and_agent_transcripts(tmp_path: Path) -> None:
    _write(tmp_path, "20261105T090000Z-1-1.log", _OK)
    _write(tmp_path, "20261106T090000Z-1-2.log", "")
    _write(tmp_path / "agents", "20261107T090000Z-1-3.log", _OK)
    runs = list_runs(tmp_path)
    assert [r.path.name for r in runs] == ["20261105T090000Z-1-1.log"]
