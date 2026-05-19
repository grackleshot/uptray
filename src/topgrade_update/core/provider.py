"""Plugin ABC for update checkers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from topgrade_update.core.models import Update


class UpdateChecker(ABC):
    """Abstract base class for update checkers."""

    name: ClassVar[str]
    label: ClassVar[str]

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this checker can run on this system."""

    @abstractmethod
    def check(self) -> list[Update]:
        """Check for updates and return a list of available updates."""
