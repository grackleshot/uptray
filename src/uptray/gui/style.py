"""Shared visual theme: color tokens and a global stylesheet.

Every top-level window applies :func:`apply_theme` so the whole app —
dialogs, run window, tray menu — shares one modern, flat look. Tokens
adapt to the desktop theme (light or dark) via the active Qt palette.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QSplitter, QWidget

if TYPE_CHECKING:
    from collections.abc import Mapping

# Semantic token names shared by both themes.
_TOKEN_NAMES = (
    "bg",
    "card",
    "card2",
    "border",
    "text",
    "muted",
    "accent",
    "accent_text",
    "success",
    "success_bg",
    "danger",
    "danger_bg",
    "warning",
    "warning_bg",
)

_LIGHT: Mapping[str, str] = {
    "bg": "#f4f5f7",
    "card": "#ffffff",
    "card2": "#eef0f3",
    "border": "#dfe3e8",
    "text": "#1c2128",
    "muted": "#66707b",
    "accent": "#2f6fdb",
    "accent_text": "#ffffff",
    "success": "#1a7f4b",
    "success_bg": "#e6f4ec",
    "danger": "#c93c37",
    "danger_bg": "#fbeaea",
    "warning": "#946200",
    "warning_bg": "#fdf3df",
}

_DARK: Mapping[str, str] = {
    "bg": "#191b1f",
    "card": "#212429",
    "card2": "#2b2f35",
    "border": "#343940",
    "text": "#e3e6ea",
    "muted": "#98a1ab",
    "accent": "#5b93ea",
    # Dark ink on the lighter dark-theme accent keeps AA contrast (>= 4.5:1).
    "accent_text": "#101828",
    "success": "#46b881",
    "success_bg": "#1e2c24",
    "danger": "#e56762",
    "danger_bg": "#2e1f21",
    "warning": "#d9a441",
    "warning_bg": "#2c2517",
}


def is_dark_theme(app: QApplication | None = None) -> bool:
    """Return True when the active palette uses a dark window color."""
    application = app or QApplication.instance()
    if application is None:
        return False
    palette = cast(QApplication, application).palette()
    luminance = palette.color(QPalette.ColorRole.Window).lightness()
    return luminance < 128


def colors(app: QApplication | None = None) -> dict[str, str]:
    """Return the theme tokens for the active light/dark palette."""
    base = _DARK if is_dark_theme(app) else _LIGHT
    return dict(base)


def _build_qss(tokens: Mapping[str, str]) -> str:
    """Compose the application stylesheet from theme tokens."""
    t = tokens
    return f"""
    QDialog, QMainWindow {{
        background: {t['bg']};
    }}
    QLabel {{
        color: {t['text']};
        background: transparent;
    }}
    QFrame[card="true"] {{
        background: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 10px;
    }}
    QGroupBox {{
        background: {t['card']};
        border: 1px solid {t['border']};
        border-radius: 10px;
        margin-top: 16px;
        padding: 14px 12px 10px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 4px;
        color: {t['text']};
    }}
    QPushButton {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 6px;
        padding: 6px 14px;
        min-height: 18px;
    }}
    QPushButton:hover {{
        border-color: {t['accent']};
    }}
    QPushButton:focus {{
        /* 2px WCAG-visible focus ring; padding shrinks to avoid layout shift. */
        border: 2px solid {t['accent']};
        padding: 5px 13px;
    }}
    QPushButton[class="primary"]:focus {{
        border: 2px solid {t['text']};
        padding: 5px 13px;
    }}
    QPushButton:pressed {{
        background: {t['card2']};
    }}
    QPushButton:disabled {{
        color: {t['muted']};
        border-color: {t['border']};
    }}
    QPushButton[class="primary"] {{
        background: {t['accent']};
        color: {t['accent_text']};
        border: 1px solid {t['accent']};
        font-weight: 600;
    }}
    QPushButton[class="primary"]:hover {{
        background: {t['accent']};
        border-color: {t['accent']};
    }}
    QPushButton[class="primary"]:pressed {{
        background: {t['accent']};
    }}
    QPushButton[class="primary"]:disabled {{
        background: {t['card2']};
        color: {t['muted']};
        border-color: {t['border']};
    }}
    QPushButton[class="danger"] {{
        color: {t['danger']};
        border-color: {t['danger']};
        font-weight: 600;
    }}
    QPushButton[class="danger"]:hover {{
        background: {t['danger_bg']};
        border-color: {t['danger']};
    }}
    QPushButton:checked {{
        background: {t['accent']};
        color: {t['accent_text']};
        border-color: {t['accent']};
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 6px;
        padding: 5px 8px;
        min-height: 18px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 2px solid {t['accent']};
        padding: 4px 7px;
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {t['muted']};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 6px;
        selection-background-color: {t['accent']};
        selection-color: {t['accent_text']};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        border: none;
        width: 16px;
    }}
    QTreeWidget, QListWidget {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 4px;
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: 4px 2px;
    }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {t['accent']};
        color: {t['accent_text']};
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{
        background: {t['card2']};
    }}
    QHeaderView::section {{
        background: transparent;
        color: {t['muted']};
        border: none;
        border-bottom: 1px solid {t['border']};
        padding: 6px 4px;
        font-weight: 600;
    }}
    QProgressBar {{
        background: {t['card2']};
        border: none;
        border-radius: 4px;
        min-height: 8px;
        max-height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background: {t['accent']};
        border-radius: 4px;
    }}
    QSplitter::handle {{
        background: transparent;
    }}
    QSplitter::handle:horizontal {{
        width: 8px;
    }}
    QMenu {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 10px;
        border-radius: 6px;
        background: transparent;
    }}
    QMenu::item:selected {{
        background: {t['accent']};
        color: {t['accent_text']};
    }}
    QMenu::item:disabled {{
        color: {t['muted']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t['border']};
        margin: 6px 4px;
    }}
    QMenu::icon {{
        padding-left: 8px;
    }}
    QToolTip {{
        background: {t['card']};
        color: {t['text']};
        border: 1px solid {t['border']};
        padding: 4px 6px;
        border-radius: 4px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t['border']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['muted']};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {t['border']};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {t['muted']};
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0;
        height: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
    }}
    QCheckBox {{
        color: {t['text']};
        spacing: 8px;
    }}
    QCheckBox:disabled {{
        color: {t['muted']};
    }}
    """


def apply_theme(widget: QWidget, app: QApplication | None = None) -> None:
    """Style *widget* (and its children) with the shared application theme."""
    widget.setStyleSheet(_build_qss(colors(app)))


def apply_app_theme(app: QApplication) -> None:
    """Apply the shared theme to an entire application (all windows/menus)."""
    app.setStyleSheet(_build_qss(colors(app)))


def repaint_marked_buttons(widget: QWidget) -> None:
    """Re-polish buttons carrying a ``class`` property so QSS re-applies."""
    for button in widget.findChildren(QWidget):
        if button.property("class") is not None:
            button.style().unpolish(button)
            button.style().polish(button)


def set_primary(button: QWidget) -> None:
    """Mark *button* as the accent-colored primary action."""
    button.setProperty("class", "primary")
    if button.style() is not None:
        button.style().unpolish(button)
        button.style().polish(button)


def set_danger(button: QWidget) -> None:
    """Mark *button* as a destructive action."""
    button.setProperty("class", "danger")
    if button.style() is not None:
        button.style().unpolish(button)
        button.style().polish(button)


def tag_card(frame: QWidget) -> None:
    """Flag *frame* with the ``card`` QSS attribute."""
    frame.setProperty("card", True)
    if frame.style() is not None:
        frame.style().unpolish(frame)
        frame.style().polish(frame)


def text_color(name: str, app: QApplication | None = None) -> QColor:
    """Return a QColor for a named theme token."""
    return QColor(colors(app)[name])


def save_window_state(widget: QWidget | None, key: str, *splitters: QSplitter) -> None:
    """Remember a window's geometry and its splitters' sizes under ``key``."""
    settings = QSettings("uptray", "uptray")
    if widget is not None:
        settings.setValue(f"{key}/geometry", widget.saveGeometry())
    for i, splitter in enumerate(splitters):
        settings.setValue(f"{key}/splitter{i}", splitter.saveState())


def restore_window_state(widget: QWidget | None, key: str, *splitters: QSplitter) -> bool:
    """Restore what :func:`save_window_state` stored; True if everything was found."""
    settings = QSettings("uptray", "uptray")
    ok = True
    if widget is not None:
        geometry = settings.value(f"{key}/geometry")
        ok = geometry is not None and widget.restoreGeometry(geometry)
    for i, splitter in enumerate(splitters):
        state = settings.value(f"{key}/splitter{i}")
        ok = (state is not None and splitter.restoreState(state)) and ok
    return ok
