from __future__ import annotations

import os

import pytest

from topgrade_update.core.config import load_config


def test_load_config_reads_tray_settings(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[tray]
click_action = "show_updates"
snooze_hours = 2
""".strip()
    )

    cfg = load_config(config_path, environ={})

    assert cfg.tray.click_action == "show_updates"
    assert cfg.tray.snooze_hours == 2


def test_load_config_reads_terminal_list_from_root_table(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'terminals = ["kitty", "xterm"]\n\n[tray]\nclick_action = "default"\n'
    )

    cfg = load_config(config_path, environ={})

    assert cfg.terminals == ["kitty", "xterm"]


def test_load_config_reads_run_mode(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('run_mode = "verbose"\n')

    cfg = load_config(config_path, environ={})

    assert cfg.run_mode == "verbose"


def test_save_run_mode_preserves_newer_settings(tmp_path) -> None:
    from topgrade_update.core.config import save_config, save_run_mode
    from topgrade_update.core.models import Config, NotificationConfig

    path = tmp_path / "config.toml"
    stale = Config(
        check_interval=600,
        notifications=NotificationConfig(enabled=False),
        run_mode="simple",
    )
    save_config(stale, path)
    # Simulate tray settings saved while a run window still holds `stale`.
    on_disk = load_config(path, environ={})
    on_disk.check_interval = 1200
    on_disk.notifications.enabled = True
    save_config(on_disk, path)

    updated = save_run_mode("verbose", path)

    assert updated.run_mode == "verbose"
    assert updated.check_interval == 1200
    assert updated.notifications.enabled is True
    reloaded = load_config(path, environ={})
    assert reloaded.run_mode == "verbose"
    assert reloaded.check_interval == 1200
    assert reloaded.notifications.enabled is True


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("sources", '"invalid"'),
        ("sources.custom_commands", "{}"),
        ("notifications", "false"),
        ("tray", "[]"),
    ],
)
def test_load_config_rejects_malformed_sections(tmp_path, section, value) -> None:
    config_path = tmp_path / "config.toml"
    if section == "sources.custom_commands":
        config_path.write_text(f"[sources.custom_commands]\nname = {value}\n")
    else:
        config_path.write_text(f"{section} = {value}\n")

    with pytest.raises(ValueError, match=section):
        load_config(config_path, environ={})


def test_environment_overrides_file_configuration(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
check_interval = 600
terminals = ["xterm"]

[sources.pacman]
enabled = false

[notifications]
enabled = false
quiet_hours_start = 22
quiet_hours_end = 6

[tray]
click_action = "show_updates"
snooze_hours = 2

[[sources.custom_commands]]
name = "My Check"
command = ["my-checker"]
enabled = false
""".strip()
    )

    cfg = load_config(
        config_path,
        environ={
            "TOPGRADE_UPDATE_CHECK_INTERVAL": "900",
            "TOPGRADE_UPDATE_TERMINALS": os.pathsep.join(["kitty", "alacritty"]),
            "TOPGRADE_UPDATE_SOURCE_PACMAN_ENABLED": "true",
            "TOPGRADE_UPDATE_SOURCE_CUSTOM_MY_CHECK_ENABLED": "yes",
            "TOPGRADE_UPDATE_NOTIFICATIONS_ENABLED": "on",
            "TOPGRADE_UPDATE_QUIET_HOURS_START": "23",
            "TOPGRADE_UPDATE_TRAY_CLICK_ACTION": "run_topgrade",
            "TOPGRADE_UPDATE_TRAY_SNOOZE_HOURS": "8",
        },
    )

    assert cfg.check_interval == 900
    assert cfg.terminals == ["kitty", "alacritty"]
    assert cfg.sources["pacman"].enabled is True
    assert cfg.notifications.enabled is True
    assert cfg.notifications.quiet_hours_start == 23
    assert cfg.notifications.quiet_hours_end == 6
    assert cfg.tray.click_action == "run_topgrade"
    assert cfg.tray.snooze_hours == 8
    assert cfg.custom_commands[0].enabled is True


def test_environment_overrides_apply_without_a_config_file(tmp_path) -> None:
    cfg = load_config(
        tmp_path / "missing.toml",
        environ={"TOPGRADE_UPDATE_CHECK_INTERVAL": "1200"},
    )

    assert cfg.check_interval == 1200


@pytest.mark.parametrize(
    ("variable", "value", "error_match"),
    [
        ("TOPGRADE_UPDATE_CHECK_INTERVAL", "later", "CHECK_INTERVAL"),
        ("TOPGRADE_UPDATE_NOTIFICATIONS_ENABLED", "sometimes", "NOTIFICATIONS_ENABLED"),
        ("TOPGRADE_UPDATE_QUIET_HOURS_START", "24", "quiet_hours_start"),
    ],
)
def test_environment_overrides_are_validated(tmp_path, variable, value, error_match) -> None:
    with pytest.raises(ValueError, match=error_match):
        load_config(tmp_path / "missing.toml", environ={variable: value})
