"""Tests for the embedded terminal fallback keyboard path."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from topgrade_update.gui import terminal_widget as terminal_mod  # noqa: E402
from topgrade_update.gui.terminal_widget import TerminalWidget  # noqa: E402


def test_fallback_backspace_emits_delete(
    qapp, monkeypatch: pytest.MonkeyPatch  # noqa: ANN001
) -> None:
    monkeypatch.setattr(terminal_mod, "_WEBENGINE_AVAILABLE", False)
    widget = TerminalWidget()
    assert widget._view is None
    captured: list[str] = []
    widget.input_ready.connect(captured.append)

    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.NoModifier,
    )
    assert widget.eventFilter(widget._fallback, event) is True
    assert captured == ["\x7f"]

    enter = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
    )
    assert widget.eventFilter(widget._fallback, enter) is True
    assert captured[-1] == "\r"
