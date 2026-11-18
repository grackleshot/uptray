"""Summaries of saved topgrade run transcripts (Qt-free)."""

from __future__ import annotations

import contextlib
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from uptray.core.run_metadata import RunMetadata, metadata_path, read_metadata
from uptray.core.topgrade_session import (
    _ParserState,
    default_runs_dir,
    finish_topgrade_parse,
    list_run_logs,
    parse_topgrade_chunk,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["RunSummary", "list_runs", "prune_runs", "summarize_run"]

Outcome = Literal["ok", "failed", "cancelled", "incomplete"]
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
    scope: str = "Unknown scope"
    finished: datetime | None = None
    returncode: int | None = None
    transcript_incomplete: bool = False


def _started_from(path: Path, fallback: float) -> datetime:
    """Parse the UTC stamp in the filename; fall back to *fallback* (mtime)."""
    try:
        return datetime.strptime(path.name[:_STAMP_LEN], _STAMP_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return datetime.fromtimestamp(fallback, tz=timezone.utc)


def summarize_run(path: Path) -> RunSummary:
    """Summarize a run by its saved outcome, falling back to legacy text."""
    record = read_metadata(metadata_path(path))
    if record is not None and record.path == path:
        return _summarize_metadata(record)
    info = path.stat()
    return _summarize_legacy(path, info.st_mtime, regular=stat.S_ISREG(info.st_mode))


def _summarize_metadata(record: RunMetadata) -> RunSummary:
    outcome: Outcome = "ok" if record.returncode == 0 else "failed"
    if record.cancelled:
        outcome = "cancelled"
    return RunSummary(
        path=record.path,
        started=record.started,
        duration_s=max(0.0, (record.finished - record.started).total_seconds()),
        outcome=outcome,
        failed_steps=record.failed_steps,
        scope=record.scope,
        finished=record.finished,
        returncode=record.returncode,
        transcript_incomplete=record.transcript_incomplete or not record.path.is_file(),
    )


def _summarize_legacy(path: Path, ended: float, *, regular: bool) -> RunSummary:
    state = _ParserState()
    if regular:
        with path.open(encoding="utf-8", errors="replace", newline="") as log:
            while chunk := log.read(65536):
                parse_topgrade_chunk(state, chunk)
        finish_topgrade_parse(state)
    started = _started_from(path, ended)
    reported_failure = any(name in state.reported_steps for name in state.failed_steps)
    return RunSummary(
        path=path,
        started=started,
        duration_s=max(0.0, ended - started.timestamp()),
        outcome="failed" if reported_failure else "incomplete",
        failed_steps=state.failed_steps,
        transcript_incomplete=not regular,
    )


def list_runs(runs_dir: Path | None = None) -> list[RunSummary]:
    """Summarize the newest saved outcomes and older nonempty logs."""
    directory = runs_dir if runs_dir is not None else default_runs_dir()
    records: list[RunSummary] = []
    recorded_paths: set[Path] = set()
    for path in directory.glob("*.log.json"):
        record = read_metadata(path)
        if record is not None:
            records.append(_summarize_metadata(record))
            recorded_paths.add(record.path.absolute())

    # Parse text only for recent legacy runs.
    legacy_count = 0
    for path in list_run_logs(directory):
        if path.absolute() in recorded_paths:
            continue
        try:
            info = path.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
                continue
            records.append(_summarize_legacy(path, info.st_mtime, regular=True))
        except OSError:
            continue
        legacy_count += 1
        if legacy_count >= _MAX_RUNS:
            break
    return sorted(records, key=lambda run: run.started, reverse=True)[:_MAX_RUNS]


def prune_runs(runs_dir: Path | None = None, keep: int = _MAX_RUNS) -> None:
    """Delete transcripts and outcomes older than the newest runs History shows."""
    for path in list_run_logs(runs_dir)[keep:]:
        for stale in (path, metadata_path(path)):
            with contextlib.suppress(OSError):
                stale.unlink(missing_ok=True)
