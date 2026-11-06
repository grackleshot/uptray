"""Tests for the network connectivity probe."""

from __future__ import annotations

import subprocess

from topgrade_update.core.network import is_online


def _probe_result(state: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["nmcli", "networking", "connectivity"],
        returncode=returncode,
        stdout=state,
        stderr="",
    )


def test_full_connectivity_is_online(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.network.shutil.which", lambda _name: "/usr/bin/nmcli"
    )
    assert is_online(runner=lambda _cmd, **_kw: _probe_result("full\n")) is True


def test_limited_and_none_and_portal_are_offline(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.network.shutil.which", lambda _name: "/usr/bin/nmcli"
    )
    for state in ("limited", "portal", "none"):
        assert is_online(runner=lambda _c, s=state, **_k: _probe_result(s)) is False


def test_unknown_state_falls_open(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.network.shutil.which", lambda _name: "/usr/bin/nmcli"
    )
    assert is_online(runner=lambda _cmd, **_kw: _probe_result("unknown")) is True


def test_probe_failure_falls_open(monkeypatch) ->  None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.network.shutil.which", lambda _name: "/usr/bin/nmcli"
    )

    def failing_probe(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise RuntimeError("nmcli hung")

    assert is_online(runner=failing_probe) is True


def test_probe_nonzero_exit_falls_open(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.network.shutil.which", lambda _name: "/usr/bin/nmcli"
    )
    assert is_online(runner=lambda _cmd, **_kw: _probe_result("", returncode=1)) is True


def test_missing_nmcli_assumes_online(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("topgrade_update.core.network.shutil.which", lambda _name: None)
    assert is_online() is True
