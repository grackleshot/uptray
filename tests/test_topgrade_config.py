from __future__ import annotations

from topgrade_update.core.topgrade_config import (
    TOPGRADE_STEP_MAP,
    get_disabled_categories,
    get_disabled_steps,
    get_only_steps,
    load_topgrade_config,
    only_restricted_checkers,
)


def test_load_topgrade_config_returns_empty_dict_when_missing(tmp_path) -> None:
    assert load_topgrade_config(tmp_path / "missing.toml") == {}


def test_load_topgrade_config_reads_toml(tmp_path) -> None:
    path = tmp_path / "topgrade.toml"
    path.write_text('flatpak = false\n[linux]\ndisabled = true\n')

    assert load_topgrade_config(path) == {"flatpak": False, "linux": {"disabled": True}}


def test_load_topgrade_config_merges_topgrade_d_then_main_file(
    tmp_path, monkeypatch  # noqa: ANN001
) -> None:
    dropin = tmp_path / "topgrade.d"
    dropin.mkdir()
    (dropin / "10-extra.toml").write_text(
        '[git]\nrepos = ["a"]\n[misc]\ndisable = ["flatpak"]\n'
    )
    (dropin / "20-override.toml").write_text('[misc]\ndisable = ["firmware"]\n')
    (tmp_path / "topgrade.toml").write_text('[misc]\ndisable = ["pacman"]\n')
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    merged = load_topgrade_config()

    # Lists from the main file replace drop-in lists; nested tables merge.
    assert merged["git"] == {"repos": ["a"]}
    assert merged["misc"]["disable"] == ["pacman"]


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
    assert TOPGRADE_STEP_MAP["pikaur"] == {"aur"}
    assert TOPGRADE_STEP_MAP["flatpak"] == {"flatpak"}
    assert TOPGRADE_STEP_MAP["linux"] == {"pacman", "aur"}


def test_get_only_steps_returns_none_when_unrestricted() -> None:
    assert get_only_steps({}) is None
    assert get_only_steps({"misc": {"only": []}}) is None
    assert get_only_steps({"misc": {"disable": ["flatpak"]}}) is None


def test_only_steps_restrict_non_listed_checkers() -> None:
    only = get_only_steps({"misc": {"only": ["flatpak", "git"]}})

    assert only == {"flatpak", "git"}
    # git is not a topgrade-update checker, so only flatpak survives.
    assert only_restricted_checkers(only) == {"pacman", "aur", "firmware"}

