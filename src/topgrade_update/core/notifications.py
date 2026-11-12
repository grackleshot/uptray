"""Desktop notification handling with DBus and fallback."""

from __future__ import annotations

import contextlib
import subprocess
from collections.abc import Callable
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING, Any

from topgrade_update.core.checkers.facade import total_updates
from topgrade_update.core.logging import get_logger

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"
ICON_NAME = "topgrade-update"

_URGENCY_LEVELS = {"low": 0, "normal": 1, "critical": 2}


class NotificationClient:
    """Hybrid notification client: DBus via jeepney, fallback to notify-send."""

    def __init__(self) -> None:
        self._dbus_available = False
        self._bus: Any | None = None
        self._proxy: Any | None = None
        self._MatchRule: Any | None = None
        self._message_bus: Any | None = None
        self._action_handler: Callable[[str], None] | None = None
        self._action_lock = Lock()
        self._action_ready = Event()
        self._action_stop = Event()
        self._action_listener_thread: Thread | None = None
        self._action_listener_available = False
        self._last_id = 0  # replaces_id so each notification replaces the previous one
        try:
            from jeepney import DBusAddress, MatchRule, new_method_call
            from jeepney.bus_messages import message_bus
            from jeepney.io.blocking import open_dbus_connection

            self._open_dbus_connection = open_dbus_connection
            self._DBusAddress = DBusAddress
            self._new_method_call = new_method_call
            self._MatchRule = MatchRule
            self._message_bus = message_bus
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
                "/org/freedesktop/Notifications",
                bus_name="org.freedesktop.Notifications",
                interface="org.freedesktop.Notifications",
            )
            return True
        except Exception:
            self._bus = None
            self._proxy = None
            return False

    def start_action_listener(self, handler: Callable[[str], None]) -> bool:
        """Start listening for notification action signals in a daemon thread."""
        if not self._dbus_available:
            return False
        with self._action_lock:
            self._action_handler = handler
        thread = self._action_listener_thread
        if thread is not None and thread.is_alive():
            return True
        self._action_stop.clear()
        self._action_ready.clear()
        self._action_listener_available = False
        self._action_listener_thread = Thread(
            target=self._listen_for_actions,
            name="topgrade-notification-actions",
            daemon=True,
        )
        self._action_listener_thread.start()
        return True

    def _listen_for_actions(self) -> None:
        """Subscribe to ActionInvoked signals and dispatch their action IDs."""
        bus: Any | None = None
        try:
            if self._MatchRule is None or self._message_bus is None:
                return
            bus = self._open_dbus_connection()
            rule = self._MatchRule(
                type="signal",
                sender="org.freedesktop.Notifications",
                interface="org.freedesktop.Notifications",
                member="ActionInvoked",
                path="/org/freedesktop/Notifications",
            )
            bus.send_and_get_reply(self._message_bus.AddMatch(rule), timeout=3)
            with bus.filter(rule) as matches:
                self._action_listener_available = True
                self._action_ready.set()
                while not self._action_stop.is_set():
                    try:
                        message = bus.recv_until_filtered(matches, timeout=0.25)
                    except TimeoutError:
                        continue
                    if len(message.body) >= 2:
                        self._dispatch_action(str(message.body[1]))
        except Exception as exc:
            get_logger("notifications").warning("Notification actions unavailable: %s", exc)
            self._action_listener_available = False
        finally:
            self._action_ready.set()
            if bus is not None:
                with contextlib.suppress(Exception):
                    bus.close()

    def _dispatch_action(self, action_id: str) -> None:
        """Call the current action handler without letting it kill the listener."""
        with self._action_lock:
            handler = self._action_handler
        if handler is None:
            return
        try:
            handler(action_id)
        except Exception:
            get_logger("notifications").exception("Notification action handler failed")

    def _supports_actions(self) -> bool:
        """Ask the notification service whether it supports action buttons."""
        if self._bus is None or self._proxy is None:
            return False
        try:
            message = self._new_method_call(self._proxy, "GetCapabilities")
            reply = self._bus.send_and_get_reply(message, timeout=5)
            capabilities = reply.body[0] if reply.body else []
            return isinstance(capabilities, list) and "actions" in capabilities
        except Exception:
            return False

    def notify(
        self,
        summary: str,
        body: str,
        actions: list[tuple[str, str]] | None = None,
        *,
        on_action: Callable[[str], None] | None = None,
        urgency: str | None = None,
        sound: bool = False,
    ) -> int | None:
        """Show a notification. Returns notification ID or None.

        Args:
            summary: Notification title.
            body: Notification body text.
            actions: List of (action_id, label) tuples for action buttons.
            on_action: Called with the action ID when the user selects a button.
            urgency: Optional "low", "normal", or "critical" urgency level.
            sound: Request the notification server's default sound.

        Returns:
            Notification ID from DBus, or None if fallback was used.
        """
        normalized_urgency = urgency if urgency in _URGENCY_LEVELS else None
        if self._ensure_connection():
            if actions:
                if on_action is None:
                    actions = None
                else:
                    self.start_action_listener(on_action)
                    if not self._action_ready.wait(timeout=1.0):
                        self._notify_send(summary, body, normalized_urgency, sound)
                        return None
                    if not self._action_listener_available or not self._supports_actions():
                        self._notify_send(summary, body, normalized_urgency, sound)
                        return None
            return self._notify_dbus(summary, body, actions, normalized_urgency, sound)
        self._notify_send(summary, body, normalized_urgency, sound)
        return None

    def _notify_dbus(
        self,
        summary: str,
        body: str,
        actions: list[tuple[str, str]] | None = None,
        urgency: str | None = None,
        sound: bool = False,
    ) -> int | None:
        assert self._bus is not None and self._proxy is not None
        action_list: list[str] = []
        if actions:
            for action_id, label in actions:
                action_list.append(action_id)
                action_list.append(label)
        hints = self._build_hints(urgency, sound)
        msg = self._new_method_call(
            self._proxy,
            "Notify",
            "susssasa{sv}i",
            (
                APP_NAME,
                self._last_id,
                ICON_NAME,
                summary,
                body,
                action_list,
                hints,
                -1,  # expire_timeout (server default)
            ),
        )
        try:
            reply = self._bus.send_and_get_reply(msg, timeout=5)
            reply_body = getattr(reply, "body", ())
            if reply_body:
                self._last_id = int(reply_body[0])
                return self._last_id
            return None
        except Exception:
            self._notify_send(summary, body, urgency, sound)
            return None

    def _build_hints(self, urgency: str | None, sound: bool) -> dict[str, object]:
        """Build the DBus hints dict (jeepney infers variant types from values)."""
        hints: dict[str, object] = {}
        if urgency in _URGENCY_LEVELS:
            hints["urgency"] = _URGENCY_LEVELS[urgency]
        if sound:
            hints["sound-name"] = "message"
        return hints

    def _notify_send(
        self,
        summary: str,
        body: str,
        urgency: str | None = None,
        sound: bool = False,
    ) -> None:
        command = [
            "notify-send",
            "-a", APP_NAME,
            "-i", ICON_NAME,
        ]
        if urgency in _URGENCY_LEVELS:
            command.extend(["-u", urgency])
        if sound:
            command.extend(["-h", "string:sound-name:message"])
        command.extend([summary, body])
        with contextlib.suppress(FileNotFoundError):
            subprocess.Popen(command)

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
            bus.send_and_get_reply(msg, timeout=5)
        except Exception:
            pass

    def shutdown(self) -> None:
        """Stop the signal listener and close the notification bus connection."""
        self._action_stop.set()
        listener = self._action_listener_thread
        if listener is not None and listener.is_alive():
            listener.join(timeout=1)
        bus = self._bus
        self._bus = None
        self._proxy = None
        if bus is not None:
            with contextlib.suppress(Exception):
                bus.close()


def format_source_counts(results: list[CheckResult]) -> str:
    """Format per-source package update counts (reboot excluded), one per line."""
    parts: list[str] = []
    for r in results:
        if r.updates and r.source != "reboot":
            parts.append(f"  {r.source}: {len(r.updates)}")
    return "\n".join(parts)


def send_notification(
    results: list[CheckResult],
    actions: list[tuple[str, str]] | None = None,
    summary: str | None = None,
    body: str | None = None,
    *,
    on_action: Callable[[str], None] | None = None,
    client: NotificationClient | None = None,
    urgency: str | None = None,
    sound: bool = False,
) -> int | None:
    """Send a desktop notification summarising available updates.

    Args:
        results: List of check results from all sources.
        actions: Optional action buttons for DBus notifications.
        summary: Optional notification title override.
        body: Optional notification body override.
        on_action: Callback for a selected action button.
        client: Reusable client, usually owned by the tray applet.
        urgency: Optional "low", "normal", or "critical" urgency level.
        sound: Request the notification server's default sound.

    Returns:
        Notification ID if DBus was used, None otherwise.
    """
    total = total_updates(results)
    if total == 0:
        return None

    notification_summary = summary or f"{total} update(s) available"
    notification_body = body or format_source_counts(results)

    notification_client = client or NotificationClient()
    return notification_client.notify(
        notification_summary,
        notification_body,
        actions,
        on_action=on_action,
        urgency=urgency,
        sound=sound,
    )


def send_message(
    summary: str,
    body: str,
    *,
    urgency: str | None = None,
    sound: bool = False,
) -> int | None:
    """Send a desktop notification without requiring update results."""
    return NotificationClient().notify(summary, body, urgency=urgency, sound=sound)
