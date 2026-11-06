"""Tests for the single-instance tray lock."""

from __future__ import annotations

import os

from topgrade_update.gui.tray import _acquire_instance_lock


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

    lock_file = tmp_path / "topgrade-update.lock"
    assert lock_file.read_text(encoding="utf-8").strip() == str(os.getpid())
    handle.close()
