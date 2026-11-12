"""Update engine that orchestrates plugin discovery and execution."""

from __future__ import annotations

import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from uptray.core.logging import get_logger

if TYPE_CHECKING:
    from uptray.core.models import CheckResult, Config
    from uptray.core.provider import UpdateChecker

_MAX_PARALLEL_CHECKERS = 8


class UpdateEngine:
    """Orchestrates update checker discovery and execution."""

    def __init__(self) -> None:
        self._checkers: dict[str, UpdateChecker] = {}

    def register(self, checker: UpdateChecker) -> None:
        """Register a checker instance."""
        if checker.name in self._checkers:
            get_logger("engine").warning(
                "Replacing duplicate checker registration: %s", checker.name
            )
        self._checkers[checker.name] = checker

    def discover_builtin(self) -> None:
        """Auto-register built-in checkers."""
        # NOTE: imports are deferred so builtins.py can be created in Plan 2
        from uptray.core.checkers.builtins import (
            AurChecker,
            FirmwareChecker,
            FlatpakChecker,
            PacmanChecker,
        )
        from uptray.core.checkers.reboot import RebootRequiredChecker

        for cls in (
            PacmanChecker,
            AurChecker,
            FlatpakChecker,
            FirmwareChecker,
            RebootRequiredChecker,
        ):
            self.register(cls())

    def discover_entry_points(self) -> None:
        """Register third-party checkers from entry_points."""
        from importlib.metadata import entry_points

        log = get_logger("engine")
        eps = entry_points(group="uptray.plugins")
        for ep in eps:
            try:
                checker_cls = ep.load()
                self.register(checker_cls())
            except Exception as exc:
                log.warning("Could not load update checker plugin %s: %s", ep.name, exc)
                continue

    def available(self) -> Iterator[UpdateChecker]:
        """Yield checkers that are available on this system."""
        log = get_logger("engine")
        for c in self._checkers.values():
            try:
                is_available = c.is_available()
            except Exception as exc:
                log.warning("Checker %s availability probe failed: %s", c.name, exc)
                continue
            if is_available:
                yield c

    def check_all(
        self,
        cfg: Config | None = None,
        topgrade_disabled: set[str] | None = None,
    ) -> list[CheckResult]:
        """Run all enabled and available checkers with error isolation.

        Args:
            cfg: Configuration for filtering enabled sources.
            topgrade_disabled: Checker names disabled by topgrade.toml.

        Returns:
            List of CheckResult, one per checker attempted.
        """
        from uptray.core.models import CheckResult, Config, SourceConfig

        if cfg is None:
            cfg = Config()

        if cfg.custom_commands:
            from uptray.core.checkers.builtins import CustomCommandChecker

            for custom in cfg.custom_commands:
                if custom.enabled:
                    self.register(CustomCommandChecker(custom.command, custom.name))

        results: list[CheckResult] = []
        log = get_logger("engine")
        available_checkers = list(self.available())
        log.info("Starting update check with %d available checkers", len(available_checkers))

        def _run_one(checker: UpdateChecker) -> CheckResult:
            start = time.monotonic()
            try:
                updates = checker.check()
                result = CheckResult(
                    source=checker.name,
                    updates=updates,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                log.info(
                    "Checker %s: %d updates in %dms",
                    checker.name,
                    len(updates),
                    result.duration_ms,
                )
            except Exception as exc:
                result = CheckResult(
                    source=checker.name,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                log.warning(
                    "Checker %s failed after %dms: %s",
                    checker.name,
                    result.duration_ms,
                    exc,
                )
            return result

        targets: list[UpdateChecker] = []
        for checker in available_checkers:
            if topgrade_disabled and checker.name in topgrade_disabled:
                continue
            src_cfg = cfg.sources.get(checker.name, SourceConfig())
            if not src_cfg.enabled:
                continue
            targets.append(checker)

        if not targets:
            return results

        # Checkers are independent subprocess wrappers, so they run
        # concurrently; pool.map preserves the deterministic result order.
        workers = min(_MAX_PARALLEL_CHECKERS, len(targets))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results.extend(pool.map(_run_one, targets))

        return results
