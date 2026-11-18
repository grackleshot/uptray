"""Persistent outcomes for monitored Topgrade runs."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_STEP_NAMES = {
    "flatpak": "Flatpak",
    "firmware": "firmware",
    "system": "system packages (pacman + AUR)",
}


def describe_run_scope(extra_args: Sequence[str]) -> str:
    """Describe the explicit scope requested by the Topgrade arguments."""
    preview = False
    only: list[str] = []
    reading_only = False
    for i, arg in enumerate(extra_args):
        if arg == "--":
            break
        if arg.startswith("-"):
            reading_only = arg.partition("=")[0] == "--only"
            if reading_only and "=" in arg:
                only.append(arg.partition("=")[2])
            preview |= (
                arg in {"--dry-run", "-n", "--run-type=dry", "-r=dry"}
                or (
                    arg in {"--run-type", "-r"}
                    and i + 1 < len(extra_args)
                    and extra_args[i + 1] == "dry"
                )
            )
        elif reading_only:
            only.append(arg)
    if only:
        steps = ", ".join(_STEP_NAMES.get(step, step.replace("_", " ")) for step in only)
        return f"{'Preview' if preview else 'Update'} {steps}"
    return "Preview" if preview else "Full update"


def metadata_path(log_path: Path) -> Path:
    return log_path.with_suffix(f"{log_path.suffix}.json")


@dataclass(frozen=True)
class RunMetadata:
    path: Path
    scope: str
    started: datetime
    finished: datetime
    returncode: int
    cancelled: bool
    transcript_incomplete: bool
    failed_steps: tuple[str, ...]


def save_metadata(path: Path, record: RunMetadata) -> None:
    """Replace a complete record atomically after flushing it to disk."""
    transcript = record.path.name if record.path.parent == path.parent else str(
        record.path.absolute()
    )
    data = {
        "version": 1,
        "transcript": transcript,
        "scope": record.scope,
        "started": record.started.isoformat(),
        "finished": record.finished.isoformat(),
        "returncode": record.returncode,
        "cancelled": record.cancelled,
        "transcript_incomplete": record.transcript_incomplete,
        "failed_steps": record.failed_steps,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, mode="w", encoding="utf-8", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)


def read_metadata(path: Path) -> RunMetadata | None:
    """Return a validated record, tolerating missing and damaged metadata."""
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            return None
        started = datetime.fromisoformat(data["started"])
        finished = datetime.fromisoformat(data["finished"])
        transcript = data["transcript"]
        scope = data["scope"]
        returncode = data["returncode"]
        cancelled = data["cancelled"]
        transcript_incomplete = data["transcript_incomplete"]
        failed_steps = data["failed_steps"]
        if (
            started.tzinfo is None or finished.tzinfo is None
            or not isinstance(transcript, str) or not transcript or "\0" in transcript
            or not isinstance(scope, str) or not scope
            or type(returncode) is not int
            or not isinstance(cancelled, bool)
            or not isinstance(transcript_incomplete, bool)
            or not isinstance(failed_steps, list)
            or not all(isinstance(name, str) for name in failed_steps)
        ):
            return None
        return RunMetadata(
            path=path.parent / transcript,
            scope=scope,
            started=started,
            finished=finished,
            returncode=returncode,
            cancelled=cancelled,
            transcript_incomplete=transcript_incomplete,
            failed_steps=tuple(failed_steps),
        )
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return None
