"""Tests for programmatic icon generation."""

from __future__ import annotations

from topgrade_update.gui.icons import IconCache


def test_default_and_colorblind_styles_are_selectable(qapp) -> None:  # noqa: ANN001
    default_cache = IconCache()
    colorblind_cache = IconCache("colorblind")

    assert default_cache.style == "default"
    assert colorblind_cache.style == "colorblind"
    # Unknown styles fall back to the default palette.
    assert IconCache("bogus").style == "default"


def test_reboot_icon_is_cached_and_distinct(qapp) -> None:  # noqa: ANN001
    cache = IconCache()

    first = cache.reboot()
    second = cache.reboot()
    updates = cache.updates(3)

    assert first is second  # cached
    assert not first.isNull()
    assert updates.cacheKey() != first.cacheKey()
