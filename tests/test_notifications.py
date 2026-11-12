"""Tests for DBus notification actions and fallback behavior."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from uptray.core.notifications import NotificationClient


class FakeBus:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def send_and_get_reply(self, message: object, **_kwargs: object) -> SimpleNamespace:
        self.calls.append(message)
        return SimpleNamespace(body=(731,))


def _make_dbus_client() -> tuple[NotificationClient, FakeBus, list[tuple[object, ...]]]:
    client = NotificationClient()
    bus = FakeBus()
    calls: list[tuple[object, ...]] = []
    client._dbus_available = True
    client._bus = bus
    client._proxy = object()
    client._new_method_call = lambda *args: calls.append(args) or "dbus-message"
    client.start_action_listener = lambda _handler: True
    client._action_ready.set()
    client._action_listener_available = True
    return client, bus, calls


def test_notify_sends_action_buttons_and_returns_notification_id() -> None:
    client, bus, calls = _make_dbus_client()
    client._supports_actions = lambda: True
    handler = Mock()
    actions = [("run_topgrade", "Run Topgrade"), ("dismiss", "Dismiss")]

    notification_id = client.notify("Updates", "2 available", actions, on_action=handler)

    assert notification_id == 731
    assert calls[0][1] == "Notify"
    assert calls[0][3][5] == ["run_topgrade", "Run Topgrade", "dismiss", "Dismiss"]
    assert bus.calls == ["dbus-message"]


def test_notify_passes_urgency_and_sound_hints() -> None:
    client, _bus, calls = _make_dbus_client()

    client.notify("Reboot required", "Please reboot", urgency="critical", sound=True)

    assert calls[0][3][6] == {"urgency": 2, "sound-name": "message"}


def test_notify_ignores_unknown_urgency() -> None:
    client, _bus, calls = _make_dbus_client()

    client.notify("Hello", "World", urgency="bogus")

    assert calls[0][3][6] == {}


def test_notify_send_fallback_includes_urgency_flag(monkeypatch) -> None:  # noqa: ANN001
    client = NotificationClient()
    popen = Mock()
    monkeypatch.setattr("uptray.core.notifications.subprocess.Popen", popen)

    client.notify("Reboot required", "Please reboot", urgency="critical")

    command = popen.call_args.args[0]
    assert "-u" in command
    assert command[command.index("-u") + 1] == "critical"


def test_notify_falls_back_without_action_support(monkeypatch) -> None:
    client, _bus, _calls = _make_dbus_client()
    client._supports_actions = lambda: False
    notify_send = Mock()
    monkeypatch.setattr(client, "_notify_send", notify_send)

    result = client.notify(
        "Updates",
        "2 available",
        [("run_topgrade", "Run Topgrade")],
        on_action=Mock(),
    )

    assert result is None
    notify_send.assert_called_once_with("Updates", "2 available", None, False)


def test_action_listener_dispatches_action_invoked_signal() -> None:
    client = NotificationClient()
    signal_bus = SimpleNamespace(added_rule=None)
    received: list[str] = []

    class FakeSignalBus:
        def send_and_get_reply(self, message: object, **_kwargs: object) -> None:
            signal_bus.added_rule = message

        @contextmanager
        def filter(self, rule: object):
            yield []

        def recv_until_filtered(self, _matches: list[object], **_kwargs: object):
            return SimpleNamespace(body=(19, "snooze"))

        def close(self) -> None:
            pass

    def handle_action(action_id: str) -> None:
        received.append(action_id)
        client._action_stop.set()

    client._open_dbus_connection = FakeSignalBus
    client._MatchRule = lambda **_kwargs: "action-rule"
    client._message_bus = SimpleNamespace(AddMatch=lambda rule: ("AddMatch", rule))
    client._action_handler = handle_action

    client._listen_for_actions()

    assert signal_bus.added_rule == ("AddMatch", "action-rule")
    assert client._action_listener_available is True
    assert received == ["snooze"]


def test_jeepney_builds_action_and_subscription_messages() -> None:
    pytest.importorskip("jeepney")
    from jeepney import DBusAddress, MatchRule
    from jeepney.bus_messages import message_bus

    client = NotificationClient()
    assert client._dbus_available is True
    client._proxy = DBusAddress(
        "/org/freedesktop/Notifications",
        "org.freedesktop.Notifications",
        "org.freedesktop.Notifications",
    )
    client._bus = FakeBus()

    notification_id = client._notify_dbus(
        "Updates",
        "2 available",
        [("run_topgrade", "Run Topgrade"), ("dismiss", "Dismiss")],
    )
    rule = MatchRule(
        type="signal",
        sender="org.freedesktop.Notifications",
        interface="org.freedesktop.Notifications",
        member="ActionInvoked",
        path="/org/freedesktop/Notifications",
    )
    subscription = message_bus.AddMatch(rule)

    assert notification_id == 731
    notify_call = client._bus.calls[0]
    assert notify_call.body[5] == [
        "run_topgrade",
        "Run Topgrade",
        "dismiss",
        "Dismiss",
    ]
    assert "member='ActionInvoked'" in subscription.body[0]


def test_jeepney_notification_address_uses_correct_object_path() -> None:
    pytest.importorskip("jeepney")
    from jeepney import DBusAddress

    client = NotificationClient()
    client._dbus_available = True
    client._open_dbus_connection = FakeBus
    client._DBusAddress = DBusAddress

    assert client._ensure_connection() is True
    assert client._proxy.object_path == "/org/freedesktop/Notifications"
    assert client._proxy.bus_name == "org.freedesktop.Notifications"
    assert client._proxy.interface == "org.freedesktop.Notifications"


def test_second_notify_replaces_the_first() -> None:
    client, _bus, calls = _make_dbus_client()

    client.notify("One", "a")
    client.notify("Two", "b")

    assert calls[0][3][1] == 0
    assert calls[1][3][1] == 731
