"""PTY-backed topgrade session with log capture and output parsing.

Qt-free so the session can be unit-tested with a fake command.
"""

from __future__ import annotations

import codecs
import contextlib
import errno
import os
import pty
import queue
import re
import select
import shutil
import signal
import socket
import struct
import termios
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

__all__ = [
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
    "available_agents",
    "build_agent_command",
    "build_diagnose_prompt",
    "default_runs_dir",
    "list_run_logs",
    "parse_topgrade_chunk",
    "strip_ansi",
]

RunMode = Literal["simple", "verbose"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]

RETRY_PROMPT = "Retry? (y)es/(N)o/(s)hell/(q)uit"

_ANSI_RE = re.compile(
    r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[()][0-9A-Za-z])"
)
_SEPARATOR_BOX_RE = re.compile(
    r"──\s+(?:(\d{2}:\d{2}:\d{2})\s+-\s+)?(.+?)\s+─{2,}\s*$"
)
_SEPARATOR_PLAIN_RE = re.compile(r"――\s+(.+?)\s+――\s*$")
_RESULT_RE = re.compile(
    r"^(?P<name>.+?):\s+(?P<status>OK|FAILED|IGNORED|SKIPPED)(?::\s*(?P<reason>.*))?$"
)
_RETRY_RE = re.compile(re.escape(RETRY_PROMPT))
# Interactive yes/no prompts use the [Y/n] bracket convention (topgrade child
# commands: paru, pacdiff, maintainer scripts, ...). Anything between the
# brackets may decorate y/n (e.g. [yes/no], [Y/n/?]).
_PROMPT_RE = re.compile(r"\[[^\]]*[Yy][^\]]*/[^\]]*[Nn][^\]]*\]")
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
class PromptRequest:
    """The running command asked the user a yes/no question.

    Detected from the standard ``[Y/n]``-style bracket convention in the
    PTY output. One event per unique question until output resumes.
    """

    question: str
    kind: SessionEventKind = SessionEventKind.PROMPT


@dataclass(frozen=True)
class PromptCleared:
    """A previously announced prompt was answered or superseded."""

    kind: SessionEventKind = SessionEventKind.PROMPT


@dataclass(frozen=True)
class SessionFinished:
    """The PTY child exited."""

    returncode: int
    log_path: Path
    failed_step: str | None = None
    kind: SessionEventKind = SessionEventKind.FINISHED


SessionEvent = (
    OutputChunk
    | StepEvent
    | RetryPrompt
    | AskpassRequest
    | PromptRequest
    | PromptCleared
    | SessionFinished
)


@dataclass
class _ParserState:
    """Incremental parser state for topgrade output."""

    buffer: str = ""
    current_step: str | None = None
    failed_step: str | None = None
    steps: dict[str, StepStatus] = field(default_factory=dict)
    last_prompt: str | None = None


def strip_ansi(text: str) -> str:
    """Remove ANSI/OSC escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


def default_runs_dir() -> Path:
    """Return the XDG data directory used for run transcripts."""
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data_home / "topgrade-update" / "runs"


def list_run_logs(runs_dir: Path | None = None) -> list[Path]:
    """Return run log paths newest-first."""
    directory = runs_dir if runs_dir is not None else default_runs_dir()
    if not directory.is_dir():
        return []
    logs = [path for path in directory.glob("*.log") if path.is_file()]
    return sorted(logs, key=lambda path: path.stat().st_mtime, reverse=True)


def available_agents() -> list[str]:
    """Return agent names whose CLI is present on PATH."""
    import shutil

    return [name for name, cmd in _AGENT_COMMANDS.items() if shutil.which(cmd[0])]


def build_diagnose_prompt(
    *,
    returncode: int | None,
    failed_step: str | None,
    log_path: Path,
) -> str:
    """Build the seed prompt for an embedded diagnose agent session."""
    step = failed_step or "unknown step"
    code = "unknown" if returncode is None else str(returncode)
    return (
        "A topgrade system update failed inside topgrade-update. "
        f"Failed step: {step}. Exit code: {code}. "
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
    state.buffer += chunk
    while True:
        newline = state.buffer.find("\n")
        if newline < 0:
            break
        line = state.buffer[:newline]
        state.buffer = state.buffer[newline + 1 :]
        events.extend(_parse_line(state, line))

    # Retry prompts often appear without a trailing newline.
    if state.buffer and _RETRY_RE.search(strip_ansi(state.buffer)):
        events.append(RetryPrompt(step_name=state.current_step))
        state.buffer = ""
        return events
    # Yes/no prompts frequently dangle without a newline while awaiting input.
    if state.buffer:
        stripped = strip_ansi(state.buffer).strip()
        match = _PROMPT_RE.search(stripped) if stripped else None
        if match is not None and not _prompt_answer_tail(stripped, match):
            question = stripped
            if question != state.last_prompt:
                state.last_prompt = question
                events.append(PromptRequest(question=question))
        elif state.last_prompt is not None and stripped:
            # Non-empty output that is not a dangling prompt: the pending
            # prompt was answered (PTY echo) or superseded.
            state.last_prompt = None
            events.append(PromptCleared())
    return events


def _prompt_answer_tail(line: str, match: re.Match[str]) -> str:
    """Return meaningful text after a prompt bracket (an echoed answer).

    Trailing prompt decoration (a lone colon) does not count as an answer.
    """
    return line[match.end() :].strip().rstrip(":").strip()


def _parse_line(state: _ParserState, raw_line: str) -> list[SessionEvent]:
    line = strip_ansi(raw_line).strip()
    if not line:
        return []

    events: list[SessionEvent] = []
    if _RETRY_RE.search(line):
        events.append(RetryPrompt(step_name=state.current_step))
        return events

    if state.last_prompt is not None:
        # Output resumed after a prompt: it was answered or superseded.
        state.last_prompt = None
        events.append(PromptCleared())

    prompt_match = _PROMPT_RE.search(line)
    if prompt_match is not None:
        if _prompt_answer_tail(line, prompt_match):
            # Answer echoed on the prompt line: consumed, not a new question.
            return events
        if line != state.last_prompt:
            state.last_prompt = line
            events.append(PromptRequest(question=line))
        return events

    separator = _SEPARATOR_BOX_RE.search(line) or _SEPARATOR_PLAIN_RE.search(line)
    if separator is not None:
        name = separator.group(separator.lastindex or 1).strip()
        if state.current_step and state.steps.get(state.current_step) == "running":
            events.append(
                StepEvent(name=state.current_step, status="succeeded", latest_line=line)
            )
            state.steps[state.current_step] = "succeeded"
        state.current_step = name
        state.steps[name] = "running"
        events.append(StepEvent(name=name, status="running", latest_line=line))
        return events

    result = _RESULT_RE.match(line)
    if result is not None:
        name = result.group("name").strip()
        status_token = result.group("status")
        reason = (result.group("reason") or "").strip() or None
        status: StepStatus
        if status_token == "OK":
            status = "succeeded"
        elif status_token == "FAILED":
            status = "failed"
            state.failed_step = name
        else:
            status = "skipped"
        state.steps[name] = status
        if state.current_step == name:
            state.current_step = None
        events.append(
            StepEvent(name=name, status=status, latest_line=line, reason=reason)
        )
        return events

    if state.current_step is not None:
        events.append(
            StepEvent(name=state.current_step, status="running", latest_line=line)
        )
    return events


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
    ) -> None:
        if not command:
            raise ValueError("command must be non-empty")
        self._command = list(command)
        self._cwd = cwd
        self._env = env
        self._enable_askpass = enable_askpass
        self._on_event = on_event
        self._runs_dir = runs_dir if runs_dir is not None else default_runs_dir()
        if log_path is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            self._log_path = self._runs_dir / f"{stamp}-{os.getpid()}-{time.time_ns()}.log"
        else:
            self._log_path = log_path

        self._master_fd: int | None = None
        self._pid: int | None = None
        self._reader: threading.Thread | None = None
        self._askpass_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._parser = _ParserState()
        self._returncode: int | None = None
        self._askpass_sock: Path | None = None
        self._askpass_server: socket.socket | None = None
        self._askpass_lock = threading.Lock()
        self._askpass_next_id = 1
        self._askpass_replies: dict[int, queue.Queue[str | None]] = {}
        self._started = False

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
        if self._started:
            raise RuntimeError("session already started")
        self._started = True
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        if self._env:
            env.update(self._env)
        env.setdefault("TERM", "xterm-256color")
        # Prefer our askpass path so sudo prompts stay inside the GUI.
        # sudo only uses SUDO_ASKPASS when invoked with -A, so put a PATH wrapper
        # ahead of the real sudo that always adds -A.
        if self._enable_askpass:
            self._start_askpass_server()
            if self._askpass_sock is not None:
                env["SUDO_ASKPASS"] = _askpass_launcher()
                env["TOPGRADE_UPDATE_ASKPASS_SOCK"] = str(self._askpass_sock)
                sudo_bin = shutil.which("sudo", path=env.get("PATH"))
                if sudo_bin is not None:
                    wrapper_dir = _sudo_askpass_wrapper_dir(sudo_bin)
                    env["PATH"] = f"{wrapper_dir}{os.pathsep}{env.get('PATH', '')}"

        pid, master_fd = pty.fork()
        if pid == 0:  # child
            child_env = env
            try:
                if self._cwd is not None:
                    os.chdir(self._cwd)
                os.execvpe(self._command[0], self._command, child_env)
            except OSError as exc:
                message = f"failed to exec {self._command[0]!r}: {exc}\n"
                os.write(2, message.encode())
                os._exit(127)

        self._pid = pid
        self._master_fd = master_fd
        # pty.fork() already makes the child a session/process-group leader;
        # do not race a parent-side setpgid() against the child's setsid().

        self._reader = threading.Thread(
            target=self._read_loop,
            name="topgrade-session-reader",
            daemon=True,
        )
        self._reader.start()

    def write(self, data: str | bytes) -> None:
        """Write bytes to the PTY (user input / retry answers)."""
        if self._master_fd is None:
            return
        payload = data if isinstance(data, bytes) else data.encode()
        with contextlib.suppress(OSError):
            os.write(self._master_fd, payload)

    def resize(self, rows: int, cols: int) -> None:
        """Update the PTY window size."""
        if self._master_fd is None:
            return
        winsize = struct.pack("HHHH", max(1, rows), max(1, cols), 0, 0)
        with contextlib.suppress(OSError):
            fcntl_ioctl = termios.TIOCSWINSZ
            import fcntl

            fcntl.ioctl(self._master_fd, fcntl_ioctl, winsize)

    def reply_askpass(self, request_id: int, password: str | None) -> None:
        """Deliver an askpass reply collected by the GUI."""
        with self._askpass_lock:
            reply_queue = self._askpass_replies.get(request_id)
        if reply_queue is not None:
            reply_queue.put(password)

    def cancel(self) -> None:
        """Terminate the process group: SIGTERM, then SIGKILL.

        Wait on the whole group, not just the session leader — a child that
        ignores SIGTERM can outlive the leader and must still get SIGKILL.
        """
        if self._pid is None:
            return
        pgid = self._pid
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGTERM)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            self._wait_nonblocking()
            if not self._process_group_alive(pgid):
                return
            time.sleep(0.05)
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, signal.SIGKILL)
        # Brief settle so callers do not race a still-dying worker.
        settle = time.monotonic() + 0.5
        while time.monotonic() < settle:
            self._wait_nonblocking()
            if not self._process_group_alive(pgid):
                return
            time.sleep(0.05)

    def wait(self, timeout: float | None = None) -> int | None:
        """Block until the reader finishes. Returns the exit code when known."""
        if self._reader is not None:
            self._reader.join(timeout=timeout)
        return self._returncode

    def close(self) -> None:
        """Stop helpers and close the PTY."""
        self._stop.set()
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=2)
        self._shutdown_askpass()
        if self._master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._master_fd)
            self._master_fd = None

    def _emit(self, event: SessionEvent) -> None:
        if self._on_event is not None:
            self._on_event(event)

    def _read_loop(self) -> None:
        assert self._master_fd is not None
        master_fd = self._master_fd
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        with self._log_path.open("ab") as log_file:
            while not self._stop.is_set():
                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.2)
                except (OSError, ValueError):
                    break
                if not ready:
                    if self._wait_nonblocking() is not None and not self._fd_has_data(
                        master_fd
                    ):
                        break
                    continue
                try:
                    data = os.read(master_fd, 4096)
                except OSError as exc:
                    if exc.errno in {errno.EIO, errno.EBADF}:
                        break
                    raise
                if not data:
                    break
                log_file.write(data)
                log_file.flush()
                text = decoder.decode(data)
                if text:
                    self._emit(OutputChunk(text=text))
                    for event in parse_topgrade_chunk(self._parser, text):
                        self._emit(event)

            tail = decoder.decode(b"", final=True)
            if tail:
                self._emit(OutputChunk(text=tail))
                for event in parse_topgrade_chunk(self._parser, tail):
                    self._emit(event)

        code = self._wait_nonblocking()
        if code is None and self._pid is not None:
            _pid, status = os.waitpid(self._pid, 0)
            code = _decode_wait_status(status)
        self._returncode = 0 if code is None else code
        self._emit(
            SessionFinished(
                returncode=self._returncode,
                log_path=self._log_path,
                failed_step=self._parser.failed_step,
            )
        )
        self._shutdown_askpass()
        if self._master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(self._master_fd)
            self._master_fd = None

    def _fd_has_data(self, fd: int) -> bool:
        try:
            ready, _, _ = select.select([fd], [], [], 0)
        except (OSError, ValueError):
            return False
        return bool(ready)

    def _wait_nonblocking(self) -> int | None:
        if self._pid is None:
            return self._returncode
        try:
            pid, status = os.waitpid(self._pid, os.WNOHANG)
        except ChildProcessError:
            return self._returncode if self._returncode is not None else 0
        if pid == 0:
            return None
        self._returncode = _decode_wait_status(status)
        return self._returncode

    @staticmethod
    def _process_group_alive(pgid: int) -> bool:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _start_askpass_server(self) -> None:
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/topgrade-update-{os.getuid()}")
        runtime.mkdir(parents=True, exist_ok=True)
        sock_path = runtime / f"topgrade-update-askpass-{os.getpid()}-{time.time_ns()}.sock"
        with contextlib.suppress(FileNotFoundError):
            sock_path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        server.listen(5)
        server.settimeout(0.5)
        self._askpass_sock = sock_path
        self._askpass_server = server
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
                raw = conn.recv(4096).decode(errors="replace").strip()
            except OSError:
                return
            prompt = raw or "Password:"
            with self._askpass_lock:
                request_id = self._askpass_next_id
                self._askpass_next_id += 1
                reply_queue: queue.Queue[str | None] = queue.Queue(maxsize=1)
                self._askpass_replies[request_id] = reply_queue
            self._emit(AskpassRequest(prompt=prompt, request_id=request_id))
            try:
                password = reply_queue.get(timeout=300)
            except queue.Empty:
                password = None
            finally:
                with self._askpass_lock:
                    self._askpass_replies.pop(request_id, None)
            if password is None:
                return
            with contextlib.suppress(OSError):
                conn.sendall(f"{password}\n".encode())

    def _shutdown_askpass(self) -> None:
        server = self._askpass_server
        self._askpass_server = None
        if server is not None:
            with contextlib.suppress(OSError):
                server.close()
        if self._askpass_sock is not None:
            with contextlib.suppress(FileNotFoundError, OSError):
                self._askpass_sock.unlink()
            self._askpass_sock = None


def _decode_wait_status(status: int) -> int:
    if os.WIFEXITED(status):
        return int(os.WEXITSTATUS(status))
    if os.WIFSIGNALED(status):
        return 128 + int(os.WTERMSIG(status))
    return 1


def _askpass_launcher() -> str:
    """Write a tiny SUDO_ASKPASS script that talks to our Unix socket."""
    import sys

    script = (
        "import os,socket,sys;"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);"
        "s.connect(os.environ['TOPGRADE_UPDATE_ASKPASS_SOCK']);"
        "prompt=sys.argv[1] if len(sys.argv)>1 else 'Password:';"
        "s.sendall(prompt.encode());"
        "sys.stdout.write(s.recv(4096).decode())"
    )
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/topgrade-update-{os.getuid()}")
    runtime.mkdir(parents=True, exist_ok=True)
    helper = runtime / f"topgrade-update-askpass-{os.getpid()}.sh"
    helper.write_text(f"#!/bin/sh\nexec {sys.executable} -c {script!r} \"$@\"\n", encoding="utf-8")
    helper.chmod(0o700)
    return str(helper)


def _sudo_askpass_wrapper_dir(real_sudo: str) -> str:
    """Return a PATH directory containing a ``sudo`` that always passes ``-A``."""
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/topgrade-update-{os.getuid()}")
    wrapper_dir = runtime / f"topgrade-update-sudo-wrap-{os.getpid()}"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper = wrapper_dir / "sudo"
    wrapper.write_text(
        "#!/bin/sh\n"
        # Avoid recursing into this wrapper if PATH still points here.
        f"exec {real_sudo} -A \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o700)
    return str(wrapper_dir)
