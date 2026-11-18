"""Tests for run transcript summaries."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from uptray.core.run_history import list_runs, prune_runs, summarize_run
from uptray.core.run_metadata import describe_run_scope, metadata_path
from uptray.core.topgrade_session import TopgradeSession

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


def test_prune_runs_keeps_only_the_runs_history_can_show(tmp_path: Path) -> None:
    logs = []
    for i in range(53):
        log = _write(tmp_path, f"20261117T1200{i:02d}Z-1-{i}.log", "output")
        metadata_path(log).write_text("{}")
        os.utime(log, (1_000 + i, 1_000 + i))
        logs.append(log)

    prune_runs(tmp_path, keep=50)

    oldest, kept = logs[:3], logs[3:]
    assert not any(log.exists() or metadata_path(log).exists() for log in oldest)
    assert all(log.exists() and metadata_path(log).exists() for log in kept)


def test_legacy_success_rows_do_not_confirm_process_exit(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _OK))
    assert run.outcome == "incomplete"
    assert run.failed_steps == ()
    assert run.started.strftime("%Y-%m-%d %H:%M") == "2026-11-05 09:00"
    assert run.scope == "Unknown scope"
    assert run.returncode is None
    assert run.finished is None


def test_failed_run(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _FAILED))
    assert run.outcome == "failed"
    assert run.failed_steps == ("Pacman",)


def test_run_without_summary_is_incomplete(tmp_path: Path) -> None:
    run = summarize_run(_write(tmp_path, "20261105T090000Z-1-1.log", _PARTIAL))
    assert run.outcome == "incomplete"


def test_legacy_retry_diagnostic_does_not_confirm_final_outcome(tmp_path: Path) -> None:
    log_path = _write(
        tmp_path, "retry.log",
        "── Flatpak ──\nFlatpak failed: example reason\nRetry? (y)es/(N)o/(s)hell/(q)uit",
    )
    run = summarize_run(log_path)
    assert run.outcome == "incomplete"
    assert run.returncode is None


def test_list_runs_skips_empty_and_agent_transcripts(tmp_path: Path) -> None:
    _write(tmp_path, "20261105T090000Z-1-1.log", _OK)
    _write(tmp_path, "20261106T090000Z-1-2.log", "")
    _write(tmp_path / "agents", "20261107T090000Z-1-3.log", _OK)
    runs = list_runs(tmp_path)
    assert [r.path.name for r in runs] == ["20261105T090000Z-1-1.log"]


def test_history_reads_observed_status_even_after_summary_heading(tmp_path: Path) -> None:
    session = TopgradeSession(
        ["/bin/sh", "-c", 'printf "── Summary ──\n"; exit 2'],
        runs_dir=tmp_path,
        extra_args=["--dry-run", "--only", "system"],
        enable_askpass=False,
    )
    session.start()
    try:
        assert session.wait(timeout=5) == 2
    finally:
        session.close()
    (run,) = list_runs(tmp_path)
    assert run == summarize_run(session.log_path)
    assert run.outcome == "failed"
    assert run.returncode == 2
    assert run.finished is not None and run.finished >= run.started
    assert run.duration_s == (run.finished - run.started).total_seconds()
    assert run.scope == "Preview system packages (pacman + AUR)"
    assert not run.transcript_incomplete


def test_saved_empty_log_keeps_confirmed_outcome(tmp_path: Path) -> None:
    session = TopgradeSession(["/bin/true"], runs_dir=tmp_path, enable_askpass=False)
    session.start()
    try:
        assert session.wait(timeout=5) == 0
    finally:
        session.close()
    (run,) = list_runs(tmp_path)
    assert run.outcome == "ok"
    assert run.scope == "Full update"
    assert not run.transcript_incomplete

    session.log_path.unlink()
    (run,) = list_runs(tmp_path)
    assert run.outcome == "ok"
    assert run.transcript_incomplete


def test_history_tolerates_corrupt_metadata_and_nonregular_logs(tmp_path: Path) -> None:
    log_path = _write(tmp_path, "ambiguous.log", "── Summary ──\n")
    metadata_path(log_path).write_text('{"version": 1,')
    pipe = tmp_path / "fifo.log"
    os.mkfifo(pipe)

    (run,) = list_runs(tmp_path)
    assert run.path == log_path
    assert run.outcome == "incomplete"
    assert summarize_run(pipe).transcript_incomplete


def test_run_scope_handles_individual_and_multiple_only_arguments() -> None:
    assert describe_run_scope(()) == "Full update"
    assert describe_run_scope(("--run-type", "dry")) == "Preview"
    assert describe_run_scope(("--only=flatpak", "firmware", "-n")) == "Preview Flatpak, firmware"
