"""Built-in update checker implementations."""

from __future__ import annotations

import shutil
from typing import ClassVar

from topgrade_update.core.models import Update
from topgrade_update.core.provider import UpdateChecker
from topgrade_update.core.subprocess import run_checked


def _parse_checkupdates_line(line: str, source: str) -> Update | None:
    """Parse a line from checkupdates or AUR helper output."""
    parts = line.strip().split()
    if len(parts) < 4:
        return None
    return Update(
        name=parts[0],
        old_version=parts[1],
        new_version=parts[3],
        source=source,
    )


class PacmanChecker(UpdateChecker):
    """Check for available pacman updates via checkupdates."""

    name: ClassVar[str] = "pacman"
    label: ClassVar[str] = "Pacman"

    def is_available(self) -> bool:
        return shutil.which("checkupdates") is not None

    def check(self) -> list[Update]:
        r = run_checked(["checkupdates"])
        if r.returncode != 0 or not r.stdout.strip():
            return []
        updates: list[Update] = []
        for line in r.stdout.strip().splitlines():
            up = _parse_checkupdates_line(line, self.name)
            if up:
                updates.append(up)
        return updates


class AurChecker(UpdateChecker):
    """Check for available AUR updates via paru or yay."""

    name: ClassVar[str] = "aur"
    label: ClassVar[str] = "AUR"

    def is_available(self) -> bool:
        return shutil.which("paru") is not None or shutil.which("yay") is not None

    def check(self) -> list[Update]:
        for helper in ("paru", "yay"):
            if not shutil.which(helper):
                continue
            r = run_checked([helper, "-Qua"])
            if r.returncode != 0 or not r.stdout.strip():
                return []
            updates: list[Update] = []
            for line in r.stdout.strip().splitlines():
                up = _parse_checkupdates_line(line, self.name)
                if up:
                    updates.append(up)
            return updates
        return []


class FlatpakChecker(UpdateChecker):
    """Check for available flatpak updates."""

    name: ClassVar[str] = "flatpak"
    label: ClassVar[str] = "Flatpak"

    def is_available(self) -> bool:
        return shutil.which("flatpak") is not None

    def check(self) -> list[Update]:
        r = run_checked([
            "flatpak",
            "remote-ls",
            "--updates",
            "--columns=application,version,branch",
        ])
        if r.returncode != 0 or not r.stdout.strip():
            return []
        updates: list[Update] = []
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                updates.append(
                    Update(
                        name=parts[0],
                        old_version="?",
                        new_version=parts[1],
                        source=self.name,
                    )
                )
        return updates
