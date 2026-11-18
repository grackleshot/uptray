"""Run-window decision card for PTY prompts and authentication."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from uptray.gui.style import set_primary

if TYPE_CHECKING:
    from uptray.gui.run_window import RunWindow


def build_prompt_bar(win: RunWindow, tokens: dict[str, str]) -> QFrame:
    """Keep the question, supporting detail and keyboard controls together."""
    win._prompt_bar = QFrame()
    win._prompt_bar.setObjectName("runDecision")
    win._prompt_bar.setStyleSheet(
        f"QFrame#runDecision {{ background: {tokens['warning_bg']};"
        f" border-left: 3px solid {tokens['warning']}; border-radius: 6px; }}"
    )
    layout = QVBoxLayout(win._prompt_bar)
    layout.setContentsMargins(13, 8, 10, 8)
    layout.setSpacing(6)
    win._prompt_label = QLabel()
    win._prompt_label.setTextFormat(Qt.TextFormat.PlainText)
    win._prompt_label.setWordWrap(True)
    font = win._prompt_label.font()
    font.setPointSizeF(font.pointSizeF() + 2)
    font.setBold(True)
    win._prompt_label.setFont(font)
    layout.addWidget(win._prompt_label)

    win._prompt_detail = QLabel()
    win._prompt_detail.setTextFormat(Qt.TextFormat.PlainText)
    win._prompt_detail.setWordWrap(True)
    win._prompt_detail.setStyleSheet(f"color: {tokens['text']};")
    layout.addWidget(win._prompt_detail)

    actions = QHBoxLayout()
    actions.setSpacing(7)
    win._btn_prompt_yes = QPushButton("Yes")
    win._btn_prompt_no = QPushButton("No")
    win._btn_prompt_term = QPushButton("Answer in terminal")
    win._btn_prompt_yes.clicked.connect(lambda: win._answer_prompt("y"))
    win._btn_prompt_no.clicked.connect(lambda: win._answer_prompt("n"))
    win._btn_prompt_term.clicked.connect(win._prompt_to_terminal)

    win._prompt_input = QLineEdit()
    win._prompt_input.setMinimumWidth(90)
    win._prompt_input.setMaximumWidth(240)
    win._prompt_input.returnPressed.connect(win._send_prompt_text)
    win._btn_prompt_send = QPushButton("Send")
    win._btn_prompt_send.clicked.connect(win._send_prompt_text)
    set_primary(win._btn_prompt_send)
    win._btn_prompt_cancel = QPushButton("Cancel")
    win._btn_prompt_cancel.clicked.connect(lambda: win._answer_password(None))

    win._btn_retry = QPushButton("Retry step")
    win._btn_retry.clicked.connect(lambda: win._answer_retry("y"))
    set_primary(win._btn_retry)
    win._btn_skip = QPushButton("Skip step")
    win._btn_skip.clicked.connect(lambda: win._answer_retry("n"))
    win._btn_retry_more = QPushButton("More options")
    menu = QMenu(win._btn_retry_more)
    menu.addAction("Open a shell in the terminal", lambda: win._answer_retry("s"))
    menu.addAction("Quit Topgrade", lambda: win._answer_retry("q"))
    win._btn_retry_more.setMenu(menu)

    for button in (
        win._btn_prompt_yes,
        win._btn_prompt_no,
        win._prompt_input,
        win._btn_prompt_send,
        win._btn_prompt_term,
        win._btn_prompt_cancel,
        win._btn_retry,
        win._btn_skip,
        win._btn_retry_more,
    ):
        actions.addWidget(button)
    actions.addStretch()
    layout.addLayout(actions)
    win._prompt_bar.hide()
    return win._prompt_bar
