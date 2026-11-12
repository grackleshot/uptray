"""Summaries of saved topgrade run transcripts (Qt-free)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from uptray.core.topgrade_session import (
    _ParserState,
    list_run_logs,
    parse_topgrade_chunk,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["RunSummary", "list_runs", "summarize_run"]

Outcome = Literal["ok", "failed", "incomplete"]
_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_STAMP_LEN = 16
_MAX_RUNS = 50


@dataclass(frozen=True)
class RunSummary:
    """One saved run transcript, summarized."""

    path: Path
    started: datetime
    duration_s: float
    outcome: Outcome
    failed_steps: tuple[str, ...]


def _started_from(path: Path, fallback: float) -> datetime:
    """Parse the UTC stamp in the filename; fall back to *fallback* (mtime)."""
    try:
        return datetime.strptime(path.name[:_STAMP_LEN], _STAMP_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return datetime.fromtimestamp(fallback, tz=timezone.utc)


def summarize_run(path: Path) -> RunSummary:
    """Parse *path* with the live-session parser and classify the outcome."""
    state = _ParserState()
    parse_topgrade_chunk(state, path.read_text(encoding="utf-8", errors="replace"))
    failed = tuple(name for name, status in state.steps.items() if status == "failed")
    outcome: Outcome = "incomplete"
    if failed:
        outcome = "failed"
    elif "Summary" in state.steps:
        outcome = "ok"
    ended = path.stat().st_mtime
    started = _started_from(path, ended)
    return RunSummary(
        path=path,
        started=started,
        duration_s=max(0.0, ended - started.timestamp()),
        outcome=outcome,
        failed_steps=failed,
    )


def list_runs(runs_dir: Path | None = None) -> list[RunSummary]:
    """Summarize saved runs, newest first; empty transcripts are skipped."""
    # shortcut: only the newest 50 transcripts are parsed, raise if users want deeper history
    paths = [p for p in list_run_logs(runs_dir) if p.stat().st_size > 0][:_MAX_RUNS]
    return [summarize_run(path) for path in paths]
