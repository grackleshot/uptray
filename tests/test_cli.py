"""Tests for the CLI's machine-readable update output."""

from __future__ import annotations

import json

from topgrade_update.cli.main import _print_json
from topgrade_update.core.models import CheckResult, Update


def test_json_output_includes_flatpak_branch(capsys) -> None:
    result = CheckResult(
        source="flatpak",
        updates=[Update("org.example.App", "?", "2.0", "flatpak", branch="stable")],
    )

    _print_json([result], 1)

    payload = json.loads(capsys.readouterr().out)
    [update] = payload["sources"]["flatpak"]["updates"]
    assert update["branch"] == "stable"
