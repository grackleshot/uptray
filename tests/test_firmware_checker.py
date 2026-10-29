"""Tests for the firmware update checker."""

from __future__ import annotations

from topgrade_update.core.checkers.builtins import FirmwareChecker, _parse_fwupd_output


def test_parse_fwupd_output_empty() -> None:
    assert _parse_fwupd_output("") == []


def test_parse_fwupd_output_no_updates() -> None:
    output = """System:
  Device: My Laptop (abc123-def456)
  Vendor: Example Corp
  Serial: 12345
"""
    assert _parse_fwupd_output(output) == []


def test_parse_fwupd_output_with_updates() -> None:
    output = """System:
  Device: My Laptop (abc123-def456)
  Vendor: Example Corp

  Updates:
    BIOS Setup Utility 9.0.16.0 -> 9.0.17.0

Touchpad:
  Device: Synaptics (xyz789)

  Updates:
    Touchpad Firmware v1.2 -> v1.3
"""
    result = _parse_fwupd_output(output)
    assert len(result) == 2
    assert result[0].source == "firmware"
    assert result[0].new_version == "9.0.17.0"
    assert result[1].source == "firmware"
    assert result[1].new_version == "v1.3"


def test_firmware_checker_is_available_no_fwupdmgr(monkeypatch: object) -> None:
    monkeypatch.setattr("shutil.which", lambda x: None)
    checker = FirmwareChecker()
    assert checker.is_available() is False
