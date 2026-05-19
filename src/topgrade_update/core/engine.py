"""Update engine that orchestrates plugin discovery and execution."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult, Config
    from topgrade_update.core.provider import UpdateChecker


class UpdateEngine:
    """Orchestrates update checker discovery and execution."""

    def __init__(self) -> None:
        self._checkers: dict[str, UpdateChecker] = {}

    def register(self, checker: UpdateChecker) -> None:
        """Register a checker instance."""
        self._checkers[checker.name] = checker

    def discover_builtin(self) -> None:
        """Auto-register built-in checkers."""
        # NOTE: imports are deferred so builtins.py can be created in Plan 2
        from topgrade_update.core.checkers.builtins import (
            AurChecker,
            FlatpakChecker,
            PacmanChecker,
        )

        for cls in (PacmanChecker, AurChecker, FlatpakChecker):
            self.register(cls())

    def discover_entry_points(self) -> None:
        """Register third-party checkers from entry_points."""
        from importlib.metadata import entry_points

        eps = entry_points(group="topgrade_update.plugins")
        for ep in eps:
            try:
                checker_cls = ep.load()
                self.register(checker_cls())
            except Exception:
                continue

    def available(self) -> Iterator[UpdateChecker]:
        """Yield checkers that are available on this system."""
        for c in self._checkers.values():
            if c.is_available():
                yield c

    def check_all(self, cfg: Config | None = None) -> list[CheckResult]:
        """Run all enabled and available checkers with error isolation.

        Args:
            cfg: Configuration for filtering enabled sources.

        Returns:
            List of CheckResult, one per checker attempted.
        """
        from topgrade_update.core.models import CheckResult, Config, SourceConfig

        if cfg is None:
            cfg = Config()

        results: list[CheckResult] = []
        for checker in self.available():
            src_cfg = cfg.sources.get(checker.name, SourceConfig())
            if not src_cfg.enabled:
                continue

            start = time.monotonic()
            try:
                updates = checker.check()
                result = CheckResult(
                    source=checker.name,
                    updates=updates,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception as exc:
                result = CheckResult(
                    source=checker.name,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            results.append(result)

        return results
