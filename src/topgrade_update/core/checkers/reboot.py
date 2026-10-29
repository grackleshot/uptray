"""Linux reboot-required detection."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import ClassVar

from topgrade_update.core.models import Update
from topgrade_update.core.provider import UpdateChecker


class RebootRequiredChecker(UpdateChecker):
    """Detect an explicit marker or a missing running-kernel module tree.

    Merely having a kernel package installed does not mean the running kernel
    is outdated, so Arch detection checks whether the running kernel's module
    directory still exists instead of treating any installed kernel as pending.
    """

    name: ClassVar[str] = "reboot"
    label: ClassVar[str] = "Reboot"

    def is_available(self) -> bool:
        # Always available — it's a simple file check
        return True

    def check(self) -> list[Update]:
        updates: list[Update] = []

        # Check for /run/reboot-required (Debian/Ubuntu style)
        try:
            with open("/run/reboot-required") as f:
                reason = f.read().strip()
            updates.append(Update(
                name="system",
                old_version="",
                new_version=f"reboot required: {reason}",
                source=self.name,
            ))
            return updates
        except FileNotFoundError:
            pass

        if shutil.which("pacman"):
            module_root = Path("/usr/lib/modules")
            if not module_root.is_dir():
                module_root = Path("/lib/modules")
            running_release = os.uname().release
            if module_root.is_dir() and not (module_root / running_release).is_dir():
                updates.append(
                    Update(
                        name="kernel",
                        old_version=running_release,
                        new_version="reboot required",
                        source=self.name,
                    )
                )

        return updates
