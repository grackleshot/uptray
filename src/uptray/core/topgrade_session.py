"""PTY-backed topgrade session with log capture and output parsing.

Qt-free so the session can be unit-tested with a fake command.
"""

from __future__ import annotations

import atexit
import codecs
import contextlib
import errno
import fcntl
import functools
import logging
import os
import pty
import queue
import re
import select
import shlex
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Literal

from uptray.core.run_metadata import RunMetadata, describe_run_scope, metadata_path, save_metadata

__all__ = [
    "AskpassExpired",
    "AskpassRequest",
    "OutputChunk",
    "RETRY_PROMPT",
    "RetryPrompt",
    "RunMode",
    "SessionEvent",
    "SessionFinished",
    "StepEvent",
    "StepStatus",
    "TopgradeSession",
    "TranscriptWarning",
    "available_agents",
    "build_agent_command",
    "build_diagnose_prompt",
    "default_runs_dir",
    "list_run_logs",
    "parse_idle",
    "parse_topgrade_chunk",
    "strip_ansi",
]

RunMode = Literal["simple", "verbose"]
StepStatus = Literal["pending", "running", "ended", "succeeded", "failed", "skipped"]

_log = logging.getLogger(__name__)
_ASKPASS_TIMEOUT_S = 300
RETRY_PROMPT = "Retry? (y)es/(N)o/(s)hell/(q)uit"

_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][0-9A-Za-z])"
)
# Step headers: "── 22:52:35 - Sudo ──────" (box) or "―― 22:52:35 - Sudo ――" (plain).
# The timestamp is optional and never part of the step's identity.
_STEP_NAME = r"(?:(?P<time>\d{2}:\d{2}:\d{2})\s+-\s+)?(?P<name>.+?)"
_SEPARATOR_BOX_RE = re.compile(rf"──\s+{_STEP_NAME}\s+─{{2,}}\s*$")
_SEPARATOR_PLAIN_RE = re.compile(rf"――\s+{_STEP_NAME}\s+――\s*$")
_RESULT_RE = re.compile(
    r"^(?P<name>.+?):\s+(?P<status>OK|FAILED|IGNORED|SKIPPED)(?::\s*(?P<reason>.*))?$"
)
_FAILURE_RE = re.compile(r"^(?P<name>.+?) failed:\s*(?P<reason>.*)$")
_MAX_REASON_LENGTH = 8192
_RETRY_RE = re.compile(re.escape(RETRY_PROMPT))
# Interactive yes/no prompts use the [Y/n] bracket convention (topgrade child
# commands: paru, pacdiff, maintainer scripts, ...). Anything between the
# brackets may decorate y/n (e.g. [yes/no], [Y/n/?]).
_PROMPT_RE = re.compile(r"\[[^\]]*[Yy][^\]]*/[^\]]*[Nn][^\]]*\]")
# Prompts that need a typed answer, matched only on a line still awaiting input:
# pacdiff "...: [v/s/r/o/q]", pacman "Enter a number (default=1):", paru/yay "==>".
_MENU_RE = re.compile(r"\[(?:\w+/)+\w+\]\s*:?$|Enter a (?:selection|number)\b.*:$|^==>$")
_AGENT_COMMANDS: dict[str, tuple[str, ...]] = {
    "claude": ("claude",),
    "codex": ("codex",),
    "pi": ("pi",),
}


class SessionEventKind(Enum):
    """Kinds of structured session events."""

    OUTPUT = "output"
    STEP = "step"
    RETRY = "retry"
    ASKPASS = "askpass"
    PROMPT = "prompt"
    TRANSCRIPT_WARNING = "transcript_warning"
    FINISHED = "finished"


@dataclass(frozen=True)
class OutputChunk:
    """Raw (or mostly raw) bytes decoded from the PTY."""

    text: str
    kind: SessionEventKind = SessionEventKind.OUTPUT


@dataclass
class StepEvent:
    """A parsed topgrade step transition."""

    name: str
    status: StepStatus
    latest_line: str = ""
    reason: str | None = None
    kind: SessionEventKind = SessionEventKind.STEP


@dataclass(frozen=True)
class RetryPrompt:
    """Topgrade asked whether to retry a failed step."""

    step_name: str | None
    kind: SessionEventKind = SessionEventKind.RETRY


@dataclass(frozen=True)
class AskpassRequest:
    """sudo askpass helper requested a password."""

    prompt: str
    request_id: int
    kind: SessionEventKind = SessionEventKind.ASKPASS


@dataclass(frozen=True)
class AskpassExpired:
    """The helper stopped waiting for a reply to this password request."""

    request_id: int
    kind: SessionEventKind = SessionEventKind.ASKPASS


@dataclass(frozen=True)
class PromptRequest:
    """The running command asked the user a question.

    Yes/no questions follow the ``[Y/n]`` bracket convention; ``free_text``
    marks menu-style prompts that need a typed answer. One event per unique
    question until output resumes.
    """

    question: str
    free_text: bool = False
    kind: SessionEventKind = SessionEventKind.PROMPT


@dataclass(frozen=True)
class PromptCleared:
    """A previously announced prompt was answered or superseded."""

    kind: SessionEventKind = SessionEventKind.PROMPT


@dataclass(frozen=True)
class TranscriptWarning:
    """The session could not capture, interpret, or save part of the run."""

    message: str
    kind: SessionEventKind = SessionEventKind.TRANSCRIPT_WARNING
    transcript_incomplete: bool = True


@dataclass(frozen=True)
class SessionFinished:
    """The PTY child exited."""

    returncode: int
    log_path: Path
    failed_step: str | None = None
    kind: SessionEventKind = SessionEventKind.FINISHED
    cancelled: bool = False
    transcript_incomplete: bool = False


SessionEvent = (
    OutputChunk
    | StepEvent
    | RetryPrompt
    | AskpassRequest
    | AskpassExpired
    | PromptRequest
    | PromptCleared
    | TranscriptWarning
    | SessionFinished
)


@dataclass
class _ParserState:
    """Incremental parser state for topgrade output."""

    buffer: str = ""
    current_step: str | None = None
    steps: dict[str, StepStatus] = field(default_factory=dict)
    in_summary: bool = False
    diagnostic_step: str | None = None
    failure_reasons: dict[str, str] = field(default_factory=dict)
    reported_steps: set[str] = field(default_factory=set)
    last_prompt: str | None = None
    prompt_source: str = ""  # dangling text that raised last_prompt
    last_line: str = ""

    @property
    def failed_step(self) -> str | None:
        return next(
            (name for name in reversed(self.failure_reasons) if self.steps[name] == "failed"),
            None,
        )

    @property
    def failed_steps(self) -> tuple[str, ...]:
        return tuple(name for name, status in self.steps.items() if status == "failed")


def strip_ansi(text: str) -> str:
    """Remove ANSI/OSC escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def default_runs_dir() -> Path:
    """Return the XDG data directory used for run transcripts."""
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data_home / "uptray" / "runs"


def list_run_logs(runs_dir: Path | None = None) -> list[Path]:
    """Return run log paths newest-first."""
    directory = runs_dir if runs_dir is not None else default_runs_dir()
    if not directory.is_dir():
        return []
    logs: list[tuple[float, Path]] = []
    for path in directory.glob("*.log"):
        try:
            info = path.stat()
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode):
            logs.append((info.st_mtime, path))
    return [path for _, path in sorted(logs, reverse=True)]


def available_agents() -> list[str]:
    """Return agent names whose CLI is present on PATH."""
    import shutil

    return [name for name, cmd in _AGENT_COMMANDS.items() if shutil.which(cmd[0])]


def build_diagnose_prompt(
    *,
    returncode: int | None,
    failed_step: str | None,
    log_path: Path,
    reason: str | None = None,
) -> str:
    """Build the seed prompt for an embedded diagnose agent session."""
    step = failed_step or "unknown step"
    code = "unknown" if returncode is None else str(returncode)
    because = f"Reason reported by topgrade: {reason}. " if reason else ""
    return (
        "A topgrade system update failed inside uptray. "
        f"Failed step: {step}. Exit code: {code}. {because}"
        f"Full transcript: {log_path}. "
        "Please diagnose the failure and propose the safest fix."
    )


def build_agent_command(agent: str, prompt: str) -> list[str]:
    """Return argv for launching *agent* with *prompt* as the initial message."""
    if agent not in _AGENT_COMMANDS:
        raise ValueError(f"unknown agent: {agent}")
    return [*_AGENT_COMMANDS[agent], prompt]


def parse_topgrade_chunk(state: _ParserState, chunk: str) -> list[SessionEvent]:
    """Feed decoded text into *state* and return newly recognized events."""
    events: list[SessionEvent] = []
    # One split, not a slice per line: whole transcripts are parsed for history.
    # CR redraws are complete display updates too. CRLF (even when split
    # across reads) must not concatenate successive percentages into one line.
    *lines, state.buffer = re.split(r"\r\n?|\n", state.buffer + chunk)
    for line in lines:
        events.extend(_parse_line(state, line))

    # Retry prompts often appear without a trailing newline.
    if state.buffer and _RETRY_RE.search(strip_ansi(state.buffer)):
        events.extend(_parse_line(state, state.buffer))
        state.buffer = ""
        return events
    # Prompts frequently dangle without a newline while awaiting input. Yes/no
    # brackets are unambiguous; menu-style ones wait for parse_idle, since a read
    # can end mid-line right after "==>" (makepkg) or "[core/extra]".
    if state.buffer and state.diagnostic_step is None:
        stripped = strip_ansi(state.buffer).strip()
        question, free_text = _dangling_prompt(state, stripped)
        if question is not None and not free_text:
            events.extend(_raise_prompt(state, question, stripped, free_text=False))
        elif state.last_prompt is not None and stripped and stripped != state.prompt_source:
            # New output after the prompt: it was answered (PTY echo) or superseded.
            state.last_prompt = None
            events.append(PromptCleared())
        # Some commands prefix redraws with CR and leave the new percentage
        # unterminated. Publish a complete percentage without consuming the
        # partial line: later chunks may still contain its suffix or a prompt.
        if (
            state.current_step is not None
            and state.steps.get(state.current_step) == "running"
            and question is None
            and stripped != state.last_line
            and re.search(r"\d+(?:\.\d+)?\s*%", stripped)
        ):
            state.last_line = stripped
            events.append(StepEvent(
                name=state.current_step, status="running", latest_line=stripped,
            ))
    return events


def finish_topgrade_parse(state: _ParserState) -> list[SessionEvent]:
    """Consume the final line, which may have no line break."""
    events = _parse_line(state, state.buffer)
    state.buffer = ""
    return events


def parse_idle(state: _ParserState) -> list[SessionEvent]:
    """Output has paused: a dangling line that looks like a prompt is one."""
    if state.diagnostic_step is not None:
        return []
    stripped = strip_ansi(state.buffer).strip()
    question, free_text = _dangling_prompt(state, stripped)
    if question is None:
        return []
    return _raise_prompt(state, question, stripped, free_text=free_text)


def _raise_prompt(
    state: _ParserState, question: str, source: str, *, free_text: bool
) -> list[SessionEvent]:
    if question == state.last_prompt:
        return []
    state.last_prompt = question
    state.prompt_source = source
    return [PromptRequest(question=question, free_text=free_text)]


def _dangling_prompt(state: _ParserState, text: str) -> tuple[str | None, bool]:
    """Return (question, free_text) when *text* is a prompt awaiting input."""
    if not text:
        return None, False
    match = _PROMPT_RE.search(text)
    if match is not None:  # yes/no wins over menu syntax
        return (None, False) if _prompt_answer_tail(text, match) else (text, False)
    if _MENU_RE.search(text):
        # A bare "==>" (paru/yay) only makes sense with the menu line above it.
        if text == "==>" and state.last_line:
            return state.last_line, True
        return text, True
    return None, False


def _prompt_answer_tail(line: str, match: re.Match[str]) -> str:
    """Return meaningful text after a prompt bracket (an echoed answer).

    Trailing prompt decoration (a lone colon) does not count as an answer.
    """
    return line[match.end() :].strip().rstrip(":").strip()


def _parse_line(state: _ParserState, raw_line: str) -> list[SessionEvent]:
    line = strip_ansi(raw_line).strip()
    if not line:
        return []
    state.last_line = line

    events: list[SessionEvent] = []
    if state.last_prompt is not None:
        # Output resumed after a prompt: it was answered or superseded.
        state.last_prompt = None
        events.append(PromptCleared())

    retry = _RETRY_RE.search(line)
    if retry is not None:
        # The retry prompt can share a line with the tail of an error report.
        step = state.diagnostic_step or state.current_step
        if retry.start():
            events.extend(_parse_line(state, line[:retry.start()]))
            step = state.diagnostic_step or step
        state.diagnostic_step = None
        events.append(RetryPrompt(step_name=step))
        return events

    # Separators win over prompts: a prompt that was never answered can share
    # a line with the next step's header ("...[Y/n]: ―― 23:08:07 - pacdiff ――").
    separator = _SEPARATOR_BOX_RE.search(line) or _SEPARATOR_PLAIN_RE.search(line)
    if separator is not None:
        name = separator.group("name").strip()
        state.diagnostic_step = None
        state.in_summary = name == "Summary"
        if (
            state.current_step
            and state.current_step != name
            and state.steps.get(state.current_step) == "running"
        ):
            # Topgrade may wait until the Summary to report a failure or skip.
            events.append(StepEvent(name=state.current_step, status="ended"))
            state.steps[state.current_step] = "ended"
        if state.in_summary:
            state.current_step = None
            return events
        state.current_step = name
        state.steps[name] = "running"
        state.reported_steps.discard(name)
        events.append(StepEvent(name=name, status="running", latest_line=line))
        return events

    result = _RESULT_RE.match(line)
    if result is not None and (
        state.in_summary
        or (not raw_line[:1].isspace() and result.group("name").strip() in state.steps)
    ):
        state.diagnostic_step = None
        events.append(_parse_result(state, result, line))
        return events

    if state.diagnostic_step is not None:
        # An error chain can itself include text like "command failed:".
        name = state.diagnostic_step
        previous = state.failure_reasons[name]
        reason = f"{previous}\n{line}".lstrip()[:_MAX_REASON_LENGTH]
        if reason != previous:
            state.failure_reasons[name] = reason
            events.append(StepEvent(name=name, status="failed", latest_line=line, reason=reason))
        return events

    failure = _FAILURE_RE.match(line)
    # Child commands print "X failed: Y" too (gpg, curl); only a known step starts a report.
    if (
        failure is not None
        and not raw_line[:1].isspace()
        and failure.group("name").strip() in state.steps
    ):
        name = failure.group("name").strip()
        state.diagnostic_step = name
        state.steps[name] = "failed"
        state.reported_steps.discard(name)
        state.failure_reasons.pop(name, None)
        reason = failure.group("reason")[:_MAX_REASON_LENGTH]
        state.failure_reasons[name] = reason
        events.append(StepEvent(
            name=name, status="failed", latest_line=line, reason=reason or None,
        ))
        return events

    prompt_match = _PROMPT_RE.search(line)
    if prompt_match is not None:
        state.diagnostic_step = None
        if _prompt_answer_tail(line, prompt_match):
            # Answer echoed on the prompt line: consumed, not a new question.
            return events
        if line != state.last_prompt:
            state.last_prompt = line
            events.append(PromptRequest(question=line))
        return events

    if state.current_step is not None and state.steps.get(state.current_step) == "running":
        events.append(
            StepEvent(name=state.current_step, status="running", latest_line=line)
        )
    return events


def _parse_result(state: _ParserState, result: re.Match[str], line: str) -> StepEvent:
    name = result.group("name").strip()
    status_token = result.group("status")
    reason = (result.group("reason") or "").strip()
    status: StepStatus
    if status_token == "FAILED":
        status = "failed"
        diagnostic = state.failure_reasons.pop(name, "")
        reason = diagnostic or reason
        state.failure_reasons[name] = reason
    else:
        status = "succeeded" if status_token == "OK" else "skipped"
        state.failure_reasons.pop(name, None)
    state.steps[name] = status
    state.reported_steps.add(name)
    if state.current_step == name:
        state.current_step = None
    return StepEvent(name=name, status=status, latest_line=line, reason=reason or None)


class TopgradeSession:
    """Run a command on a PTY, tee output to a log, and emit parsed events."""

    def __init__(
        self,
        command: list[str],
        *,
        log_path: Path | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        runs_dir: Path | None = None,
        enable_askpass: bool = True,
        on_event: Callable[[SessionEvent], None] | None = None,
        extra_args: Sequence[str] = (),
    ) -> None:
        if not command:
            raise ValueError("command must be non-empty")
        self._command = list(command)
        self._cwd = cwd
        self._env = env
        self._enable_askpass = enable_askpass
        self._on_event = on_event
        self._scope = describe_run_scope(extra_args)
        if runs_dir is None:
            runs_dir = (
                log_path.parent if log_path is not None and log_path.suffix == ".log"
                else default_runs_dir()
            )
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._runs_dir = runs_dir
        generated_log = runs_dir / f"{stamp}-{os.getpid()}-{time.time_ns()}.log"
        self._log_path = log_path if log_path is not None else generated_log
        self._metadata_path = metadata_path(
            self._log_path
            if self._log_path.parent == runs_dir and self._log_path.suffix == ".log"
            else generated_log
        )

        self._master_fd: int | None = None
        self._pid: int | None = None
        self._proc: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._askpass_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._parser = _ParserState()
        self._parsing_enabled = True
        self._returncode: int | None = None
        self._cancelled = False
        self._waiting_retry = False
        self._transcript_incomplete = False
        self._log_file: BinaryIO | None = None
        self._started_at: datetime | None = None
        self._askpass_sock: Path | None = None
        self._askpass_server: socket.socket | None = None
        self._askpass_helpers: tempfile.TemporaryDirectory[str] | None = None
        self._askpass_lock = threading.Lock()
        self._askpass_next_id = 1
        self._askpass_replies: dict[int, queue.Queue[str | None]] = {}
        self._size = (24, 80)

    @property
    def log_path(self) -> Path:
        """Path of the transcript for this run."""
        return self._log_path

    @property
    def returncode(self) -> int | None:
        """Child exit status once finished, else None."""
        return self._returncode

    @property
    def failed_step(self) -> str | None:
        """Name of the last failed step, if any."""
        return self._parser.failed_step

    @property
    def running(self) -> bool:
        """True while the reader thread is alive."""
        return self._reader is not None and self._reader.is_alive()

    def start(self) -> None:
        """Spawn the child on a PTY and begin streaming."""
        if self._started_at is not None:
            raise RuntimeError("session already started")
        self._started_at = datetime.now(timezone.utc)
        _mkdir_private(self._runs_dir)
        if not self._log_path.parent.exists():
            _mkdir_private(self._log_path.parent)
        self._log_file = _open_private_append(self._log_path)
        try:
            self._spawn()
            self._reader = threading.Thread(
                target=self._read_loop,
                name="topgrade-session-reader",
                daemon=True,
            )
            self._reader.start()
        except BaseException as exc:
            self._stop.set()
            self._shutdown_askpass()
            if self._pid is not None:
                self._signal_child(self._pid, signal.SIGKILL)
                self._wait_for_exit()
                self._pid = None
            self._close_pty()
            self._close_log()
            self._reader = None
            if isinstance(exc, RuntimeError):
                raise OSError(str(exc)) from exc
            raise

    def _spawn(self) -> None:
        env = os.environ.copy()
        if self._env:
            env.update(self._env)
        env.setdefault("TERM", "xterm-256color")
        # Prefer our askpass path so sudo prompts stay inside the GUI.
        # sudo only uses SUDO_ASKPASS when invoked with -A, so put a PATH wrapper
        # ahead of the real sudo that always adds -A.
        # openpty + Popen avoids forkpty() in this multi-threaded process.
        # The child claims the slave as its controlling terminal after setsid,
        # which Popen's start_new_session does not do on its own.
        if shutil.which(self._command[0], path=env.get("PATH")) is None and not Path(
            self._command[0]
        ).is_file():
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), self._command[0])
        try:
            if self._enable_askpass:
                self._start_askpass_server()
                if self._askpass_sock is not None and self._askpass_helpers is not None:
                    helper_dir = Path(self._askpass_helpers.name)
                    env["SUDO_ASKPASS"] = _askpass_launcher(helper_dir)
                    env["UPTRAY_ASKPASS_SOCK"] = str(self._askpass_sock)
                    sudo_bin = shutil.which("sudo", path=env.get("PATH"))
                    if sudo_bin is not None:
                        wrapper_dir = _sudo_askpass_wrapper_dir(sudo_bin, helper_dir)
                        env["PATH"] = f"{wrapper_dir}{os.pathsep}{env.get('PATH', '')}"
            master_fd, slave_fd = pty.openpty()
            try:
                _set_pty_size(slave_fd, *self._size)
                proc = subprocess.Popen(
                    [sys.executable, "-c", _ACQUIRE_CONTROLLING_TTY, *self._command],
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    cwd=self._cwd,
                    env=env,
                    start_new_session=True,
                    close_fds=True,
                )
            except Exception:
                os.close(master_fd)
                os.close(slave_fd)
                raise
            os.close(slave_fd)
        except Exception:
            self._shutdown_askpass()
            raise
        self._proc = proc
        self._pid = proc.pid
        self._master_fd = master_fd

    def write(self, data: str | bytes) -> None:
        """Write bytes to the PTY (user input / retry answers)."""
        payload = data if isinstance(data, bytes) else data.encode()
        with self._process_lock:
            if self._master_fd is None:
                return
            with contextlib.suppress(OSError):
                written = os.write(self._master_fd, payload)
                if self._waiting_retry and written:
                    key = payload[:1].lower()
                    if key == b"q":
                        self._cancelled = True
                    if key in {b"q", b"y", b"n", b"s", b"\n", b"\r"}:
                        self._waiting_retry = False

    def resize(self, rows: int, cols: int) -> None:
        """Update the PTY window size."""
        self._size = (min(65535, max(1, rows)), min(65535, max(1, cols)))
        with self._process_lock:
            if self._master_fd is not None:
                winsize = struct.pack("HHHH", *self._size, 0, 0)
                with contextlib.suppress(OSError):
                    fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)

    def reply_askpass(self, request_id: int, password: str | None) -> None:
        """Deliver an askpass reply collected by the GUI."""
        with self._askpass_lock:
            if self._stop.is_set():
                return
            reply_queue = self._askpass_replies.get(request_id)
            if reply_queue is not None:
                with contextlib.suppress(queue.Full):
                    reply_queue.put_nowait(password)

    def cancel(self) -> None:
        """Terminate the process group: SIGTERM, then SIGKILL.

        Wait on the whole group, not just the session leader — a child that
        ignores SIGTERM can outlive the leader and must still get SIGKILL.
        """
        pgid = self._pid
        if pgid is None:
            return
        if self._wait_nonblocking() is not None and not self._process_group_alive(pgid):
            return
        with self._process_lock:
            if self._pid != pgid:
                return
            self._cancelled = True
        self._signal_child(pgid, signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            self._wait_nonblocking()
            if not self._process_group_alive(pgid):
                return
            time.sleep(0.05)
        self._signal_child(pgid, signal.SIGKILL)
        # Brief settle so callers do not race a still-dying worker.
        settle = time.monotonic() + 0.5
        while time.monotonic() < settle:
            self._wait_nonblocking()
            if not self._process_group_alive(pgid):
                return
            time.sleep(0.05)

    def _signal_child(self, pgid: int, sig: signal.Signals) -> None:
        with self._process_lock:
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                # The child may be between fork and setsid. Until it is reaped
                # its PID still identifies the same process.
                if self._returncode is None:
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.kill(pgid, sig)
            except PermissionError:
                pass

    def wait(self, timeout: float | None = None) -> int | None:
        """Block until the reader finishes. Returns the exit code when known."""
        if self._reader is not None:
            self._reader.join(timeout=timeout)
        return self._returncode

    def close(self) -> None:
        """Stop the child if it is still running, then wait up to 2 s for its output.

        This ends the run: its process group gets SIGTERM, then SIGKILL after
        3 s (see :meth:`cancel`). Do not call it to merely detach from a run.
        """
        self.cancel()
        if self._reader is not None and self._reader is not threading.current_thread():
            self.wait(timeout=2)

    def _emit(self, event: SessionEvent) -> None:
        if isinstance(event, RetryPrompt):
            with self._process_lock:
                self._waiting_retry = True
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                _log.exception("Session event callback failed")

    def _read_loop(self) -> None:
        assert self._master_fd is not None
        assert self._started_at is not None
        try:
            self._read_pty(self._master_fd)
        except OSError as exc:
            self._warn_transcript(f"Lost the terminal connection: {exc}")
            _log.exception("PTY reader failed")
        finally:
            self._close_pty()
            self._close_log()
            self._stop.set()
            self._shutdown_askpass()
        code = self._wait_for_exit()
        with self._process_lock:
            self._pid = None
            cancelled = self._cancelled
        record = RunMetadata(
            path=self._log_path,
            scope=self._scope,
            started=self._started_at,
            finished=datetime.now(timezone.utc),
            returncode=code,
            cancelled=cancelled,
            transcript_incomplete=self._transcript_incomplete,
            failed_steps=self._parser.failed_steps,
        )
        try:
            save_metadata(self._metadata_path, record)
        except OSError as exc:
            self._emit(TranscriptWarning(
                f"Could not save the run outcome: {exc}", transcript_incomplete=False,
            ))
        self._emit(SessionFinished(
            returncode=code,
            log_path=self._log_path,
            failed_step=self._parser.failed_step,
            cancelled=cancelled,
            transcript_incomplete=self._transcript_incomplete,
        ))

    def _read_pty(self, master_fd: int) -> None:
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        poller = select.poll()
        poller.register(master_fd, select.POLLIN)
        while True:
            if not poller.poll(200):
                self._emit_parsed(parse_idle, self._parser)
                if self._wait_nonblocking() is not None and not poller.poll(0):
                    break
                continue
            try:
                data = os.read(master_fd, 4096)
            except OSError as exc:
                if exc.errno == errno.EIO:  # Linux signals EOF on a PTY this way.
                    break
                raise
            if not data:
                break
            self._write_log(data)
            self._emit_text(decoder.decode(data))
        self._emit_text(decoder.decode(b"", final=True))
        self._emit_parsed(finish_topgrade_parse, self._parser)

    def _emit_text(self, text: str) -> None:
        if text:
            self._emit(OutputChunk(text=text))
            self._emit_parsed(parse_topgrade_chunk, self._parser, text)

    def _emit_parsed(self, parse: Callable[..., list[SessionEvent]], *args: object) -> None:
        if not self._parsing_enabled:
            return
        try:
            events = parse(*args)
        except Exception:
            self._parsing_enabled = False
            _log.exception("Structured terminal output is unavailable. Raw output is still active.")
            self._emit(TranscriptWarning(
                "Could not interpret the update output. Use Verbose to follow the run.",
                transcript_incomplete=False,
            ))
            return
        for event in events:
            self._emit(event)

    def _warn_transcript(self, message: str) -> None:
        if not self._transcript_incomplete:
            self._transcript_incomplete = True
            self._emit(TranscriptWarning(message))

    def _write_log(self, data: bytes) -> None:
        if self._log_file is None:
            return
        try:
            if self._log_file.write(data) != len(data):
                raise OSError("short transcript write")
            self._log_file.flush()
        except OSError as exc:
            self._warn_transcript(f"Transcript is incomplete: {exc}")
            self._close_log()

    def _close_log(self) -> None:
        log_file = self._log_file
        self._log_file = None
        if log_file is not None:
            try:
                log_file.close()
            except OSError as exc:
                self._warn_transcript(f"Transcript is incomplete: {exc}")

    def _close_pty(self) -> None:
        with self._process_lock:
            if self._master_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(self._master_fd)
                self._master_fd = None

    def _wait_nonblocking(self) -> int | None:
        # Popen reaps the child. A second waitpid makes poll() see ECHILD.
        if self._returncode is not None:
            return self._returncode
        proc = self._proc
        if proc is None:
            return None
        code = proc.poll()
        if code is None:
            return None
        self._returncode = _normalize_returncode(code)
        return self._returncode

    def _wait_for_exit(self) -> int:
        # Keep the process lock available to cancel even when a child has
        # closed its own terminal but continues running.
        while (code := self._wait_nonblocking()) is None:
            time.sleep(0.05)
        return code

    @staticmethod
    def _process_group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _helper_directory(self) -> Path:
        """Private directory for this session's askpass socket and sudo helper."""
        if self._askpass_helpers is None:
            self._askpass_helpers = tempfile.TemporaryDirectory(
                prefix="uptray-", dir=_private_dir()
            )
        return Path(self._askpass_helpers.name)

    def _start_askpass_server(self) -> None:
        sock_path = self._helper_directory() / "askpass.sock"
        with contextlib.suppress(FileNotFoundError):
            sock_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._askpass_server = server
        server.bind(str(sock_path))
        self._askpass_sock = sock_path
        server.listen(5)
        server.settimeout(0.5)
        self._askpass_thread = threading.Thread(
            target=self._askpass_loop,
            name="topgrade-askpass",
            daemon=True,
        )
        self._askpass_thread.start()

    def _askpass_loop(self) -> None:
        server = self._askpass_server
        if server is None:
            return
        while not self._stop.is_set():
            try:
                conn, _addr = server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_askpass_conn,
                args=(conn,),
                daemon=True,
            ).start()

    def _handle_askpass_conn(self, conn: socket.socket) -> None:
        with conn:
            try:
                conn.settimeout(1)
                raw = conn.recv(4096).decode(errors="replace").strip()
            except OSError:
                return
            prompt = raw or "Password:"
            with self._askpass_lock:
                if self._stop.is_set():
                    return
                request_id = self._askpass_next_id
                self._askpass_next_id += 1
                reply_queue: queue.Queue[str | None] = queue.Queue(maxsize=1)
                self._askpass_replies[request_id] = reply_queue
            self._emit(AskpassRequest(prompt=prompt, request_id=request_id))
            expired = False
            try:
                password = reply_queue.get(timeout=_ASKPASS_TIMEOUT_S)
            except queue.Empty:
                with self._askpass_lock:
                    self._askpass_replies.pop(request_id, None)
                    # A reply already queued at the timeout boundary still wins.
                    try:
                        password = reply_queue.get_nowait()
                    except queue.Empty:
                        password = None
                        expired = not self._stop.is_set()
            else:
                with self._askpass_lock:
                    self._askpass_replies.pop(request_id, None)
            if expired:
                self._emit(AskpassExpired(request_id=request_id))
            if password is None or self._stop.is_set():
                return
            with contextlib.suppress(OSError):
                conn.sendall(f"{password}\n".encode())

    def _shutdown_askpass(self) -> None:
        with self._askpass_lock:
            for reply_queue in self._askpass_replies.values():
                with contextlib.suppress(queue.Full):
                    reply_queue.put_nowait(None)
        server = self._askpass_server
        self._askpass_server = None
        if server is not None:
            with contextlib.suppress(OSError):
                server.close()
        if self._askpass_sock is not None:
            with contextlib.suppress(FileNotFoundError, OSError):
                self._askpass_sock.unlink()
            self._askpass_sock = None
        if self._askpass_helpers is not None:
            with contextlib.suppress(OSError):
                self._askpass_helpers.cleanup()
            self._askpass_helpers = None


def _normalize_returncode(code: int) -> int:
    """Match the historical 128+signal convention for signal deaths."""
    if code < 0:
        return 128 + (-code)
    return code


# Runs after start_new_session's setsid(). Popen does not call TIOCSCTTY, so
# without this the child has no controlling terminal: /dev/tty fails, and
# resize and Ctrl-C never become SIGWINCH and SIGINT.
_ACQUIRE_CONTROLLING_TTY = (
    "import fcntl,os,sys,termios\n"
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
    "try:\n"
    "    os.execvp(sys.argv[1], sys.argv[1:])\n"
    "except Exception as exc:\n"
    "    sys.stderr.write('failed to exec %r: %s\\n' % (sys.argv[1], exc))\n"
    "    raise SystemExit(127)\n"
)
_LEGACY_ASKPASS = re.compile(r"uptray-askpass-(\d+)\.sh$")
_LEGACY_SUDO_WRAP = re.compile(r"uptray-sudo-wrap-(\d+)$")


def _set_pty_size(fd: int, rows: int, cols: int) -> None:
    winsize = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _mkdir_private(path: Path) -> None:
    """Create a directory and any missing parents, readable only by the owner."""
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        parent = current.parent
        if parent == current:
            break
        current = parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700, exist_ok=True)
        _restrict(directory, 0o700)
    if not missing and path.is_dir():
        _restrict(path, 0o700)


def _restrict(path: Path, mode: int) -> None:
    try:
        current = path.stat().st_mode
    except OSError:
        return
    if current & 0o077:
        with contextlib.suppress(OSError):
            path.chmod(mode)


def _open_private_append(path: Path) -> BinaryIO:
    """Open a transcript for append, creating it as mode 0600."""
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        if os.fstat(fd).st_mode & 0o077:
            os.fchmod(fd, 0o600)
    except OSError:
        pass
    return os.fdopen(fd, "ab")


def _write_private_executable(path: Path, text: str) -> None:
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o700)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)


def private_runtime_dir() -> Path | None:
    """$XDG_RUNTIME_DIR if it is a directory only this user can reach, else None."""
    raw = os.environ.get("XDG_RUNTIME_DIR")
    if not raw:
        return None
    try:
        info = os.stat(raw)
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        return None
    return Path(raw)


@functools.cache
def _private_dir() -> Path:
    """Directory for the askpass socket and sudo helpers that no other user can touch.

    Never a predictable /tmp path: another local user could create it first and
    plant a fake ``sudo`` that captures the password.
    """
    runtime = private_runtime_dir()
    if runtime is not None:
        _sweep_legacy_helpers(runtime)
        return runtime
    path = Path(tempfile.mkdtemp(prefix="uptray-"))  # 0700, unpredictable name
    atexit.register(shutil.rmtree, path, True)
    return path


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _sweep_legacy_helpers(directory: Path) -> None:
    """Remove askpass files left in the runtime dir by older Uptray versions."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return
    for entry in entries:
        match = _LEGACY_ASKPASS.match(entry.name) or _LEGACY_SUDO_WRAP.match(entry.name)
        if match is None or _pid_alive(int(match.group(1))):
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
        except OSError:
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            with contextlib.suppress(OSError):
                entry.unlink()


def _askpass_launcher(directory: Path) -> str:
    """Write a tiny SUDO_ASKPASS script that talks to our Unix socket."""
    import sys

    script = (
        "import os,socket,sys;"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
        "s.connect(os.environ['UPTRAY_ASKPASS_SOCK']);"
        "prompt=sys.argv[1] if len(sys.argv)>1 else 'Password:';"
        "s.sendall(prompt.encode());"
        "sys.stdout.write(s.recv(4096).decode())"
    )
    helper = directory / "askpass.sh"
    command = f"exec {shlex.quote(sys.executable)} -c {shlex.quote(script)} \"$@\""
    _write_private_executable(helper, f"#!/bin/sh\n{command}\n")
    return str(helper)


def _sudo_askpass_wrapper_dir(real_sudo: str, directory: Path) -> str:
    """Return a PATH directory containing a ``sudo`` that always passes ``-A``."""
    wrapper_dir = directory / "sudo-wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    _restrict(wrapper_dir, 0o700)
    _write_private_executable(
        wrapper_dir / "sudo",
        "#!/bin/sh\n"
        # Avoid recursing into this wrapper if PATH still points here.
        f"exec {shlex.quote(real_sudo)} -A \"$@\"\n",
    )
    return str(wrapper_dir)
