from __future__ import annotations

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

    cfg = load_config(config_path)

    assert cfg.tray.click_action == "show_updates"
    assert cfg.tray.snooze_hours == 2


def test_load_config_reads_terminal_list_from_root_table(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'terminals = ["kitty", "xterm"]\n\n[tray]\nclick_action = "default"\n'
    )

    cfg = load_config(config_path)

    assert cfg.terminals == ["kitty", "xterm"]


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
        load_config(config_path)
