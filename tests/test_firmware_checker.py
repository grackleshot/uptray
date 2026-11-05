"""Tests for the firmware update checker."""

from __future__ import annotations

import json
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

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


def test_parse_fwupd_output_json_payload() -> None:
    """The JSON branch of _parse_fwupd_output is the primary path (--json)."""
    payload = {"Devices": [{"Name": "Laptop", "Version": "1.0", "Releases": [{"Version": "2.0"}]}]}
    result = _parse_fwupd_output(json.dumps(payload))
    assert len(result) == 1
    update = result[0]
    assert update.name == "Laptop"
    assert update.old_version == "1.0"
    assert update.new_version == "2.0"
    assert update.source == "firmware"


def test_parse_fwupd_output_invalid_json_falls_back_to_text() -> None:
    output = """System:
  Device: My Laptop (abc123-def456)

  Updates:
    BIOS 9.0 -> 9.1
"""
    result = _parse_fwupd_output(output)
    assert len(result) == 1
    assert result[0].name == "Device: My Laptop: BIOS"
    assert result[0].old_version == "9.0"
    assert result[0].new_version == "9.1"
    assert result[0].source == "firmware"


@pytest.mark.parametrize("devices", [None, 5, "oops", {}])
def test_parse_fwupd_output_devices_not_a_list(devices: object) -> None:
    """Non-list Devices must yield []; None/5 raise TypeError if the isinstance guard is removed."""
    assert _parse_fwupd_output(json.dumps({"Devices": devices})) == []


def test_firmware_checker_check_parses_json_output() -> None:
    """FirmwareChecker.check() runs fwupdmgr --json and parses its JSON output."""
    payload = {"Devices": [{"Name": "Laptop", "Version": "1.0", "Releases": [{"Version": "2.0"}]}]}
    completed = CompletedProcess(
        args=["fwupdmgr", "get-updates", "--json"],
        returncode=0,
        stdout=json.dumps(payload),
        stderr="",
    )
    checker = FirmwareChecker()
    with patch(
        "topgrade_update.core.checkers.builtins.run_checked", return_value=completed
    ) as mock_run:
        [update] = checker.check()
    mock_run.assert_called_once_with(["fwupdmgr", "get-updates", "--json"])
    assert update.name == "Laptop"
    assert update.old_version == "1.0"
    assert update.new_version == "2.0"
    assert update.source == "firmware"
