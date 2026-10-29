"""Update checker facade — delegates to UpdateEngine."""

from topgrade_update.core.checkers.builtins import (
    AurChecker,
    FirmwareChecker,
    FlatpakChecker,
    PacmanChecker,
)
from topgrade_update.core.checkers.facade import check_all, find_terminal, total_updates
from topgrade_update.core.checkers.reboot import RebootRequiredChecker

__all__ = [
    "PacmanChecker",
    "AurChecker",
    "FlatpakChecker",
    "FirmwareChecker",
    "RebootRequiredChecker",
    "check_all",
    "total_updates",
    "find_terminal",
]
