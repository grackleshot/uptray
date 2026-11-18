"""Tests for upstream package URL resolution."""

from __future__ import annotations

import subprocess

from uptray.core.links import flatpak_ref_is_unpublished, upstream_url


def _si_result(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["pacman", "-Si"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_aur_uses_aur_package_page() -> None:
    assert (
        upstream_url("paru-bin", "aur")
        == "https://aur.archlinux.org/packages/paru-bin/"
    )


def test_flatpak_uses_flathub_page() -> None:
    assert upstream_url("org.mozilla.firefox", "flatpak") == "https://flathub.org/apps/org.mozilla.firefox"


def test_published_flatpak_runtime_keeps_its_page() -> None:
    assert not flatpak_ref_is_unpublished("org.gnome.Platform")
    assert not flatpak_ref_is_unpublished("org.freedesktop.Platform.GL.default")
    assert not flatpak_ref_is_unpublished("org.freedesktop.Platform.GL32.default")
    assert (
        upstream_url("org.gnome.Platform", "flatpak")
        == "https://flathub.org/apps/org.gnome.Platform"
    )
    assert (
        upstream_url("org.freedesktop.Platform.GL.default", "flatpak")
        == "https://flathub.org/apps/org.freedesktop.Platform.GL.default"
    )


def test_unpublished_flatpak_ref_has_no_link() -> None:
    for name in (
        "org.gnome.Platform.Locale",
        "org.freedesktop.Platform.Compat.i386",
        "org.gnome.Sdk.Debug",
        "org.freedesktop.Sdk.Docs",
        "org.freedesktop.Platform.GL.GLES",
        "org.gnome.Platform.Var",
        # Driver builds: common on NVIDIA systems, and all 404 on Flathub.
        "org.freedesktop.Platform.GL.nvidia-550-78",
        "org.freedesktop.Platform.GL32.nvidia-550-78",
        "org.freedesktop.Platform.GL.mesa-git",
    ):
        assert flatpak_ref_is_unpublished(name)
        assert upstream_url(name, "flatpak") == ""


def test_firmware_uses_fwupd_page() -> None:
    assert upstream_url("ThinkPad BIOS", "firmware") == "https://fwupd.org/"


def test_reboot_has_no_link() -> None:
    assert upstream_url("kernel", "reboot") == ""


def test_pacman_uses_packaged_url(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("uptray.core.links.shutil.which", lambda _n: "/usr/bin/pacman")
    si_output = "Repository      : extra\nURL             : https://firefox.org\n"

    url = upstream_url("firefox", "pacman", runner=lambda _cmd, **_kw: _si_result(si_output))

    assert url == "https://firefox.org"


def test_pacman_falls_back_to_search(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("uptray.core.links.shutil.which", lambda _n: "/usr/bin/pacman")

    url = upstream_url("unknown-pkg", "pacman", runner=lambda _c, **_k: _si_result("", 1))

    assert url == "https://archlinux.org/packages/?q=unknown-pkg"
