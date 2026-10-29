"""Tests for the pacman update checker and parser."""

from __future__ import annotations

from topgrade_update.core.checkers.builtins import (
    _parse_checkupdates_line as parse_line,
)


def test_parse_3_field_line() -> None:
    """checkupdates outputs 3 fields: name old new."""
    result = parse_line("firefox 120.0-1 121.0-1", "pacman")
    assert result is not None
    assert result.name == "firefox"
    assert result.old_version == "120.0-1"
    assert result.new_version == "121.0-1"
    assert result.source == "pacman"


def test_parse_4_field_line() -> None:
    """Some AUR helpers output 4 fields: name old _ new."""
    result = parse_line("firefox 120.0-1 extra 121.0-1", "aur")
    assert result is not None
    assert result.name == "firefox"
    assert result.old_version == "120.0-1"
    assert result.new_version == "121.0-1"
    assert result.source == "aur"


def test_parse_too_short_line() -> None:
    """Lines with fewer than 3 fields are rejected."""
    assert parse_line("only", "pacman") is None
    assert parse_line("two fields", "pacman") is None


def test_parse_empty_line() -> None:
    assert parse_line("", "pacman") is None
    assert parse_line("   ", "pacman") is None


def test_parse_tab_separated() -> None:
    """checkupdates uses tab separation."""
    result = parse_line("pkg\t1.0-1\t2.0-1", "pacman")
    assert result is not None
    assert result.name == "pkg"
    assert result.new_version == "2.0-1"
