"""Best-effort KDE/Unity task manager progress for the installed desktop entry."""

from __future__ import annotations

from PySide6.QtDBus import QDBusConnection, QDBusMessage


class TaskProgress:
    """Publish current-operation progress; unavailable session buses are harmless."""

    def __init__(self) -> None:
        self._bus = QDBusConnection.sessionBus()
        self._last: float | None = None

    def update(self, fraction: float | None) -> None:
        """Show a known fraction, or remove the overlay when unknown/finished."""
        if fraction is not None:
            fraction = min(1.0, max(0.0, fraction))
        if fraction == self._last:
            return
        self._last = fraction
        if not self._bus.isConnected():
            return
        message = QDBusMessage.createSignal(
            "/com/canonical/Unity/LauncherEntry",
            "com.canonical.Unity.LauncherEntry",
            "Update",
        )
        message.setArguments([
            "application://uptray.desktop",
            {
                "progress-visible": fraction is not None,
                "progress": fraction or 0.0,
            },
        ])
        self._bus.send(message)
