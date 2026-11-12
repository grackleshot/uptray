"""Tests for the CLI's machine-readable update output."""

from __future__ import annotations

import json

import pytest

from topgrade_update.cli import main as cli
from topgrade_update.cli.main import _print_json
from topgrade_update.core.models import CheckResult, Config, CustomCommandConfig, Update


def test_json_output_includes_flatpak_branch(capsys) -> None:
    result = CheckResult(
        source="flatpak",
        updates=[Update("org.example.App", "?", "2.0", "flatpak", branch="stable")],
    )

    _print_json([result], 1)

    payload = json.loads(capsys.readouterr().out)
    [update] = payload["sources"]["flatpak"]["updates"]
    assert update["branch"] == "stable"


def test_cli_values_override_loaded_configuration(monkeypatch) -> None:
    cfg = Config(check_interval=900)
    cfg.notifications.enabled = False
    cfg.notifications.quiet_hours_start = 22
    cfg.notifications.quiet_hours_end = 6
    cfg.sources["pacman"].enabled = False
    cfg.custom_commands = [CustomCommandConfig("My Check", ["my-checker"], enabled=False)]
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "load_config", lambda: cfg)
    captured: list[Config] = []
    monkeypatch.setattr(
        cli,
        "cmd_list",
        lambda loaded_cfg, *, json_output=False: captured.append(loaded_cfg) or 0,
    )

    result = cli.main(
        [
            "--list",
            "--check-interval",
            "1800",
            "--terminal",
            "kitty",
            "--terminal",
            "xterm",
            "--enable-source",
            "pacman",
            "--enable-source",
            "custom_my_check",
            "--disable-source",
            "flatpak",
            "--enable-notifications",
            "--no-quiet-hours",
            "--tray-click-action",
            "run_topgrade",
            "--snooze-hours",
            "8",
        ]
    )

    assert result == 0
    assert captured == [cfg]
    assert cfg.check_interval == 1800
    assert cfg.terminals == ["kitty", "xterm"]
    assert cfg.sources["pacman"].enabled is True
    assert cfg.sources["flatpak"].enabled is False
    assert cfg.custom_commands[0].enabled is True
    assert cfg.notifications.enabled is True
    assert cfg.notifications.quiet_hours_start is None
    assert cfg.notifications.quiet_hours_end is None
    assert cfg.tray.click_action == "run_topgrade"
    assert cfg.tray.snooze_hours == 8


def test_cli_rejects_overrides_without_a_mode(monkeypatch) -> None:
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)

    with pytest.raises(SystemExit, match="2"):
        cli.main(["--check-interval", "900"])


def test_cli_rejects_empty_terminal_name(monkeypatch) -> None:
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)

    with pytest.raises(SystemExit, match="2"):
        cli.main(["--list", "--terminal", "   "])


def test_version_flag(capsys) -> None:
    from topgrade_update import __version__

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])

    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_tray_config_error_sends_notification(monkeypatch, capsys) -> None:
    def boom() -> Config:
        raise ValueError("bad toml")

    sent: list[str] = []
    monkeypatch.setattr(cli, "setup_logging", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "load_config", boom)
    monkeypatch.setattr(cli, "send_message", lambda summary, body, **_kw: sent.append(body))

    assert cli.main(["--tray"]) == 2
    assert "bad toml" in sent[0]
    assert "bad toml" in capsys.readouterr().err

    sent.clear()
    assert cli.main(["--check"]) == 2
    assert sent == []
