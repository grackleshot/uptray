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
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    window = RunWindow(
        Config(run_mode="simple"),
        command=_fake_command(tmp_path),
    )
    qtbot.waitUntil(lambda: window._returncode is not None, timeout=5000)
    assert window._log_path is not None
    assert window._log_path.is_file()
    from topgrade_update.gui.run_window import ReviewLogDialog

    dialog = ReviewLogDialog(current=window._log_path)
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
