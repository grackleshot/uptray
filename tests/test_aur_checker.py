"""Tests for the AUR checker's helper handling and exit-code semantics."""

from __future__ import annotations

import subprocess

from uptray.core.checkers.builtins import AurChecker


def _run(stdout: str, returncode: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["paru", "-Qua"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_exit_one_with_no_output_means_no_updates(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "uptray.core.checkers.builtins.shutil.which",
        lambda n: "/bin/paru" if n == "paru" else None,
    )
    import uptray.core.checkers.builtins as builtins

    checker = AurChecker()
    monkeypatch.setattr(builtins, "run_checked", lambda _cmd: _run("", 1))
    assert checker.check() == []


def test_parses_updates_on_success(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "uptray.core.checkers.builtins.shutil.which",
        lambda n: "/bin/paru" if n == "paru" else None,
    )
    import uptray.core.checkers.builtins as builtins

    checker = AurChecker()
    monkeypatch.setattr(
        builtins, "run_checked", lambda _cmd: _run("foo 1.0 1.1\n", 0)
    )

    updates = checker.check()

    assert len(updates) == 1
    assert updates[0].name == "foo"
    assert updates[0].new_version == "1.1"


def test_hard_failures_raise(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "uptray.core.checkers.builtins.shutil.which",
        lambda n: "/bin/paru" if n == "paru" else None,
    )
    import uptray.core.checkers.builtins as builtins

    checker = AurChecker()
    monkeypatch.setattr(
        builtins, "run_checked", lambda _cmd: _run("network unreachable", 2)
    )

    try:
        checker.check()
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_pikaur_is_supported(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "uptray.core.checkers.builtins.shutil.which",
        lambda n: "/bin/pikaur" if n == "pikaur" else None,
    )

    assert AurChecker().is_available() is True
