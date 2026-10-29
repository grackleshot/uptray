from __future__ import annotations

from topgrade_update.core.topgrade_config import (
    TOPGRADE_STEP_MAP,
    get_disabled_categories,
    get_disabled_steps,
    load_topgrade_config,
)


def test_load_topgrade_config_returns_empty_dict_when_missing(tmp_path) -> None:
    assert load_topgrade_config(tmp_path / "missing.toml") == {}


def test_load_topgrade_config_reads_toml(tmp_path) -> None:
    path = tmp_path / "topgrade.toml"
    path.write_text('flatpak = false\n[linux]\ndisabled = true\n')

    assert load_topgrade_config(path) == {"flatpak": False, "linux": {"disabled": True}}


def test_get_disabled_steps_returns_false_top_level_steps_lowercased() -> None:
    cfg = {"Flatpak": False, "pacman": True, "linux": {"disabled": True}}

    assert get_disabled_steps(cfg) == {"flatpak"}


def test_get_disabled_categories_returns_disabled_nested_categories_lowercased() -> None:
    cfg = {"linux": {"disabled": True}, "git": {"disabled": False}, "flatpak": False}

    assert get_disabled_categories(cfg) == {"linux"}


def test_topgrade_step_map_maps_known_steps_to_checker_names() -> None:
    assert TOPGRADE_STEP_MAP["pacman"] == {"pacman"}
    assert TOPGRADE_STEP_MAP["yay"] == {"aur"}
    assert TOPGRADE_STEP_MAP["paru"] == {"aur"}
    assert TOPGRADE_STEP_MAP["flatpak"] == {"flatpak"}
    assert TOPGRADE_STEP_MAP["linux"] == {"pacman", "aur"}
