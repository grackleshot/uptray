"""Tests for launching Topgrade from the tray."""

from __future__ import annotations

from unittest.mock import patch

from topgrade_update.gui.tray import launch_topgrade_in_terminal


def test_launch_topgrade_reports_when_topgrade_is_missing(monkeypatch) -> None:
    monkeypatch.setattr("topgrade_update.gui.tray.shutil.which", lambda _command: None)

    with (
        patch("topgrade_update.gui.tray.find_terminal") as find_terminal,
        patch("topgrade_update.gui.tray.send_message") as send_message,
    ):
        launch_topgrade_in_terminal()

    find_terminal.assert_not_called()
    send_message.assert_called_once_with(
        "Topgrade not found", "Install topgrade before trying to run it."
    )


def test_launch_topgrade_uses_detected_terminal(monkeypatch) -> None:
    monkeypatch.setattr(
        "topgrade_update.gui.tray.shutil.which", lambda command: "/usr/bin/topgrade"
    )

    with (
        patch(
            "topgrade_update.gui.tray.find_terminal",
            return_value=("/usr/bin/kitty", ["-e"]),
        ),
        patch("topgrade_update.gui.tray.subprocess.Popen") as popen,
    ):
        launch_topgrade_in_terminal()

    popen.assert_called_once_with(["/usr/bin/kitty", "-e", "/usr/bin/topgrade"])
