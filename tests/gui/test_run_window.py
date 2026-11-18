"""Tests for the in-app topgrade run window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from uptray.core.models import Config  # noqa: E402
from uptray.gui.run_window import RunWindow  # noqa: E402


def _command(tmp_path: Path, body: str, *, name: str = "fixture.sh") -> list[str]:
    script = tmp_path / name
    script.write_text(body, encoding="utf-8")
    return ["/bin/sh", str(script)]


def _fake_command(tmp_path: Path, *, fail: bool = False) -> list[str]:
    script = tmp_path / ("fail.sh" if fail else "ok.sh")
    if fail:
        script.write_text(
            "#!/bin/sh\n"
            "printf '\\n── 12:00:00 - Broken ──────────\\n'\n"
            "printf 'Broken: FAILED: disk full\\n'\n"
            "exit 2\n",
            encoding="utf-8",
        )
    else:
        script.write_text(
            "#!/bin/sh\n"
            "printf '\\n── 12:00:00 - Demo ──────────\\n'\n"
            "printf 'Demo: OK\\n'\n"
            "exit 0\n",
            encoding="utf-8",
        )
    script.chmod(0o755)
    return ["/bin/sh", str(script)]


def test_run_window_mode_toggle_switches_stack(qapp, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
    )
    assert window._stack.currentIndex() == 0
    window._set_mode("verbose")
    assert window._stack.currentIndex() == 1
    assert window._mode_verbose.isChecked()
    window.close()


def test_run_window_failed_run_enables_diagnose_default(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path, fail=True),
    )
    window.show()
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)
    assert window._returncode not in (None, 0)
    assert window._btn_diagnose.isDefault()
    window._toggle_diagnose()
    assert not window._diagnose.isHidden()
    window.close()


def test_review_log_lists_current_transcript(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    runs = tmp_path / "runs"
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
        runs_dir=runs,
    )
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)
    assert window._log_path is not None
    assert window._log_path.is_file()
    assert window._log_path.parent == runs
    from uptray.gui.run_window import ReviewLogDialog

    dialog = ReviewLogDialog(current=window._log_path, runs_dir=runs)
    assert dialog._list.count() >= 1
    dialog.close()
    window.close()


def test_run_window_prompt_bar_announces_and_clears(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    """Detected [Y/n] prompts show the strip; cleared events hide it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from uptray.core.topgrade_session import PromptCleared, PromptRequest

    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
    )
    window._on_session_event(PromptRequest(question="Continue? [y/N]:"))
    assert not window._prompt_bar.isHidden()
    assert "Continue?" in window._prompt_label.text()
    window._on_session_event(PromptCleared())
    assert window._prompt_bar.isHidden()
    window.close()


def test_diagnose_drawer_opens_resizable(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    """The diagnose drawer takes a substantial, user-resizable share."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
    )
    window.show()
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)
    window._toggle_diagnose()
    assert not window._diagnose.isHidden()
    sizes = window._splitter.sizes()
    assert sizes[1] >= 200
    window._toggle_diagnose()
    assert window._diagnose.isHidden()
    window.close()


def _slow_command(tmp_path: Path) -> list[str]:
    script = tmp_path / "slow.sh"
    script.write_text(
        "#!/bin/sh\nprintf '\\n── 12:00:00 - Slow ──────────\\n'\nsleep 30\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return ["/bin/sh", str(script)]


def _running_window(qtbot, tmp_path: Path) -> RunWindow:  # noqa: ANN001
    window = RunWindow(
        Config(run_mode="simple"),
        command=_slow_command(tmp_path),
        runs_dir=tmp_path / "runs",
    )
    window.show()
    qtbot.waitUntil(lambda: window._current_step == "Slow", timeout=5000)
    return window


def test_close_while_running_hides_and_keeps_running(
    qapp,
    qtbot,
    tmp_path,
    sent_messages,  # noqa: ANN001
) -> None:
    window = _running_window(qtbot, tmp_path)

    window.close()
    window.close()

    assert window.isHidden()
    assert window.is_active
    assert sent_messages == [
        (
            "Still running in the background",
            "Choose Open current run in the tray to bring the window back.",
        ),
    ]
    window.shutdown()
    assert not window.is_active


def test_cancel_declined_keeps_update_running(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _running_window(qtbot, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No)

    window._cancel()

    assert window.is_active
    window.shutdown()


def test_confirmed_cancel_is_not_reported_as_a_failure(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,
    sent_messages,  # noqa: ANN001
) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _running_window(qtbot, tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)

    window._cancel()
    qtbot.waitUntil(lambda: window.monitor_status == "Update cancelled", timeout=5000)
    assert "Update failed" not in [summary for summary, _body in sent_messages]


def test_escape_closes_only_when_finished(qapp, qtbot, tmp_path) -> None:  # noqa: ANN001
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    running = _running_window(qtbot, tmp_path)
    QTest.keyClick(running, Qt.Key.Key_Escape)
    assert running.isVisible()
    running.shutdown()

    done = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )
    done.show()
    qtbot.waitUntil(lambda: done._returncode is not None, timeout=5000)
    QTest.keyClick(done, Qt.Key.Key_Escape)
    assert not done.isVisible()


def test_hidden_window_notifies_once_on_finish(
    qapp,
    qtbot,
    tmp_path,
    sent_messages,  # noqa: ANN001
) -> None:
    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )

    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)

    assert [summary for summary, _ in sent_messages] == ["Update finished"]
    window.close()


def test_askpass_is_waiting_with_a_masked_focused_input(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit

    from uptray.core.topgrade_session import AskpassRequest

    window = _running_window(qtbot, tmp_path)
    assert window._session is not None
    replies: list[tuple[int, str | None]] = []
    monkeypatch.setattr(
        window._session,
        "reply_askpass",
        lambda request_id, password: replies.append(
            (request_id, password),
        ),
    )
    window._handle_askpass(AskpassRequest(prompt="[sudo] password", request_id=1))
    window._tick()
    assert window._state_label.text() == "Waiting for a password"
    assert window.monitor_status == "Waiting for a password · Slow"
    assert window._prompt_detail.text() == "[sudo] password"
    assert not window._prompt_bar.isHidden()
    assert window._btn_prompt_yes.isHidden()
    assert window._prompt_input.echoMode() == QLineEdit.EchoMode.Password
    assert window.focusWidget() is window._prompt_input
    QTest.keyClicks(window._prompt_input, "fixture-password")
    QTest.keyClick(window._prompt_input, Qt.Key.Key_Return)
    assert replies == [(1, "fixture-password")]
    assert window._prompt_input.text() == ""
    assert window._prompt_bar.isHidden()
    assert window.monitor_status == "Updating · Slow"
    window.shutdown()


def test_askpass_expiry_preserves_other_input_and_reveals_live_decisions(
    qapp,
    qtbot,
    tmp_path,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import AskpassExpired, AskpassRequest, RetryPrompt

    window = _running_window(qtbot, tmp_path)
    window._on_session_event(AskpassRequest("First password", 1))
    window._on_session_event(AskpassRequest("Queued password", 2))
    window._on_session_event(AskpassRequest("Next password", 3))
    window._on_session_event(RetryPrompt("Slow"))
    window._prompt_input.setText("first answer")

    window._on_session_event(AskpassExpired(2))
    assert window._prompt_detail.text() == "First password"
    assert window._prompt_input.text() == "first answer"

    window._on_session_event(AskpassExpired(1))
    assert window._prompt_detail.text() == "Next password"
    assert window._prompt_input.text() == ""
    assert window.focusWidget() is window._prompt_input

    window._prompt_input.setText("next answer")
    window._on_session_event(AskpassExpired(1))
    assert window._prompt_input.text() == "next answer"

    window._on_session_event(AskpassExpired(3))
    assert window._prompt_input.text() == ""
    assert window._prompt_label.text() == "Retry the Slow step?"
    assert window.focusWidget() is window._btn_retry
    assert window.monitor_status == "Waiting for your answer · Slow"
    window.shutdown()


def test_run_window_remembers_geometry_and_body_split(qapp, tmp_path) -> None:  # noqa: ANN001
    def make() -> RunWindow:
        return RunWindow(
            Config(run_mode="simple"),
            command=_fake_command(tmp_path),
            runs_dir=tmp_path / "runs",
        )

    first = make()
    first.resize(1100, 760)  # well above the 840x560 minimum
    first.show()
    qapp.processEvents()
    first._body.setSizes([300, 500])
    qapp.processEvents()
    saved = first._body.sizes()[0]
    saved_size = (first.width(), first.height())  # what the (small) screen allowed
    first.shutdown()

    # Compare laid-out windows: an unshown splitter's sizes depend on font metrics.
    second = make()
    second.show()
    qapp.processEvents()
    assert (second.width(), second.height()) == saved_size
    assert abs(second._body.sizes()[0] - saved) < 10
    second.shutdown()


def test_failed_run_shows_topgrade_reason(qapp, qtbot, tmp_path) -> None:  # noqa: ANN001
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path, fail=True),
        runs_dir=tmp_path / "runs",
    )
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)

    assert "disk full" in window._subtitle_label.text()
    assert "disk full" in window._diagnose_prompt()
    window.close()


def test_dry_run_offers_run_for_real(qapp, qtbot, tmp_path, sent_messages) -> None:  # noqa: ANN001
    calls: list[str] = []
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
        extra_args=["--run-type=dry", "--only", "flatpak"],
        on_run_for_real=lambda: calls.append("real"),
        runs_dir=tmp_path / "runs",
    )
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)

    assert window._state_label.text() == "Preview complete"
    assert sent_messages == [("Preview finished", "No changes were made.\nPreview Flatpak")]
    assert not window._btn_run_real.isHidden()
    window._btn_run_real.click()
    assert calls == ["real"]
    window.close()


def test_silent_step_gets_no_output_hint(qapp, qtbot, tmp_path) -> None:  # noqa: ANN001
    window = _running_window(qtbot, tmp_path)
    qtbot.waitUntil(lambda: window._current_step == "Slow", timeout=5000)

    window._last_output -= 200
    window._refresh_subtitle()

    assert "no output for 3:20" in window._subtitle_label.text()
    window.shutdown()


def test_typed_prompt_answer_is_sent_to_terminal(qapp, tmp_path) -> None:  # noqa: ANN001
    from uptray.core.topgrade_session import PromptRequest

    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )
    written: list[str] = []
    window._pty_write = written.append  # type: ignore[method-assign]

    window._on_session_event(PromptRequest(question="Quit: [v/s/r/o/q]", free_text=True))
    assert not window._prompt_input.isHidden()
    assert window._btn_prompt_yes.isHidden()
    window._prompt_input.setText("s")
    window._send_prompt_text()

    assert written == ["s\n"]
    assert window._prompt_bar.isHidden()
    window.close()


def test_prompt_brings_back_a_hidden_window(qapp, tmp_path) -> None:  # noqa: ANN001
    from uptray.core.topgrade_session import PromptRequest

    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )
    assert window.isHidden()

    window._on_session_event(PromptRequest(question="Continue? [y/N]:"))

    assert window.isVisible()
    window.shutdown()


def test_window_closed_before_start_never_launches(qapp, qtbot, tmp_path) -> None:  # noqa: ANN001
    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )

    window.close()
    qtbot.wait(50)

    assert window._session is None


def test_operation_progress_resets_between_steps(qapp, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    from uptray.core.topgrade_session import SessionFinished, StepEvent

    window = RunWindow(Config(), command=_fake_command(tmp_path))
    updates: list[float | None] = []
    monkeypatch.setattr(window._task_progress, "update", updates.append)
    window._apply_step(StepEvent("System update", "running", latest_line="integrity 43%"))
    assert window._progress.maximum() == 100
    assert window._progress.value() == 43
    assert updates[-1] == 0.43
    window._apply_step(StepEvent("Flatpak", "running", latest_line="Starting…"))
    assert window._progress.maximum() == 0
    assert updates[-1] is None
    window._finish(SessionFinished(returncode=0, log_path=tmp_path / "run.log"))
    assert updates[-1] is None
    window.close()


def test_carriage_return_stream_updates_both_progress_indicators(
    qapp,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import _ParserState, parse_topgrade_chunk

    window = RunWindow(Config(), command=_fake_command(tmp_path))
    updates: list[float | None] = []
    monkeypatch.setattr(window._task_progress, "update", updates.append)
    state = _ParserState()
    for event in parse_topgrade_chunk(state, "── System update ──\n"):
        window._on_session_event(event)
    for percent in (10, 50, 100):
        for event in parse_topgrade_chunk(state, f"\rchecking integrity {percent}%"):
            window._on_session_event(event)
        assert window._progress.value() == percent
        assert updates[-1] == percent / 100
    window.close()


def test_hidden_retry_restores_window_and_keyboard_answers_original_child(
    qapp,
    qtbot,
    tmp_path,
    sent_messages,  # noqa: ANN001
) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from uptray.core.topgrade_session import RETRY_PROMPT, RetryPrompt

    command = _command(
        tmp_path,
        "printf '── Flatpak ──\n'\n"
        'while [ ! -f "$1" ]; do sleep 0.02; done\n'
        "stty raw -echo\n"
        "printf 'Flatpak: FAILED: Could not reach the remote repository.\\r\\n'\n"
        f"printf '{RETRY_PROMPT}'\n"
        "key=$(dd bs=1 count=1 2>/dev/null)\n"
        '[ "$key" = y ]\n',
    )
    trigger = tmp_path / "trigger"
    window = RunWindow(Config(), command=[*command, str(trigger)], runs_dir=tmp_path / "runs")
    window.show()
    qtbot.waitUntil(lambda: window._current_step == "Flatpak")
    original = window._session

    window.close()
    assert window.isHidden()
    trigger.touch()
    qtbot.waitUntil(lambda: window._state_label.text() == "Waiting for your answer")
    window._on_session_event(RetryPrompt("Flatpak"))
    window._tick()
    assert window.isVisible()
    assert window.monitor_status == "Waiting for your answer · Flatpak"
    assert window._prompt_label.text() == "Retry the Flatpak step?"
    assert "remote repository" in window._prompt_detail.text()
    assert window.focusWidget() is window._btn_retry
    assert [summary for summary, _ in sent_messages].count("Topgrade needs your answer") == 1

    QTest.keyClick(window._btn_retry, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window._returncode is not None)
    assert window._returncode == 0
    assert window._session is original
    assert window._prompt_bar.isHidden()
    assert window._state_label.text() == "Update complete"
    window.close()


def test_verbose_single_key_clears_retry_with_no_extra_input(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import RetryPrompt

    window = _running_window(qtbot, tmp_path)
    assert window._session is not None
    written: list[str] = []
    monkeypatch.setattr(window._session, "write", written.append)
    window._on_session_event(RetryPrompt("Slow"))
    window._set_mode("verbose")
    window._term.input_ready.emit("n")
    assert window._stack.currentIndex() == 1
    assert written == ["n"]
    assert window._prompt_bar.isHidden()
    assert window.monitor_status == "Updating · Slow"
    window.shutdown()


@pytest.mark.parametrize("size", [(640, 480), (840, 560)])
def test_simple_monitor_keeps_wrapped_activity_and_prompt_available(
    qapp,
    qtbot,
    tmp_path,
    size,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import PromptRequest, StepEvent

    window = _running_window(qtbot, tmp_path)
    window.resize(*size)
    line = "Checking package " + "very-long-package-name-" * 20 + "see the end"
    window._on_session_event(StepEvent("Slow", "running", latest_line=line))
    window._on_session_event(PromptRequest("Proceed with the installation? [Y/n]"))
    qapp.processEvents()

    assert (window.width(), window.height()) == size
    assert window._steps_panel.isHidden() == (size[0] == 640)
    assert window._prompt_bar.isVisible()
    assert window._elapsed_label.isVisible()
    assert window._activity.isVisible()
    assert "see the end" in window._activity.toPlainText()
    assert window._activity.document().firstBlock().layout().lineCount() > 1
    assert window._activity.horizontalScrollBar().maximum() == 0
    assert window._btn_prompt_yes is window.focusWidget()
    window.shutdown()


@pytest.mark.parametrize(
    ("question", "default"),
    [
        ("Proceed with installation? [Y/n]", "yes"),
        ("Remove old packages? [y/N]", "no"),
        ("Continue? [y/n]", "no"),
    ],
)
def test_yes_no_prompt_focuses_the_answer_enter_would_give(
    qapp,
    qtbot,
    tmp_path,
    question: str,
    default: str,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import PromptRequest

    window = _running_window(qtbot, tmp_path)
    window._on_session_event(PromptRequest(question=question))

    expected = window._btn_prompt_yes if default == "yes" else window._btn_prompt_no
    assert window.focusWidget() is expected
    window.shutdown()


def test_growing_failure_report_appears_once_in_activity(qapp, tmp_path) -> None:  # noqa: ANN001
    from uptray.core.topgrade_session import _ParserState, parse_topgrade_chunk

    window = RunWindow(Config(), command=_fake_command(tmp_path))
    state = _ParserState()
    for chunk in (
        "── Flatpak ──\n",
        "Flatpak failed: \n",
        "   0: Command failed: `flatpak update -y`\n",
        "   1: exit status: 1\n",
        "── Summary ──\n",
        "System update: OK\n",
        "Flatpak: FAILED\n",
    ):
        for event in parse_topgrade_chunk(state, chunk):
            window._on_session_event(event)

    text = window._activity.toPlainText()
    assert text.count("Flatpak failed") == 1
    assert text.count("exit status: 1") == 1
    assert "System update completed" in text
    window.close()


def test_run_outcome_warning_does_not_claim_transcript_is_incomplete(
    qapp,
    tmp_path,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import SessionFinished, TranscriptWarning

    window = RunWindow(Config(), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs")
    window._on_session_event(
        TranscriptWarning("Could not save the run outcome: disk full", transcript_incomplete=False)
    )
    window._on_session_event(SessionFinished(0, tmp_path / "run.log"))
    assert not window._warning_label.isHidden()
    assert window._warning_label.text() == "Could not save the run outcome: disk full"
    assert window.monitor_status == "Update complete"
    window.close()


def test_cancelled_run_keeps_transcript_warning_and_distinct_outcome(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,  # noqa: ANN001
) -> None:
    from uptray.core.topgrade_session import TranscriptWarning

    window = _running_window(qtbot, tmp_path)
    window._on_session_event(TranscriptWarning("Transcript is incomplete: disk full"))
    monkeypatch.setattr(window, "confirm_stop", lambda: True)
    window._cancel()
    qtbot.waitUntil(lambda: window._returncode is not None)
    assert window.monitor_status == "Update cancelled"
    assert window._warning_label.isVisible()
    assert "disk full" in window._warning_label.text()
    assert window._btn_try_again.isVisible()
    window.close()


def test_log_open_failure_prevents_launch_and_reports_startup_error(
    qapp,
    qtbot,
    tmp_path,  # noqa: ANN001
) -> None:
    inaccessible = tmp_path / "file"
    inaccessible.write_text("this is not a directory")
    window = RunWindow(
        Config(),
        command=_fake_command(tmp_path),
        runs_dir=inaccessible,
    )
    with qtbot.waitSignal(window.finished) as result:
        window.show()
    assert result.args == [126]
    assert window.monitor_status == "Could not start"
    assert not window.is_active
    assert window._btn_try_again.isVisible()
    window.close()
