"""Tests for the settings dialog."""

from __future__ import annotations

import uptray.core.autostart as autostart
from uptray.core.models import (
    Config,
    CustomCommandConfig,
    NotificationConfig,
    SourceConfig,
    TrayConfig,
)
from uptray.gui.settings import SettingsDialog


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

    dialog._interval.setValue(60)
    dialog._terminals.setText("alacritty, xterm")
    dialog._notifications_sound.setChecked(True)
    dialog._quiet_start.setCurrentIndex(0)  # (off)
    dialog._quiet_end.setCurrentIndex(0)
    dialog._icon_style.setCurrentIndex(1)  # colorblind
    dialog._run_mode.setCurrentIndex(1)  # verbose
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
    assert edited.run_mode == "verbose"
    assert edited.sources["pacman"].enabled is False
    assert edited.sources["aur"].enabled is True
    assert edited.custom_commands[0].enabled is False
    # Untouched tray settings survive.
    assert edited.tray.click_action == "show_updates"


def test_all_builtin_sources_have_checkboxes(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(_sample_config())

    assert {"pacman", "aur", "flatpak", "firmware", "reboot"} <= set(dialog._source_boxes)
    assert dialog._source_boxes["firmware"].isChecked()
    dialog._source_boxes["reboot"].setChecked(False)
    assert dialog.get_config().sources["reboot"].enabled is False


def test_restore_defaults_repopulates(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(_sample_config())

    dialog._populate(Config())

    assert dialog._interval.value() == Config().check_interval // 60
    assert dialog._source_boxes["aur"].isChecked()
    assert dialog._quiet_start.currentData() is None


def test_interval_shown_in_minutes(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(_sample_config())

    assert dialog._interval.value() == 30
    dialog._interval.setValue(45)
    assert dialog.get_config().check_interval == 2700


def test_quiet_hours_warning_visibility(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(_sample_config())  # 23 -> 7
    assert dialog._quiet_warning.isHidden()

    dialog._quiet_end.setCurrentIndex(dialog._quiet_start.currentIndex())
    assert not dialog._quiet_warning.isHidden()

    dialog._quiet_end.setCurrentIndex(0)  # one side off
    assert not dialog._quiet_warning.isHidden()

    dialog._quiet_start.setCurrentIndex(0)  # both off
    assert dialog._quiet_warning.isHidden()


def test_autostart_toggle_applies_on_accept(qapp, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    dest = tmp_path / "autostart"
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", dest)
    monkeypatch.setattr(autostart, "AUTOSTART_FILE", dest / "uptray.desktop")
    dialog = SettingsDialog(_sample_config())
    assert not dialog._autostart.isChecked()

    dialog.accept()  # unchanged: nothing written
    assert not autostart.AUTOSTART_FILE.exists()

    dialog = SettingsDialog(_sample_config())
    dialog._autostart.setChecked(True)
    dialog.accept()
    assert autostart.AUTOSTART_FILE.exists()

    dialog = SettingsDialog(_sample_config())
    assert dialog._autostart.isChecked()
    dialog._autostart.setChecked(False)
    dialog.accept()
    assert not autostart.AUTOSTART_FILE.exists()


def test_settings_keeps_hand_edited_interval_unless_changed(qapp) -> None:  # noqa: ANN001
    dialog = SettingsDialog(Config(check_interval=450))
    assert dialog.get_config().check_interval == 450

    dialog._interval.setValue(10)
    assert dialog.get_config().check_interval == 600
