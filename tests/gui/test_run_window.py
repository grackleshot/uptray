"""Tests for the in-app topgrade run window."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from topgrade_update.core.models import Config  # noqa: E402
from topgrade_update.gui.run_window import RunWindow  # noqa: E402


def _fake_command(tmp_path: Path, *, fail: bool = False) -> list[str]:
    script = tmp_path / ("fail.sh" if fail else "ok.sh")
    if fail:
        script.write_text(
            "#!/bin/sh\n"
            "printf '\\n── 12:00:00 - Broken ──────────\\n'\n"
            "printf 'Broken: FAILED\\n'\n"
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
    qapp, qtbot, tmp_path, monkeypatch  # noqa: ANN001
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
    qapp, qtbot, tmp_path, monkeypatch  # noqa: ANN001
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
    from topgrade_update.gui.run_window import ReviewLogDialog

    dialog = ReviewLogDialog(current=window._log_path, runs_dir=runs)
    assert dialog._list.count() >= 1
    dialog.close()
    window.close()


def test_run_window_prompt_bar_announces_and_clears(
    qapp, qtbot, tmp_path, monkeypatch  # noqa: ANN001
) -> None:
    """Detected [Y/n] prompts show the strip; cleared events hide it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from topgrade_update.core.topgrade_session import PromptCleared, PromptRequest

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
    qapp, qtbot, tmp_path, monkeypatch  # noqa: ANN001
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
    qtbot.waitUntil(lambda: window.is_active, timeout=5000)
    return window


def test_close_while_running_hides_and_keeps_running(
    qapp, qtbot, tmp_path, sent_messages  # noqa: ANN001
) -> None:
    window = _running_window(qtbot, tmp_path)

    window.close()
    window.close()

    assert window.isHidden()
    assert window.is_active
    assert [summary for summary, _ in sent_messages] == ["Still updating in the background"]
    window.shutdown()
    assert not window.is_active


def test_cancel_declined_keeps_update_running(
    qapp, qtbot, tmp_path, monkeypatch  # noqa: ANN001
) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _running_window(qtbot, tmp_path)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.No
    )

    window._cancel()

    assert window.is_active
    window.shutdown()


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
    qapp, qtbot, tmp_path, sent_messages  # noqa: ANN001
) -> None:
    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )

    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)

    assert [summary for summary, _ in sent_messages] == ["Update finished"]
    window.close()


def test_askpass_is_announced_in_prompt_bar(
    qapp, tmp_path, monkeypatch  # noqa: ANN001
) -> None:
    from PySide6.QtWidgets import QInputDialog

    from topgrade_update.core.topgrade_session import AskpassRequest

    window = RunWindow(
        Config(run_mode="simple"), command=_fake_command(tmp_path), runs_dir=tmp_path / "runs"
    )
    seen: dict[str, object] = {}

    def fake_get_text(*_a: object, **_k: object) -> tuple[str, bool]:
        seen["text"] = window._prompt_label.text()
        seen["bar"] = not window._prompt_bar.isHidden()
        seen["yes"] = not window._btn_prompt_yes.isHidden()
        return ("", False)

    monkeypatch.setattr(QInputDialog, "getText", fake_get_text)
    window._current_step = "System update"

    window._handle_askpass(AskpassRequest(prompt="[sudo] password", request_id=1))

    assert seen == {"text": "Password required for “System update”", "bar": True, "yes": False}
    assert window._prompt_bar.isHidden()
    window.shutdown()


def test_run_window_remembers_geometry_and_body_split(qapp, tmp_path) -> None:  # noqa: ANN001
    def make() -> RunWindow:
        return RunWindow(
            Config(run_mode="simple"),
            command=_fake_command(tmp_path),
            runs_dir=tmp_path / "runs",
        )

    first = make()
    first.show()
    first.resize(840, 590)
    first._body.setSizes([300, 650])
    first.close()
    second = make()
    assert (second.width(), second.height()) == (840, 590)
    assert abs(second._body.sizes()[0] - first._body.sizes()[0]) < 10
    second.close()
