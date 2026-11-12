"""Embedded terminal: xterm.js via WebEngine, with a plain-text fallback."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QKeyEvent, QResizeEvent, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from collections.abc import Callable

_WEBENGINE_AVAILABLE = False
try:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except ImportError:
    QWebChannel = object  # type: ignore[misc, assignment]
    QWebEngineView = object  # type: ignore[misc, assignment]


def webengine_available() -> bool:
    """Return True when Qt WebEngine can host xterm.js."""
    return _WEBENGINE_AVAILABLE


class _Bridge(QObject):
    """JS → Python input bridge for xterm.js."""

    input_received = Signal(str)

    @Slot(str)
    def sendInput(self, data: str) -> None:  # noqa: N802 — JS API
        self.input_received.emit(data)


class TerminalWidget(QWidget):
    """PTY display surface with optional xterm.js rendering."""

    input_ready = Signal(str)
    ready = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_resize: Callable[[int, int], None] | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._use_web = _WEBENGINE_AVAILABLE
        self._view: QWebEngineView | None = None
        self._bridge: _Bridge | None = None
        self._term_ready = not self._use_web
        self._pending: list[str] = []
        self._fallback = QPlainTextEdit()
        # Read-only display; keystrokes go to the PTY (including Backspace).
        self._fallback.setReadOnly(True)
        self._fallback.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._fallback.setStyleSheet(
            "QPlainTextEdit { background: #1e1e1e; color: #ddd; font-family: monospace; }"
        )
        self._fallback.installEventFilter(self)

        if self._use_web:
            self._view = QWebEngineView(self)
            settings = self._view.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            self._bridge = _Bridge()
            self._bridge.input_received.connect(self.input_ready.emit)
            channel = QWebChannel(self._view.page())
            channel.registerObject("bridge", self._bridge)
            self._view.page().setWebChannel(channel)
            self._view.loadFinished.connect(self._on_load)
            layout.addWidget(self._view)
            self._fallback.hide()
            html = _asset_path("terminal.html")
            self._view.load(QUrl.fromLocalFile(str(html)))
        else:
            layout.addWidget(self._fallback)
            self.ready.emit()

    def set_resize_handler(self, callback: Callable[[int, int], None] | None) -> None:
        """Register a callback invoked with (rows, cols) after fit."""
        self._on_resize = callback

    def write(self, text: str) -> None:
        """Append PTY output, buffering until the WebEngine terminal is ready."""
        if self._view is not None and not self._term_ready:
            self._pending.append(text)
            return
        self._write_now(text)

    def clear(self) -> None:
        """Clear the display."""
        self._pending.clear()
        if self._view is not None:
            if self._term_ready:
                self._view.page().runJavaScript(
                    "window.termApi && window.termApi.clear()"
                )
            return
        self._fallback.clear()

    def _write_now(self, text: str) -> None:
        if self._view is not None:
            escaped = (
                text.replace("\\", "\\\\")
                .replace("`", "\\`")
                .replace("${", "\\${")
            )
            self._view.page().runJavaScript(
                f"window.termApi && window.termApi.write(`{escaped}`)"
            )
            return
        self._fallback.moveCursor(QTextCursor.MoveOperation.End)
        self._fallback.insertPlainText(text)

    def focus_terminal(self) -> None:
        """Focus the terminal for keyboard input."""
        if self._view is not None:
            self._view.setFocus()
            self._view.page().runJavaScript(
                "window.termApi && window.termApi.focus()"
            )
        else:
            self._fallback.setFocus()

    def _on_load(self, ok: bool) -> None:
        if not ok or self._view is None:
            return
        # Expose QWebChannel bridge to window.bridge
        self._view.page().runJavaScript(
            """
            new QWebChannel(qt.webChannelTransport, function(channel) {
              window.bridge = channel.objects.bridge;
            });
            """
        )
        self._term_ready = True
        pending = self._pending
        self._pending = []
        for chunk in pending:
            self._write_now(chunk)
        self.ready.emit()
        self._fit()

    def _fit(self) -> None:
        if self._view is None:
            return
        self._view.page().runJavaScript(
            "window.termApi && (window.termApi.fit(), "
            "[window.termApi.rows(), window.termApi.cols()])",
            self._apply_size,
        )

    def _apply_size(self, size: object) -> None:
        if not isinstance(size, list) or len(size) != 2 or self._on_resize is None:
            return
        rows, cols = size
        if isinstance(rows, int) and isinstance(cols, int):
            self._on_resize(rows, cols)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._view is not None:
            QTimer.singleShot(50, self._fit)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self._fallback and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            key = event.key()
            if key in {Qt.Key.Key_Backspace, Qt.Key.Key_Delete}:
                self.input_ready.emit("\x7f")
                return True
            if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                self.input_ready.emit("\r")
                return True
            text = event.text()
            if text and not event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
            ):
                self.input_ready.emit(text)
                return True
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier and text:
                # Forward Ctrl-C / Ctrl-D style bytes when present.
                self.input_ready.emit(text)
                return True
            return True
        return super().eventFilter(watched, event)


def _asset_path(name: str) -> Path:
    base = Path(__file__).resolve().parent / "assets" / "xterm"
    path = base / name
    if path.is_file():
        return path
    # Installed package fallback
    root = resources.files("uptray.gui.assets.xterm")
    return Path(str(root.joinpath(name)))
