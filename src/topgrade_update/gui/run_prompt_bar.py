"""Run-window prompt strip: surfaces questions the running command asks."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

from topgrade_update.gui.icons import ICON_SM, status_pixmap

if TYPE_CHECKING:
    from topgrade_update.gui.run_window import RunWindow


def build_prompt_bar(win: RunWindow, tokens: dict[str, str]) -> QFrame:
    """Build the (hidden) prompt strip, attaching its widgets to ``win``.

    Yes/No for [Y/n] questions, a text box for menu prompts, and an
    "Answer in terminal" escape hatch.
    """
    win._prompt_bar = QFrame()
    win._prompt_bar.setStyleSheet(
        f"QFrame {{ background: {tokens['warning_bg']};"
        f" border: 1px solid {tokens['warning']}; border-radius: 8px; }}"
        "QLabel { background: transparent; border: none; }"
        "QPushButton { background: transparent; }"
    )
    prompt_layout = QHBoxLayout(win._prompt_bar)
    prompt_layout.setContentsMargins(12, 8, 12, 8)
    prompt_layout.setSpacing(8)
    prompt_icon = QLabel()
    prompt_icon.setPixmap(status_pixmap("warning", ICON_SM))
    prompt_layout.addWidget(prompt_icon)
    win._prompt_label = QLabel("")
    win._prompt_label.setWordWrap(True)
    prompt_layout.addWidget(win._prompt_label, 1)
    win._btn_prompt_yes = QPushButton("Yes")
    win._btn_prompt_no = QPushButton("No")
    win._btn_prompt_term = QPushButton("Answer in terminal")
    win._btn_prompt_yes.clicked.connect(lambda: win._answer_prompt("y"))
    win._btn_prompt_no.clicked.connect(lambda: win._answer_prompt("n"))
    win._btn_prompt_term.clicked.connect(
        functools.partial(win._answer_prompt, None)
    )
    win._prompt_input = QLineEdit()
    win._prompt_input.setPlaceholderText("Type your answer…")
    win._prompt_input.setMaximumWidth(220)
    win._prompt_input.returnPressed.connect(win._send_prompt_text)
    win._btn_prompt_send = QPushButton("Send")
    win._btn_prompt_send.clicked.connect(win._send_prompt_text)
    prompt_layout.addWidget(win._btn_prompt_yes)
    prompt_layout.addWidget(win._btn_prompt_no)
    prompt_layout.addWidget(win._prompt_input)
    prompt_layout.addWidget(win._btn_prompt_send)
    prompt_layout.addWidget(win._btn_prompt_term)
    win._prompt_bar.hide()
    return win._prompt_bar
