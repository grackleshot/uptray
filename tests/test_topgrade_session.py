"""Tests for the PTY topgrade session and output parser."""

from __future__ import annotations

import codecs
import os
import time
from pathlib import Path

import pytest

from topgrade_update.core.topgrade_session import (
    OutputChunk,
    PromptCleared,
    PromptRequest,
    RetryPrompt,
    SessionFinished,
    StepEvent,
    TopgradeSession,
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
    assert any(isinstance(e, SessionFinished) for e in events)


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
    session._started = True
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
    from topgrade_update.core.topgrade_session import _sudo_askpass_wrapper_dir

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
