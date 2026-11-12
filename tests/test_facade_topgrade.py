from __future__ import annotations

from uptray.core.checkers import facade


def test_get_topgrade_disabled_checkers_maps_topgrade_toml_steps(tmp_path, monkeypatch) -> None:
    topgrade_toml = tmp_path / "topgrade.toml"
    topgrade_toml.write_text("flatpak = false\n[linux]\ndisabled = true\n")
    monkeypatch.setattr(facade, "find_topgrade_toml", lambda: topgrade_toml)

    assert facade._get_topgrade_disabled_checkers() == {"flatpak", "pacman", "aur"}


def test_get_topgrade_disabled_checkers_returns_empty_set_without_topgrade_toml(
    monkeypatch,
) -> None:
    monkeypatch.setattr(facade, "find_topgrade_toml", lambda: None)

    assert facade._get_topgrade_disabled_checkers() == set()
