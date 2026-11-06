"""Tests for post-update maintenance detection."""

from __future__ import annotations

import subprocess

from topgrade_update.core.maintenance import (
    CACHE_WARN_BYTES,
    cache_usage,
    find_orphans,
    find_unmerged_config_files,
    maintenance_summary,
)


def _pacman_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pacman", "-Qdtq"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_find_orphans_parses_pacman_output(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.maintenance.shutil.which", lambda _name: "/usr/bin/pacman"
    )
    orphans = find_orphans(runner=lambda _cmd, **_kw: _pacman_result("foo\nbar\n"))

    assert orphans == ["foo", "bar"]


def test_find_orphans_exit_one_means_none(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(
        "topgrade_update.core.maintenance.shutil.which", lambda _name: "/usr/bin/pacman"
    )
    assert find_orphans(runner=lambda _cmd, **_kw: _pacman_result("", returncode=1)) == []


def test_find_orphans_without_pacman(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("topgrade_update.core.maintenance.shutil.which", lambda _name: None)
    assert find_orphans() == []


def test_find_unmerged_config_files(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "pacman.d").mkdir()
    (tmp_path / "pacman.d" / "mirrorlist.pacnew").write_text("x", encoding="utf-8")
    (tmp_path / "passwd").write_text("x", encoding="utf-8")
    (tmp_path / "fstab.pacsave").write_text("x", encoding="utf-8")

    found = find_unmerged_config_files(tmp_path)

    assert found == ["fstab.pacsave", "pacman.d/mirrorlist.pacnew"]


def test_cache_usage_sums_files(tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "a.pkg.tar.zst").write_bytes(b"x" * 100)
    (tmp_path / "b.pkg.tar.zst").write_bytes(b"x" * 50)
    (tmp_path / "subdir").mkdir()

    assert cache_usage(tmp_path) == 150
    assert cache_usage(tmp_path / "missing") == 0


def test_maintenance_summary_combines_findings() -> None:
    findings = maintenance_summary(
        orphans=["orphan1"],
        config_files=["pacman.d/mirrorlist.pacnew"],
        cache_bytes=CACHE_WARN_BYTES + 1,
    )

    assert [f.kind for f in findings] == ["orphans", "pacnew", "cache"]
    assert findings[0].detail == ["orphan1"]


def test_maintenance_summary_empty_when_healthy() -> None:
    assert (
        maintenance_summary(orphans=[], config_files=[], cache_bytes=CACHE_WARN_BYTES) == []
    )
