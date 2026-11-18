"""Readable recent activity for the Simple run monitor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QFrame, QLabel, QPlainTextEdit, QVBoxLayout

from uptray.gui.style import tag_card

if TYPE_CHECKING:
    from uptray.gui.run_window import RunWindow


def build_simple_page(win: RunWindow, tokens: dict[str, str]) -> QFrame:
    """Build a compact log preview with wrapping and a stable viewport."""
    page = QFrame()
    tag_card(page)
    layout = QVBoxLayout(page)
    layout.setContentsMargins(16, 12, 16, 10)
    layout.setSpacing(4)

    heading = QLabel("Recent activity")
    heading_font = heading.font()
    heading_font.setPointSizeF(heading_font.pointSizeF() + 1)
    heading_font.setBold(True)
    heading.setFont(heading_font)
    layout.addWidget(heading)

    win._activity = QPlainTextEdit()
    win._activity.setReadOnly(True)
    win._activity.setAccessibleName("Recent activity")
    win._activity.setPlaceholderText("Activity will appear as Topgrade reports it.")
    win._activity.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    win._activity.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    win._activity.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    win._activity.setStyleSheet(
        f"background: transparent; color: {tokens['text']}; border: none; padding: 0;"
    )
    win._activity.setMinimumHeight(58)
    layout.addWidget(win._activity, 1)

    return page
