"""Programmatic icon generation for the system tray and dialogs.

Every status is encoded by shape as well as color (arrow / clock / check /
cross / dash / ring / restart arrows) so tray and step states stay readable
without relying on hue alone.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)

from uptray.gui.style import colors

_SIZE = 64

# Icon size tokens shared by every window (keep the scale small and consistent).
ICON_SM = 16
ICON_MD = 24
ICON_LG = 32
ICON_XL = 48

# Okabe-Ito colorblind-safe palette alongside the default colors.
_PALETTES: dict[str, dict[str, str]] = {
    "default": {
        "idle": "#78909c",
        "checking": "#ffa726",
        "uptodate": "#66bb6a",
        "updates": "#42a5f5",
        "badge": "#e53935",
        "reboot": "#7e57c2",
        "error": "#e53935",
    },
    "colorblind": {
        "idle": "#999999",
        "checking": "#e69f00",
        "uptodate": "#009e73",
        "updates": "#0072b2",
        "badge": "#e69f00",
        "reboot": "#cc79a7",
        "error": "#d55e00",
    },
}

# Tray state -> (palette token, glyph).
_TRAY_KINDS: dict[str, tuple[str, str]] = {
    "idle": ("idle", "blank"),
    "checking": ("checking", "clock"),
    "uptodate": ("uptodate", "check"),
    "updates": ("updates", "arrow"),
    "reboot": ("reboot", "reboot"),
    "error": ("error", "cross"),
}

# In-window status kinds -> (theme token, glyph).
_STATUS_KINDS: dict[str, tuple[str, str]] = {
    "pending": ("muted", "ring"),
    "running": ("accent", "clock"),
    "done": ("success", "check"),
    "failed": ("danger", "cross"),
    "skipped": ("muted", "dash"),
    "warning": ("warning", "triangle"),
}


class IconCache:
    """Cache for generated tray icons to avoid repeated pixmap creation."""

    def __init__(self, style: str = "default") -> None:
        """Create an icon cache using the named palette style."""
        self._style = style if style in _PALETTES else "default"
        self._colors = _PALETTES[self._style]
        self._cache: dict[str, QIcon] = {}
        self._updates: dict[str, QIcon] = {}

    @property
    def style(self) -> str:
        """Return the active palette name."""
        return self._style

    def idle(self) -> QIcon:
        """Return the idle-state icon (plain dot, no glyph)."""
        return self._tray_icon("idle")

    def checking(self) -> QIcon:
        """Return the checking-state icon (clock glyph)."""
        return self._tray_icon("checking")

    def uptodate(self) -> QIcon:
        """Return the up-to-date icon (checkmark glyph)."""
        return self._tray_icon("uptodate")

    def reboot(self) -> QIcon:
        """Return the reboot-required icon (restart arrows glyph)."""
        return self._tray_icon("reboot")

    def error(self) -> QIcon:
        """Return the check-failed icon (cross glyph)."""
        return self._tray_icon("error")

    def updates(self, count: int) -> QIcon:
        """Return an updates-available icon with a badge count."""
        key = str(count) if count < 100 else "99+"
        if key not in self._updates:
            color, glyph = _TRAY_KINDS["updates"]
            self._updates[key] = _make_icon(
                self._colors[color],
                key,
                self._colors["badge"],
                glyph=glyph,
            )
        return self._updates[key]

    def _tray_icon(self, kind: str) -> QIcon:
        if kind not in self._cache:
            color, glyph = _TRAY_KINDS[kind]
            self._cache[kind] = _make_icon(self._colors[color], glyph=glyph)
        return self._cache[kind]


def status_pixmap(kind: str, size: int = ICON_SM) -> QPixmap:
    """Return a small status icon (pending/running/done/failed/skipped/warning)."""
    tokens = colors()
    color, glyph = _STATUS_KINDS.get(kind, ("muted", "ring"))
    return _make_icon(tokens[color], glyph=glyph).pixmap(size)


_SPINNER_FRAMES = 8
_spinner_cache: dict[int, list[QPixmap]] = {}


def spinner_pixmaps(size: int = ICON_MD) -> list[QPixmap]:
    """Return rotation frames for a gentle activity spinner (accent color)."""
    cached = _spinner_cache.get(size)
    if cached is not None:
        return cached
    tokens = colors()
    frames: list[QPixmap] = []
    for frame in range(_SPINNER_FRAMES):
        pix = QPixmap(size, size)
        pix.fill(QColor(0, 0, 0, 0))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(tokens["accent"]), max(2.0, size / 12))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        inset = size * 0.12
        rect = QRectF(inset, inset, size - inset * 2, size - inset * 2)
        start = 90 * 16 - frame * (360 * 16 // _SPINNER_FRAMES)
        p.drawArc(rect, start, 270 * 16)
        p.end()
        frames.append(pix)
    _spinner_cache[size] = frames
    return frames


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
    elif glyph == "check":
        _draw_check_glyph(p, cx, cy)
    elif glyph == "cross":
        _draw_cross_glyph(p, cx, cy)
    elif glyph == "clock":
        _draw_clock_glyph(p, cx, cy)
    elif glyph == "ring":
        _draw_ring_glyph(p, cx, cy)
    elif glyph == "dash":
        _draw_dash_glyph(p, cx, cy)
    elif glyph == "triangle":
        _draw_triangle_glyph(p, cx, cy, QColor(color))
    elif glyph == "arrow":
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
    # glyph == "blank": no glyph, plain disc.

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


def _white_pen(width: float) -> QPen:
    pen = QPen(QColor("#ffffff"), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_check_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a bold checkmark for the up-to-date/done state."""
    p.setPen(_white_pen(6))
    path = QPainterPath()
    path.moveTo(cx - 12, cy + 1)
    path.lineTo(cx - 3, cy + 10)
    path.lineTo(cx + 13, cy - 10)
    p.drawPath(path)


def _draw_cross_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a bold cross for the failed state."""
    p.setPen(_white_pen(6))
    path = QPainterPath()
    path.moveTo(cx - 10, cy - 10)
    path.lineTo(cx + 10, cy + 10)
    path.moveTo(cx + 10, cy - 10)
    path.lineTo(cx - 10, cy + 10)
    p.drawPath(path)


def _draw_clock_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a clock face for the checking/running state."""
    p.setPen(_white_pen(5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    radius = 15.0
    p.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))
    # Hands: centre -> 12 o'clock -> ~4 o'clock.
    path = QPainterPath()
    path.moveTo(cx, cy)
    path.lineTo(cx, cy - 9)
    path.lineTo(cx + 7, cy + 4)
    p.drawPath(path)


def _draw_ring_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a hollow circle for the pending state."""
    p.setPen(_white_pen(5))
    p.setBrush(Qt.BrushStyle.NoBrush)
    radius = 13.0
    p.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))


def _draw_dash_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a horizontal dash for the skipped state."""
    p.setPen(_white_pen(6))
    p.drawLine(QPointF(cx - 11, cy), QPointF(cx + 11, cy))


def _draw_triangle_glyph(p: QPainter, cx: float, cy: float, disc: QColor) -> None:
    """Draw a warning triangle; body white, exclamation punched in the disc."""
    p.setPen(Qt.PenStyle.NoPen)
    triangle = QPolygonF(
        [
            QPointF(cx, cy - 15),
            QPointF(cx - 15, cy + 11),
            QPointF(cx + 15, cy + 11),
        ]
    )
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(triangle)
    # Exclamation mark drawn in the disc color so it reads inside the triangle.
    pen = QPen(disc, 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(cx, cy - 7)
    path.lineTo(cx, cy + 2)
    p.drawPath(path)
    p.setBrush(disc)
    p.drawEllipse(QRectF(cx - 2, cy + 5, 4, 4))


def _draw_reboot_glyph(p: QPainter, cx: float, cy: float) -> None:
    """Draw a two-segment circular arrow suggesting a restart."""
    radius = 14.0
    pen = QPen(QColor("#ffffff"), 4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
    p.drawArc(rect, 30 * 16, 120 * 16)
    p.drawArc(rect, 210 * 16, 120 * 16)

    # Arrowheads at each arc end.
    p.setPen(Qt.PenStyle.NoPen)
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
