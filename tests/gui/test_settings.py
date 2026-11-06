"""Tests for the settings dialog."""

from __future__ import annotations

from topgrade_update.core.models import (
    Config,
    CustomCommandConfig,
    NotificationConfig,
    SourceConfig,
    TrayConfig,
)
from topgrade_update.gui.settings import SettingsDialog


def _sample_config() -> Config:
    return Config(
        check_interval=1800,
        terminals=["konsole", "kitty"],
        sources={"pacman": SourceConfig(True), "aur": SourceConfig(False)},
        notifications=NotificationConfig(
            enabled=True,
            quiet_hours_start=23,
            quiet_hours_end=7,
            sound=False,
        ),
        tray=TrayConfig(click_action="show_updates", snooze_hours=2),
        custom_commands=[
            CustomCommandConfig(name="my-check", command=["check"], enabled=True)
        ],
    )


def test_settings_roundtrip_preserves_values(qapp) -> None:  # noqa: ANN001
    cfg = _sample_config()
    dialog = SettingsDialog(cfg)

    assert dialog.get_config() == cfg


def test_settings_edits_apply(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(_sample_config())

    dialog._interval.setValue(3600)
    dialog._terminals.setText("alacritty, xterm")
    dialog._notifications_sound.setChecked(True)
    dialog._quiet_start.setCurrentIndex(0)  # (off)
    dialog._quiet_end.setCurrentIndex(0)
    dialog._icon_style.setCurrentIndex(1)  # colorblind
    dialog._source_boxes["aur"].setChecked(True)
    dialog._source_boxes["pacman"].setChecked(False)
    dialog._custom_boxes["my-check"].setChecked(False)

    edited = dialog.get_config()

    assert edited.check_interval == 3600
    assert edited.terminals == ["alacritty", "xterm"]
    assert edited.notifications.sound is True
    assert edited.notifications.quiet_hours_start is None
    assert edited.notifications.quiet_hours_end is None
    assert edited.tray.icon_style == "colorblind"
    assert edited.sources["pacman"].enabled is False
    assert edited.sources["aur"].enabled is True
    assert edited.custom_commands[0].enabled is False
    # Untouched tray settings survive.
    assert edited.tray.click_action == "show_updates"
