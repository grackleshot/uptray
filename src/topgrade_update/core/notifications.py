"""Desktop notification handling with DBus and fallback."""

from __future__ import annotations

import contextlib
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"
ICON_NAME = "topgrade-update"


class NotificationClient:
    """Hybrid notification client: DBus via jeepney, fallback to notify-send."""

    def __init__(self) -> None:
        self._dbus_available = False
        self._bus: Any | None = None
        self._proxy: Any | None = None
        try:
            from jeepney import DBusAddress, new_method_call
            from jeepney.io.blocking import open_dbus_connection

            self._open_dbus_connection = open_dbus_connection
            self._DBusAddress = DBusAddress
            self._new_method_call = new_method_call
            self._dbus_available = True
        except ImportError:
            pass

    def _ensure_connection(self) -> bool:
        if not self._dbus_available:
            return False
        if self._bus is not None:
            return True
        try:
            self._bus = self._open_dbus_connection()
            self._proxy = self._DBusAddress(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications",
            )
            return True
        except Exception:
            self._bus = None
            self._proxy = None
            return False

    def notify(
        self,
        summary: str,
        body: str,
        actions: list[tuple[str, str]] | None = None,
    ) -> int | None:
        """Show a notification. Returns notification ID or None.

        Args:
            summary: Notification title.
            body: Notification body text.
            actions: List of (action_id, label) tuples for action buttons.

        Returns:
            Notification ID from DBus, or None if fallback was used.
        """
        if self._ensure_connection():
            return self._notify_dbus(summary, body, actions)
        self._notify_send(summary, body)
        return None

    def _notify_dbus(
        self,
        summary: str,
        body: str,
        actions: list[tuple[str, str]] | None = None,
    ) -> int | None:
        assert self._bus is not None and self._proxy is not None
        action_list: list[str] = []
        if actions:
            for action_id, label in actions:
                action_list.append(action_id)
                action_list.append(label)
        msg = self._new_method_call(
            self._proxy,
            "Notify",
            "susssasa{sv}i",
            (
                APP_NAME,
                0,  # replaces_id
                ICON_NAME,
                summary,
                body,
                action_list,
                {},  # hints
                -1,  # expire_timeout (server default)
            ),
        )
        try:
            reply = self._bus.send_and_get_reply(msg)
            return reply[0] if reply else None
        except Exception:
            self._notify_send(summary, body)
            return None

    def _notify_send(self, summary: str, body: str) -> None:
        with contextlib.suppress(FileNotFoundError):
            subprocess.Popen(
                [
                    "notify-send",
                    "-a", APP_NAME,
                    "-i", ICON_NAME,
                    summary,
                    body,
                ]
            )

    def close(self, notification_id: int) -> None:
        """Close a notification by ID."""
        if not self._ensure_connection():
            return
        bus = self._bus
        proxy = self._proxy
        if bus is None or proxy is None:
            return
        try:
            msg = self._new_method_call(
                proxy,
                "CloseNotification",
                "u",
                (notification_id,),
            )
            bus.send_and_get_reply(msg)
        except Exception:
            pass


def _format_body(results: list[CheckResult]) -> str:
    """Format check results into a notification body."""
    parts: list[str] = []
    for r in results:
        if r.updates:
            parts.append(f"  {r.source}: {len(r.updates)}")
    return "\n".join(parts)


def send_notification(
    results: list[CheckResult],
    actions: list[tuple[str, str]] | None = None,
) -> int | None:
    """Send a desktop notification summarising available updates.

    Args:
        results: List of check results from all sources.
        actions: Optional action buttons for DBus notifications.

    Returns:
        Notification ID if DBus was used, None otherwise.
    """
    total = sum(len(r.updates) for r in results)
    if total == 0:
        return None

    summary = f"{total} update(s) available"
    body = _format_body(results)

    client = NotificationClient()
    return client.notify(summary, body, actions)
