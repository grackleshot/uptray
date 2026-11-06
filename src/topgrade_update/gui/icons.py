"""Programmatic icon generation for the system tray."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap, QPolygonF

_SIZE = 64

# Okabe-Ito colorblind-safe palette alongside the default colors.
_PALETTES: dict[str, dict[str, str]] = {
    "default": {
        "idle": "#78909c",
        "checking": "#ffa726",
        "uptodate": "#66bb6a",
        "updates": "#42a5f5",
        "badge": "#e53935",
        "reboot": "#7e57c2",
    },
    "colorblind": {
        "idle": "#999999",
        "checking": "#e69f00",
        "uptodate": "#009e73",
        "updates": "#0072b2",
        "badge": "#e69f00",
        "reboot": "#cc79a7",
    },
}


class IconCache:
    """Cache for generated tray icons to avoid repeated pixmap creation."""

    def __init__(self, style: str = "default") -> None:
        """Create an icon cache using the named palette style."""
        self._style = style if style in _PALETTES else "default"
        self._colors = _PALETTES[self._style]
        self._idle: QIcon | None = None
        self._checking: QIcon | None = None
        self._uptodate: QIcon | None = None
        self._reboot: QIcon | None = None
        self._updates: dict[str, QIcon] = {}

    @property
    def style(self) -> str:
        """Return the active palette name."""
        return self._style

    def idle(self) -> QIcon:
        """Return the idle-state icon."""
        if self._idle is None:
            self._idle = _make_icon(self._colors["idle"])
        return self._idle

    def checking(self) -> QIcon:
        """Return the checking-state icon."""
        if self._checking is None:
            self._checking = _make_icon(self._colors["checking"])
        return self._checking

    def uptodate(self) -> QIcon:
        """Return the up-to-date icon."""
        if self._uptodate is None:
            self._uptodate = _make_icon(self._colors["uptodate"])
        return self._uptodate

    def reboot(self) -> QIcon:
        """Return the reboot-required icon."""
        if self._reboot is None:
            self._reboot = _make_icon(self._colors["reboot"], glyph="reboot")
        return self._reboot

    def updates(self, count: int) -> QIcon:
        """Return an updates-available icon with a badge count."""
        key = str(count) if count < 100 else "99+"
        if key not in self._updates:
            self._updates[key] = _make_icon(
                self._colors["updates"], key, self._colors["badge"]
            )
        return self._updates[key]


def _make_icon(
    color: str,
    badge_text: str = "",
    badge_color: str = "",
    glyph: str = "arrow",
) -> QIcon:
    """Create a 64×64 icon with a coloured circle, glyph, and optional badge."""
    pix = QPixmap(_SIZE, _SIZE)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Main circle
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, _SIZE - 4, _SIZE - 4)

    p.setBrush(QColor("#ffffff"))
    cx, cy = _SIZE / 2, _SIZE / 2
    if glyph == "reboot":
        # Circular-arrows style reboot hint drawn from arc segments.
        _draw_reboot_glyph(p, cx, cy)
    else:
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


def _draw_reboot_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a two-segment circular arrow suggesting a restart."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QPen

    radius = 14.0
    pen = QPen(QColor("#ffffff"), 4)
    pen.setCapStyle(_Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
    p.drawArc(rect, 30 * 16, 120 * 16)
    p.drawArc(rect, 210 * 16, 120 * 16)

    # Arrowheads at each arc end.
    p.setPen(_Qt.PenStyle.NoPen)
    head_a = QPolygonF(
        [
            QPointF(cx + radius * 0.87, cy - radius * 0.5),
            QPointF(cx + radius * 0.4, cy - radius * 0.75),
            QPointF(cx + radius * 0.75, cy - radius * 0.05),
        ]
    )
    head_b = QPolygonF(
        [
            QPointF(cx - radius * 0.87, cy + radius * 0.5),
            QPointF(cx - radius * 0.4, cy + radius * 0.75),
            QPointF(cx - radius * 0.75, cy + radius * 0.05),
        ]
    )
    p.drawPolygon(head_a)
    p.drawPolygon(head_b)
