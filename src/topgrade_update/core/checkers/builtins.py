"""Built-in update checker implementations."""

from __future__ import annotations

import json
import re
import shutil
from typing import ClassVar

from topgrade_update.core.models import Update, custom_checker_name
from topgrade_update.core.provider import UpdateChecker
from topgrade_update.core.subprocess import run_checked


def _command_error(command: list[str], returncode: int, stderr: str | None) -> RuntimeError:
    """Build a useful error for a failed update-check command."""
    detail = (stderr or "").strip()
    if not detail:
        detail = f"exited with status {returncode}"
    return RuntimeError(f"{command[0]} {detail}")


def _parse_checkupdates_line(line: str, source: str) -> Update | None:
    """Parse a line from checkupdates or AUR helper output.

    Handles both 3-field (name old new) and 4-field (name old _ new)
    formats used by checkupdates, paru, yay, and flatpak.
    """
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    name = parts[0]
    old_version = parts[1]
    # 3-field: name old new → new is at index 2
    # 4-field: name old _ new → new is at index 3
    new_version = parts[3] if len(parts) >= 4 else parts[2]
    return Update(name=name, old_version=old_version, new_version=new_version, source=source)


class PacmanChecker(UpdateChecker):
    """Check for available pacman updates via checkupdates."""

    name: ClassVar[str] = "pacman"
    label: ClassVar[str] = "Pacman"

    def is_available(self) -> bool:
        return shutil.which("checkupdates") is not None

    def check(self) -> list[Update]:
        command = ["checkupdates"]
        r = run_checked(command)
        if r.returncode == 2:  # checkupdates uses 2 to mean no updates
            return []
        if r.returncode != 0:
            raise _command_error(command, r.returncode, r.stderr)
        if not r.stdout.strip():
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
            command = [helper, "-Qua"]
            r = run_checked(command)
            if r.returncode != 0:
                raise _command_error(command, r.returncode, r.stderr)
            if not r.stdout.strip():
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
        command = [
            "flatpak",
            "remote-ls",
            "--updates",
            "--columns=application,version,branch",
        ]
        r = run_checked(command)
        if r.returncode != 0:
            raise _command_error(command, r.returncode, r.stderr)
        if not r.stdout.strip():
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
                        branch=parts[2] if len(parts) >= 3 and parts[2] else None,
                    )
                )
        return updates


class FirmwareChecker(UpdateChecker):
    """Check for available firmware updates via fwupd."""

    name: ClassVar[str] = "firmware"
    label: ClassVar[str] = "Firmware"

    def is_available(self) -> bool:
        return shutil.which("fwupdmgr") is not None

    def check(self) -> list[Update]:
        command = ["fwupdmgr", "get-updates", "--json"]
        r = run_checked(command)
        if r.returncode != 0:
            raise _command_error(command, r.returncode, r.stderr)
        return _parse_fwupd_output(r.stdout)


def _parse_fwupd_output(output: str) -> list[Update]:
    """Parse fwupdmgr get-updates output, preferring its stable JSON format."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, dict):
        devices = payload.get("Devices", [])
        if not isinstance(devices, list):
            return []
        updates: list[Update] = []
        for device in devices:
            if not isinstance(device, dict):
                continue
            releases = device.get("Releases", [])
            if not isinstance(releases, list) or not releases:
                continue
            release = releases[0]
            if not isinstance(release, dict):
                continue
            name = device.get("Name") or device.get("DeviceId") or "Firmware device"
            updates.append(
                Update(
                    name=str(name),
                    old_version=str(device.get("Version") or "?"),
                    new_version=str(release.get("Version") or "?"),
                    source="firmware",
                )
            )
        return updates

    # Retain support for older fwupd text output and test fixtures.
    text_updates: list[Update] = []
    device_name: str | None = None
    in_updates = False
    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        # Detect device name line (e.g. "Device Name (UUID)")
        dev_match = re.match(r"^(.+?)\s+\(([\w-]+)\)", stripped)
        if dev_match:
            device_name = dev_match.group(1)
        # Detect "Updates" subsection (with optional colon)
        if stripped.lower().startswith("updates"):
            in_updates = True
            continue
        # End of updates section — non-indented line without "->" signals
        # a new device section or top-level heading
        if in_updates and not stripped.startswith(" ") and "->" not in stripped:
            in_updates = False
            device_name = None
            continue
        if in_updates and "->" in stripped:
            idx = stripped.index("->")
            before = stripped[:idx].strip()
            after = stripped[idx + 2:].strip()
            before_parts = before.split()
            if len(before_parts) >= 2 and device_name:
                text_updates.append(Update(
                    name=f"{device_name}: {before_parts[0]}",
                    old_version=before_parts[1] if len(before_parts) > 1 else "?",
                    new_version=after,
                    source="firmware",
                ))
    return text_updates


class CustomCommandChecker(UpdateChecker):
    """Check for updates via user-defined shell commands.

    The command should output lines in the format:
        <name> <old_version> <something> <new_version>
    (same format as checkupdates output, parsed by _parse_checkupdates_line.)

    Configure via config.toml:
        [[sources.custom_commands]]
        name = "my-checker"
        command = ["my-script", "--check"]
        enabled = true
    """

    label: ClassVar[str] = "Custom Command"

    def __init__(self, command: list[str], display_name: str = "Custom") -> None:
        """Initialize with the command to run.

        Args:
            command: List of command arguments (no shell interpretation).
            display_name: Display name for this checker.
        """
        self._command = command
        self._display_name = display_name

    @property
    def name(self) -> str:  # type: ignore[override]
        """Return a unique name for this checker instance."""
        return custom_checker_name(self._display_name)

    def is_available(self) -> bool:
        if not self._command:
            return False
        return shutil.which(self._command[0]) is not None

    def check(self) -> list[Update]:
        r = run_checked(self._command)
        if r.returncode != 0:
            raise _command_error(self._command, r.returncode, r.stderr)
        if not r.stdout.strip():
            return []
        updates: list[Update] = []
        for line in r.stdout.strip().splitlines():
            up = _parse_checkupdates_line(line, self.name)
            if up:
                updates.append(up)
        return updates
