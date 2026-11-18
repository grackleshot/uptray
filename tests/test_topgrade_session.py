"""Tests for the PTY topgrade session and output parser."""

from __future__ import annotations

import codecs
import os
import pty
import socket
import threading
import time
from pathlib import Path

import pytest

from uptray.core import topgrade_session
from uptray.core.run_history import list_runs
from uptray.core.topgrade_session import (
    AskpassExpired,
    AskpassRequest,
    OutputChunk,
    PromptCleared,
    PromptRequest,
    RetryPrompt,
    SessionFinished,
    StepEvent,
    TopgradeSession,
    TranscriptWarning,
    _ParserState,
    build_diagnose_prompt,
    list_run_logs,
    parse_idle,
    parse_topgrade_chunk,
    strip_ansi,
)


def test_strip_ansi_removes_color_codes() -> None:
    assert strip_ansi("\x1b[1m── 12:00:00 - System update ────\x1b[0m") == (
        "── 12:00:00 - System update ────"
    )


def test_parser_detects_steps_results_and_retry() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state,
        "\n── 12:00:00 - System update ────────────────\n"
        "reading package lists\n"
        "── 12:00:01 - Flatpak ───────────────────────\n"
        "System update: FAILED\n"
        "Retry? (y)es/(N)o/(s)hell/(q)uit",
    )

    running = [
        e for e in events
        if isinstance(e, StepEvent) and e.name == "System update" and e.status == "running"
    ]
    failed = [
        e for e in events
        if isinstance(e, StepEvent) and e.name == "System update" and e.status == "failed"
    ]
    assert running
    assert failed
    assert any(isinstance(e, RetryPrompt) for e in events)
    assert state.failed_step == "System update"


def test_parser_plain_separator_and_skip() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(state, "―― rustup ――\nrustup: SKIPPED: not installed\n")
    assert any(
        isinstance(e, StepEvent) and e.name == "rustup" and e.status == "running"
        for e in events
    )
    assert any(isinstance(e, StepEvent) and e.status == "skipped" for e in events)


def test_parser_retains_topgrade_error_chain_through_retry_and_summary() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state,
        "── 21:28:55 - Monitor fixture ──\r\n"
        "Monitor fixture failed: \r\n"
        "   0: \x1b[91mCommand failed: `/bin/sh -c 'sleep 0.4 && false'`\x1b[0m\r\n"
        "   1: \x1b[91m`/bin/sh` failed: exit status: 1\x1b[0m\r\n\r\n"
        "Location:\r\n"
        "   \x1b[35msrc/steps/generic.rs\x1b[0m:1637\x1b]0;Topgrade - Awaiting user\a\r\n"
        "Retry? (y)es/(N)o/(s)hell/(q)uit",
    )
    (retry,) = [event for event in events if isinstance(event, RetryPrompt)]
    assert retry.step_name == "Monitor fixture"
    events.extend(parse_topgrade_chunk(
        state, "\r\n── 21:28:55 - Summary ──\r\nMonitor fixture: FAILED\r\n",
    ))
    steps = [event for event in events if isinstance(event, StepEvent)]
    failed = [event for event in steps if event.status == "failed"]
    expected_reason = (
        "0: Command failed: `/bin/sh -c 'sleep 0.4 && false'`\n"
        "1: `/bin/sh` failed: exit status: 1\n"
        "Location:\nsrc/steps/generic.rs:1637"
    )
    assert failed[-2].reason == failed[-1].reason == expected_reason
    assert {event.name for event in steps} == {"Monitor fixture"}
    assert not any(event.status == "succeeded" for event in steps)
    assert state.failed_step == "Monitor fixture"


def test_child_command_failure_line_is_not_a_step_and_keeps_prompts() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state,
        "── 12:00:00 - AUR ──\n"
        "gpg: keyserver receive failed: No data\n"
        ":: Import PGP key ABCD? [Y/n] ",
    )
    assert [e.question for e in events if isinstance(e, PromptRequest)] == [
        ":: Import PGP key ABCD? [Y/n]"
    ]
    assert state.steps == {"AUR": "running"}
    assert state.failed_step is None


def test_summary_resolves_retried_failure_and_ignores_unrelated_step_rows() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state,
        "── Demo ──\n"
        "some subprocess: OK\n"
        "Demo failed: first attempt failed\n"
        "Retry? (y)es/(N)o/(s)hell/(q)uit\n"
        "── Demo ──\n"
        "── Summary ──\n"
        "Demo: OK\n",
    )
    assert state.steps == {"Demo": "succeeded"}
    assert state.failed_step is None
    assert [
        event.latest_line for event in events
        if isinstance(event, StepEvent) and event.status == "succeeded"
    ] == ["Demo: OK"]


def test_step_outcome_stays_unconfirmed_until_summary() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state, "── Demo ──\nwork\n── Flatpak ──\n── Summary ──\nDemo: FAILED\nFlatpak: OK\n",
    )
    assert [
        event.status for event in events
        if isinstance(event, StepEvent) and event.name == "Demo"
    ] == ["running", "running", "ended", "failed"]
    assert state.steps == {"Demo": "failed", "Flatpak": "succeeded"}


@pytest.mark.parametrize(
    "header",
    [
        "── 22:52:35 - Sudo ──────────────",
        "── Sudo ──────────────",
        "―― 22:52:35 - Sudo ――",
        "―― Sudo ――",
        "generic.rs:871―― 22:52:35 - Sudo ――",
    ],
)
def test_parser_step_name_never_includes_timestamp(header: str) -> None:
    events = parse_topgrade_chunk(_ParserState(), f"{header}\n")
    names = [e.name for e in events if isinstance(e, StepEvent)]
    assert names == ["Sudo"]


def test_parser_separator_wins_over_unanswered_prompt_on_same_line() -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(
        state,
        ":: Do you want to remove all saved diffs? [Y/n]: ―― 23:08:07 - pacdiff check ――\n",
    )
    assert not any(isinstance(e, PromptRequest) for e in events)
    assert state.current_step == "pacdiff check"


def test_session_writes_log_and_emits_finish(tmp_path: Path) -> None:
    events: list[object] = []
    script = tmp_path / "fake_topgrade.sh"
    script.write_text(
        "#!/bin/sh\n"
        "printf '\\n── 12:00:00 - Demo ──────────\\n'\n"
        "printf 'working\\n'\n"
        "printf 'Demo: OK\\n'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    log_path = tmp_path / "runs" / "test.log"
    session = TopgradeSession(
        ["/bin/sh", str(script)],
        log_path=log_path,
        enable_askpass=False,
        on_event=events.append,
    )
    session.start()
    code = session.wait(timeout=5)
    session.close()

    assert code == 0
    assert log_path.is_file()
    assert "Demo" in log_path.read_text(encoding="utf-8", errors="replace")
    assert any(isinstance(e, OutputChunk) for e in events)
    assert any(isinstance(e, SessionFinished) and e.returncode == 0 for e in events)


def test_session_opens_transcript_before_spawning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_path = tmp_path / "directory.log"
    blocked_path.mkdir()
    session = TopgradeSession(["/bin/true"], log_path=blocked_path, enable_askpass=False)

    def unexpected_fork() -> tuple[int, int]:
        pytest.fail("fork ran despite transcript open failure")

    monkeypatch.setattr(pty, "fork", unexpected_fork)
    with pytest.raises(IsADirectoryError):
        session.start()
    assert not session.running


def test_full_transcript_does_not_interrupt_output_input_or_exit(tmp_path: Path) -> None:
    full = Path("/dev/full")
    if not full.exists():
        pytest.skip("requires /dev/full")
    prompted = threading.Event()
    events: list[object] = []

    def collect(event: object) -> None:
        events.append(event)
        if isinstance(event, PromptRequest):
            prompted.set()

    session = TopgradeSession(
        ["/bin/sh", "-c", "printf 'Continue? [Y/n] '; read reply; echo Answer: \"$reply\"; exit 2"],
        log_path=full,
        runs_dir=tmp_path,
        enable_askpass=False,
        on_event=collect,
        extra_args=["--only", "flatpak"],
    )
    session.start()
    try:
        assert prompted.wait(5)
        session.write("y\n")
        assert session.wait(timeout=5) == 2
    finally:
        session.close()

    (warning,) = [event for event in events if isinstance(event, TranscriptWarning)]
    assert warning.transcript_incomplete
    (finished,) = [event for event in events if isinstance(event, SessionFinished)]
    assert finished.returncode == 2
    assert finished.transcript_incomplete
    assert "Answer: y" in "".join(e.text for e in events if isinstance(e, OutputChunk))
    (run,) = list_runs(tmp_path)
    assert run.outcome == "failed"
    assert run.returncode == 2
    assert run.transcript_incomplete
    assert run.scope == "Update Flatpak"


@pytest.mark.parametrize("operation", ["write", "close"])
def test_transcript_errors_do_not_change_child_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    events: list[object] = []
    log_path = tmp_path / "test.log"

    class BrokenLog:
        closed = False

        def write(self, data: bytes) -> int:
            if operation == "write":
                raise OSError("transcript write failed")
            return len(data)

        def flush(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True
            if operation == "close":
                raise OSError("transcript close failed")

    log_file = BrokenLog()
    original_open = Path.open

    def fake_open(path, mode="r", *args, **kwargs):  # type: ignore[no-untyped-def]
        if path == log_path and mode == "ab":
            return log_file
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)
    session = TopgradeSession(
        ["/bin/sh", "-c", "echo output; exit 3"],
        log_path=log_path,
        enable_askpass=False,
        on_event=events.append,
    )
    session.start()
    try:
        assert session.wait(timeout=5) == 3
    finally:
        session.close()
    assert log_file.closed
    assert len([e for e in events if isinstance(e, TranscriptWarning)]) == 1
    (finish,) = [e for e in events if isinstance(e, SessionFinished)]
    assert finish.transcript_incomplete
    assert finish.returncode == 3
    assert "output" in "".join(e.text for e in events if isinstance(e, OutputChunk))


def test_parser_failure_keeps_the_terminal_and_log_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = threading.Event()
    events: list[object] = []

    def collect(event: object) -> None:
        events.append(event)
        if isinstance(event, TranscriptWarning):
            ready.set()

    def broken_parse(_state: _ParserState, _text: str) -> list[object]:
        raise ValueError("bad parser state")

    monkeypatch.setattr(topgrade_session, "parse_topgrade_chunk", broken_parse)
    session = TopgradeSession(
        ["/bin/sh", "-c", "printf 'Waiting '; read reply; echo Input: \"$reply\"; exit 4"],
        runs_dir=tmp_path,
        enable_askpass=False,
        on_event=collect,
    )
    session.start()
    try:
        assert ready.wait(5)
        session.write("test\n")
        assert session.wait(timeout=5) == 4
    finally:
        session.close()
    (warning,) = [event for event in events if isinstance(event, TranscriptWarning)]
    (finish,) = [event for event in events if isinstance(event, SessionFinished)]
    assert not warning.transcript_incomplete
    assert not finish.transcript_incomplete
    assert "Input: test" in session.log_path.read_text()


def test_session_cancel_kills_process_group(tmp_path: Path) -> None:
    events: list[object] = []
    script = tmp_path / "sleep.sh"
    script.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    script.chmod(0o755)
    session = TopgradeSession(
        ["/bin/sh", str(script)],
        log_path=tmp_path / "cancel.log",
        enable_askpass=False,
        on_event=events.append,
    )
    session.start()
    time.sleep(0.2)
    session.cancel()
    code = session.wait(timeout=5)
    session.close()

    assert code is not None and code != 0
    (finished,) = [event for event in events if isinstance(event, SessionFinished)]
    assert finished.cancelled
    (run,) = list_runs(tmp_path)
    assert run.outcome == "cancelled"
    assert run.returncode == code


def test_cancel_sigkills_when_process_group_outlives_leader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even after the session leader exits, cancel must SIGKILL remaining group members."""
    import signal

    session = TopgradeSession(
        ["/bin/true"],
        log_path=Path("/tmp/unused-cancel.log"),
        enable_askpass=False,
    )
    session._pid = 4242
    signals: list[int] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        assert pgid == 4242
        signals.append(sig)

    def fake_alive(_pgid: int) -> bool:
        # Stay alive until SIGKILL has been delivered.
        return signal.SIGKILL not in signals

    # Advance the cancel deadlines immediately.
    ticks = {"n": 0}

    def fake_monotonic() -> float:
        ticks["n"] += 1
        return float(ticks["n"])

    monkeypatch.setattr(os, "killpg", fake_killpg)
    monkeypatch.setattr(session, "_wait_nonblocking", lambda: 0)
    monkeypatch.setattr(session, "_process_group_alive", fake_alive)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(time, "monotonic", fake_monotonic)

    session.cancel()

    assert signal.SIGTERM in signals
    assert signal.SIGKILL in signals


def test_list_run_logs_newest_first(tmp_path: Path) -> None:
    older = tmp_path / "a.log"
    newer = tmp_path / "b.log"
    older.write_text("old", encoding="utf-8")
    time.sleep(0.05)
    newer.write_text("new", encoding="utf-8")
    os.utime(older, (1, 1))
    assert list_run_logs(tmp_path)[0] == newer


def test_diagnose_prompt_includes_log_and_step(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("boom", encoding="utf-8")
    prompt = build_diagnose_prompt(returncode=1, failed_step="pacman", log_path=log)
    assert "pacman" in prompt
    assert str(log) in prompt
    assert "1" in prompt


def test_session_default_log_paths_are_unique(tmp_path: Path) -> None:
    a = TopgradeSession(["/bin/true"], runs_dir=tmp_path, enable_askpass=False)
    b = TopgradeSession(["/bin/true"], runs_dir=tmp_path, enable_askpass=False)
    assert a.log_path != b.log_path


def test_sudo_askpass_wrapper_invokes_real_sudo_with_dash_a(tmp_path: Path) -> None:
    from uptray.core.topgrade_session import _sudo_askpass_wrapper_dir

    real = tmp_path / "real-sudo"
    real.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\n", encoding="utf-8")
    real.chmod(0o755)
    wrap_dir = Path(_sudo_askpass_wrapper_dir(str(real)))
    wrapped = wrap_dir / "sudo"
    assert wrapped.is_file()
    import subprocess

    out = subprocess.check_output([str(wrapped), "pacman", "-Syu"], text=True)
    assert out.splitlines() == ["-A", "pacman", "-Syu"]


def test_incremental_utf8_decode_preserves_step_separator() -> None:
    """A UTF-8 box-drawing char split across reads must still parse as a step."""
    raw = "\n── 12:00:00 - Demo ──────────\n".encode()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    state = _ParserState()
    events: list[object] = []
    # Split inside the first U+2500 (e2 94 80).
    for chunk in (raw[:2], raw[2:3], raw[3:]):
        text = decoder.decode(chunk)
        if text:
            events.extend(parse_topgrade_chunk(state, text))
    tail = decoder.decode(b"", final=True)
    if tail:
        events.extend(parse_topgrade_chunk(state, tail))
    assert any(
        isinstance(event, StepEvent) and event.name == "Demo" and event.status == "running"
        for event in events
    )



def test_parser_detects_and_clears_yn_prompts() -> None:
    """Bracket-style prompts surface once, then clear when output resumes."""
    state = _ParserState()
    # Prompt arrives without a trailing newline, as PTYs usually deliver it.
    events = parse_topgrade_chunk(state, "── 12:00:00 - paru cleanup ──\n")
    events += parse_topgrade_chunk(state, "Clean ALL AUR packages from cache? [y/N]: ")
    prompts = [event for event in events if isinstance(event, PromptRequest)]
    assert [p.question for p in prompts] == ["Clean ALL AUR packages from cache? [y/N]:"]

    # The same prompt text again must not re-announce.
    events = parse_topgrade_chunk(state, "")
    assert not [event for event in events if isinstance(event, PromptRequest)]

    # Typed answer echoes back: the prompt clears exactly once.
    events = parse_topgrade_chunk(state, "y\r\n")
    assert any(isinstance(event, PromptCleared) for event in events)
    assert not any(isinstance(event, PromptRequest) for event in events)


def test_parser_new_prompt_supersedes_previous() -> None:
    """A pending announcement clears when the next question appears."""
    state = _ParserState()
    parse_topgrade_chunk(state, "Remove saved diffs? [Y/n]: ")
    # Answer arrives in the next chunk, immediately followed by a new prompt.
    events = parse_topgrade_chunk(state, "n\nClean cache too? [y/N]: ")
    assert any(isinstance(event, PromptCleared) for event in events)
    questions = [
        event.question for event in events if isinstance(event, PromptRequest)
    ]
    assert questions == ["Clean cache too? [y/N]:"]


@pytest.mark.parametrize(
    ("chunk", "question", "free_text"),
    [
        (":: Proceed with installation? [Y/n] ", ":: Proceed with installation? [Y/n]", False),
        (
            "(V)iew, (S)kip, (R)emove pacnew, (O)verwrite with pacnew, (Q)uit: [v/s/r/o/q] ",
            "(V)iew, (S)kip, (R)emove pacnew, (O)verwrite with pacnew, (Q)uit: [v/s/r/o/q]",
            True,
        ),
        ("Enter a number (default=1): ", "Enter a number (default=1):", True),
        ("==> [N]one [A]ll [Ab]ort\n==> ", "==> [N]one [A]ll [Ab]ort", True),
    ],
)
def test_parser_flags_prompts_that_need_typed_answers(
    chunk: str, question: str, free_text: bool
) -> None:
    state = _ParserState()
    events = parse_topgrade_chunk(state, chunk) + parse_idle(state)
    prompts = [e for e in events if isinstance(e, PromptRequest)]
    assert [(p.question, p.free_text) for p in prompts] == [(question, free_text)]


def test_menu_prompt_waits_for_idle_so_split_reads_are_not_prompts() -> None:
    state = _ParserState()
    first = parse_topgrade_chunk(state, "building\n==>")
    rest = parse_topgrade_chunk(state, " Making package: foo 1.0\n")
    assert not any(isinstance(e, (PromptRequest, PromptCleared)) for e in first + rest)


def test_terminal_control_output_does_not_clear_pending_menu_prompt() -> None:
    state = _ParserState()
    parse_topgrade_chunk(state, "Enter a number (default=1): ")
    assert parse_idle(state)

    events = parse_topgrade_chunk(state, "\x1b[?25h") + parse_idle(state)

    assert events == []


def test_parser_ignores_dangling_non_prompt_output() -> None:
    events = parse_topgrade_chunk(_ParserState(), "compiling foo [release]")
    assert not any(isinstance(e, PromptRequest) for e in events)


def test_diagnose_prompt_includes_reason_when_known(tmp_path: Path) -> None:
    prompt = build_diagnose_prompt(
        returncode=1, failed_step="npm", log_path=tmp_path / "x.log", reason="EACCES"
    )
    assert "EACCES" in prompt
    assert "Reason" not in build_diagnose_prompt(
        returncode=1, failed_step="npm", log_path=tmp_path / "x.log"
    )


def test_private_runtime_dir_rejects_shared_or_missing_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uptray.core.topgrade_session import private_runtime_dir

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(private))
    assert private_runtime_dir() == private
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(shared))
    assert private_runtime_dir() is None
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert private_runtime_dir() is None


def test_askpass_expires_only_the_unanswered_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(topgrade_session, "_ASKPASS_TIMEOUT_S", 0.01)
    events: list[object] = []
    session = TopgradeSession(
        ["/bin/true"], runs_dir=tmp_path, enable_askpass=False, on_event=events.append,
    )

    helper, server = socket.socketpair()
    with helper:
        helper.sendall(b"Password for the first request:")
        session._handle_askpass_conn(server)
        assert helper.recv(4096) == b""

    request, expired = events
    assert isinstance(request, AskpassRequest)
    assert expired == AskpassExpired(request_id=request.request_id)
    assert request.request_id not in session._askpass_replies


def test_sudo_helpers_never_use_a_predictable_tmp_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    import stat

    from uptray.core import topgrade_session

    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    topgrade_session._private_dir.cache_clear()
    try:
        wrapper_dir = Path(topgrade_session._sudo_askpass_wrapper_dir("/usr/bin/sudo"))
        base = wrapper_dir.parent
        assert base != Path(f"/tmp/uptray-{os.getuid()}")
        assert stat.S_IMODE(base.stat().st_mode) == 0o700
        assert base.stat().st_uid == os.getuid()
    finally:
        topgrade_session._private_dir.cache_clear()


def test_initial_pty_size_reaches_child(tmp_path: Path) -> None:
    events: list[object] = []
    session = TopgradeSession(
        ["/bin/sh", "-c", "stty size"], runs_dir=tmp_path,
        on_event=events.append, enable_askpass=False,
    )
    session.resize(31, 67)
    session.start()
    session.wait(timeout=5)
    assert session.returncode == 0
    output = "".join(e.text for e in events if isinstance(e, OutputChunk))
    assert "31 67" in output
    session.close()


@pytest.mark.parametrize("ending", ["\r", "\r\n", "\n"])
def test_progress_redraws_emit_live_steps(ending: str) -> None:
    state = _ParserState()
    parse_topgrade_chunk(state, "── System update ──\n")
    for percent in (10, 50, 100):
        events = parse_topgrade_chunk(state, f"checking {percent}%{ending}")
        steps = [e for e in events if isinstance(e, StepEvent)]
        assert steps[-1].latest_line == f"checking {percent}%"
        assert steps[-1].name == "System update"


def test_progress_redraws_in_one_chunk_do_not_concatenate() -> None:
    state = _ParserState()
    parse_topgrade_chunk(state, "── System update ──\n")
    events = parse_topgrade_chunk(state, "checking 10%\rchecking 50%\rchecking 100%\r\n")
    steps = [e for e in events if isinstance(e, StepEvent)]
    assert [e.latest_line for e in steps] == ["checking 10%", "checking 50%", "checking 100%"]


def test_progress_prefixed_with_cr_can_end_mid_chunk() -> None:
    state = _ParserState()
    parse_topgrade_chunk(state, "── System update ──\n")
    assert not parse_topgrade_chunk(state, "\rchecking 5")
    events = parse_topgrade_chunk(state, "0%")
    steps = [e for e in events if isinstance(e, StepEvent)]
    assert steps[-1].latest_line == "checking 50%"
    events = parse_topgrade_chunk(state, "\r\nnext phase\n")
    steps = [e for e in events if isinstance(e, StepEvent)]
    assert steps[-1].latest_line == "next phase"
