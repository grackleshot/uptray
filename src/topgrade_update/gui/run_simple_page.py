"""Simple-view page of the run window (big status hero + recovery row)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from topgrade_update.gui.icons import ICON_XL, status_pixmap
from topgrade_update.gui.style import set_primary

if TYPE_CHECKING:
    from topgrade_update.gui.run_window import RunWindow


def build_simple_page(win: RunWindow, tokens: dict[str, str]) -> QWidget:
    """Build the Simple page, attaching its widgets to ``win`` as before."""
    simple_page = QWidget()
    simple_layout = QVBoxLayout(simple_page)
    simple_layout.setContentsMargins(24, 32, 24, 24)
    simple_layout.setSpacing(10)
    simple_layout.addStretch(2)
    win._big_icon = QLabel()
    win._big_icon.setPixmap(status_pixmap("running", ICON_XL))
    win._big_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    simple_layout.addWidget(win._big_icon)
    win._big_title = QLabel("Updating your computer…")
    big_font = win._big_title.font()
    big_font.setPointSizeF(big_font.pointSizeF() + 7)
    big_font.setBold(True)
    win._big_title.setFont(big_font)
    win._big_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    simple_layout.addWidget(win._big_title)
    win._big_subtitle = QLabel(
        f'<span style="color:{tokens["muted"]}">'
        "This may take a few minutes. You can keep working."
        "</span>"
    )
    win._big_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    simple_layout.addWidget(win._big_subtitle)
    simple_layout.addSpacing(8)
    win._activity_label = QLabel("")
    win._activity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    win._activity_label.setStyleSheet(
        f"color: {tokens['muted']};"
        f" font-family: '{mono}';"
    )
    simple_layout.addWidget(win._activity_label)

    # Recovery row: error states must always offer a way forward.
    win._hero_actions = QWidget()
    hero_row = QHBoxLayout(win._hero_actions)
    hero_row.setSpacing(8)
    hero_row.addStretch()
    win._btn_try_again = QPushButton("Try again")
    set_primary(win._btn_try_again)
    win._btn_try_again.clicked.connect(win._try_again)
    hero_row.addWidget(win._btn_try_again)
    hero_row.addStretch()
    win._hero_actions.hide()
    simple_layout.addWidget(win._hero_actions)
    simple_layout.addStretch(3)
    return simple_page
