"""Tests for the embedded terminal fallback keyboard path."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402

from uptray.gui import terminal_widget as terminal_mod  # noqa: E402
from uptray.gui.terminal_widget import TerminalWidget  # noqa: E402


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


def test_fallback_redraw_and_resize(qapp, qtbot, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(terminal_mod, "_WEBENGINE_AVAILABLE", False)
    widget = TerminalWidget()
    qtbot.addWidget(widget)
    sizes: list[tuple[int, int]] = []
    widget.set_resize_handler(lambda rows, cols: sizes.append((rows, cols)))
    widget.resize(800, 400)
    widget.show()
    qtbot.waitUntil(lambda: bool(sizes))
    wide = sizes[-1][1]
    widget.write("checking 10%\r\x1b[")
    widget.write("Kchecking 50%\r\nnext")
    assert widget._fallback.toPlainText() == "checking 50%\nnext"
    widget.resize(400, 400)
    qtbot.waitUntil(lambda: sizes[-1][1] < wide)
    assert widget._fallback.lineWrapMode() == widget._fallback.LineWrapMode.NoWrap
