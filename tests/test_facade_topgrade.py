from __future__ import annotations

from pathlib import Path

import pytest

from uptray.core.checkers import facade
from uptray.core.models import Config


def test_get_topgrade_disabled_checkers_maps_topgrade_toml_steps(tmp_path, monkeypatch) -> None:
    topgrade_toml = tmp_path / "topgrade.toml"
    topgrade_toml.write_text("flatpak = false\n[linux]\ndisabled = true\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert facade._get_topgrade_disabled_checkers() == {"flatpak", "pacman", "aur"}


def test_get_topgrade_disabled_checkers_returns_empty_set_without_topgrade_toml(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert facade._get_topgrade_disabled_checkers() == set()


@pytest.mark.parametrize("with_main", [False, True])
def test_checker_selection_honors_dropins(tmp_path, monkeypatch, with_main) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    dropins = tmp_path / "topgrade.d"
    dropins.mkdir()
    (dropins / "10-packages").write_text('[misc]\nonly = ["system"]\ndisable = ["flatpak"]\n')
    (dropins / ".DS_Store").write_bytes(b"not a config file")
    if with_main:
        (tmp_path / "topgrade.toml").write_text('[misc]\nonly = ["firmware"]\n')
    expected = {"flatpak"} if with_main else {"firmware", "flatpak"}
    assert facade._get_topgrade_disabled_checkers() == expected


def test_empty_terminal_list_uses_the_builtin_defaults(monkeypatch) -> None:  # noqa: ANN001
    def which(cmd: str) -> str | None:
        if cmd == "konsole":
            return "/usr/bin/konsole"
        return None

    monkeypatch.setattr(facade.shutil, "which", which)
    monkeypatch.delenv("TERMINAL", raising=False)

    assert facade.find_terminal(Config(terminals=[])) == ("/usr/bin/konsole", ["-e"])
