from __future__ import annotations

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
