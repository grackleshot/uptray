from __future__ import annotations

from uptray.core.checkers import facade


def test_get_topgrade_disabled_checkers_maps_topgrade_toml_steps(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "topgrade.toml").write_text("flatpak = false\n[linux]\ndisabled = true\n")

    assert facade._get_topgrade_disabled_checkers() == {"flatpak", "pacman", "aur"}


def test_get_topgrade_disabled_checkers_returns_empty_set_without_config(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert facade._get_topgrade_disabled_checkers() == set()


def test_topgrade_dropin_disables_checkers_without_a_main_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dropin = tmp_path / "topgrade.d"
    dropin.mkdir()
    (dropin / "flatpak.toml").write_text('[misc]\ndisable = ["flatpak"]\n')

    assert facade._get_topgrade_disabled_checkers() == {"flatpak"}


def test_main_topgrade_file_overrides_dropin_disable_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    dropin = tmp_path / "topgrade.d"
    dropin.mkdir()
    (dropin / "10.toml").write_text('[misc]\ndisable = ["flatpak"]\n')
    (tmp_path / "topgrade.toml").write_text('[misc]\ndisable = ["firmware"]\n')

    assert facade._get_topgrade_disabled_checkers() == {"firmware"}
