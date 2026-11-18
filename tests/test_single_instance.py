"""Tests for the single-instance tray lock."""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from uptray.gui.tray_logic import _acquire_instance_lock


def test_lock_is_exclusive(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    first = _acquire_instance_lock()
    assert first is not None

    second = _acquire_instance_lock()
    assert second is None

    first.close()
    third = _acquire_instance_lock()
    assert third is not None
    third.close()


def test_lock_file_records_pid(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    handle = _acquire_instance_lock()
    assert handle is not None

    lock_file = tmp_path / "uptray.lock"
    assert lock_file.read_text(encoding="utf-8").strip() == str(os.getpid())
    handle.close()


def test_contended_lock_closes_the_handle(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    opened: list[object] = []
    real_open = Path.open

    def tracking_open(self: Path, *args: object, **kwargs: object) -> object:
        handle = real_open(self, *args, **kwargs)
        if self.name == "uptray.lock":
            opened.append(handle)
        return handle

    def busy(*_args: object, **_kwargs: object) -> None:
        raise BlockingIOError(errno.EAGAIN, "busy")

    monkeypatch.setattr(Path, "open", tracking_open)
    monkeypatch.setattr("uptray.gui.tray_logic.fcntl.flock", busy)

    assert _acquire_instance_lock() is None
    assert opened
    assert opened[0].closed  # type: ignore[attr-defined]


def test_lock_does_not_treat_other_oserrors_as_already_running(
    tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr("uptray.gui.tray_logic.fcntl.flock", denied)

    with pytest.raises(PermissionError):
        _acquire_instance_lock()
