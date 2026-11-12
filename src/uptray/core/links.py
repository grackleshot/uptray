"""Upstream package URLs for tray and dialog navigation."""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from subprocess import CompletedProcess

    Runner = Callable[..., CompletedProcess[str]]

_PACKAGE_SEARCH_URL = "https://archlinux.org/packages/?q={name}"
_AUR_PACKAGE_URL = "https://aur.archlinux.org/packages/{name}/"
_FLATHUB_APP_URL = "https://flathub.org/apps/{name}"
_FWUPD_URL = "https://fwupd.org/"


def upstream_url(name: str, source: str, runner: Runner | None = None) -> str:
    """Return a web URL describing a package, best-effort and never raising."""
    if source == "aur":
        return _AUR_PACKAGE_URL.format(name=name)
    if source == "flatpak":
        return _FLATHUB_APP_URL.format(name=name)
    if source == "firmware":
        return _FWUPD_URL
    if source == "reboot":
        return ""

    # pacman and custom sources: prefer the packaged upstream URL, fall back
    # to the package search page.
    url = _pacman_url(name, runner)
    return url or _PACKAGE_SEARCH_URL.format(name=name)


def _pacman_url(name: str, runner: Runner | None) -> str:
    if shutil.which("pacman") is None:
        return ""
    probe = runner or _default_runner
    try:
        result = probe(["pacman", "-Si", "--", name])
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    for line in (result.stdout or "").splitlines():
        field, separator, value = line.partition(":")
        if not separator:
            continue
        if field.strip() == "URL":
            url = value.strip()
            return url if url.startswith(("http://", "https://")) else ""
    return ""


def _default_runner(cmd: list[str], **_kwargs: bool) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv from trusted sources
        cmd,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
