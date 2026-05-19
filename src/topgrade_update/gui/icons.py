"""Programmatic icon generation for the system tray."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF

_SIZE = 64


class IconCache:
    """Cache for generated tray icons to avoid repeated pixmap creation."""

    def __init__(self) -> None:
        self._idle: QIcon | None = None
        self._checking: QIcon | None = None
        self._uptodate: QIcon | None = None
        self._updates: dict[str, QIcon] = {}

    def idle(self) -> QIcon:
        """Return the idle-state icon."""
        if self._idle is None:
            self._idle = _make_icon("#78909c")
        return self._idle

    def checking(self) -> QIcon:
        """Return the checking-state icon."""
        if self._checking is None:
            self._checking = _make_icon("#ffa726")
        return self._checking

    def uptodate(self) -> QIcon:
        """Return the up-to-date icon."""
        if self._uptodate is None:
            self._uptodate = _make_icon("#66bb6a")
        return self._uptodate

    def updates(self, count: int) -> QIcon:
        """Return an updates-available icon with a badge count."""
        key = str(count) if count < 100 else "99+"
        if key not in self._updates:
            self._updates[key] = _make_icon("#42a5f5", key, "#e53935")
        return self._updates[key]


def _make_icon(color: str, badge_text: str = "", badge_color: str = "") -> QIcon:
    """Create a 64×64 icon with a coloured circle, arrow, and optional badge."""
    pix = QPixmap(_SIZE, _SIZE)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Main circle
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)

    # Arrow
    p.setBrush(QColor("#ffffff"))
    cx, cy = _SIZE / 2, _SIZE / 2
    arrow = QPolygonF(
        [
            QPointF(cx, cy - 16),
            QPointF(cx - 10, cy - 2),
            QPointF(cx - 5, cy - 2),
            QPointF(cx - 5, cy + 12),
            QPointF(cx + 5, cy + 12),
            QPointF(cx + 5, cy - 2),
            QPointF(cx + 10, cy - 2),
        ]
    )
    p.drawPolygon(arrow)

    # Badge
    if badge_text and badge_color:
        badge_r = 14
        bx, by = _SIZE - badge_r - 1, badge_r + 1
        p.setBrush(QColor(badge_color))
        p.drawEllipse(QRectF(bx - badge_r, by - badge_r, badge_r * 2, badge_r * 2))
        p.setPen(QColor("#ffffff"))
        font = QFont("sans-serif", 12, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(
            QRectF(bx - badge_r, by - badge_r, badge_r * 2, badge_r * 2),
            Qt.AlignmentFlag.AlignCenter,
            badge_text,
        )

    p.end()
    return QIcon(pix)
