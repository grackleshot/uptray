"""Tests that built-in checkers are properly registered in the engine."""

from __future__ import annotations

import threading
import time

from uptray.core.engine import UpdateEngine
from uptray.core.models import Update
from uptray.core.provider import UpdateChecker


def test_all_builtin_checkers_registered() -> None:
    """Engine should discover all built-in checkers."""
    engine = UpdateEngine()
    engine.discover_builtin()

    registered_names = set(engine._checkers.keys())
    expected = {"pacman", "aur", "flatpak", "firmware", "reboot"}
    assert expected.issubset(registered_names), (
        f"Missing checkers: {expected - registered_names}"
    )


def test_reboot_checker_is_available() -> None:
    """Reboot checker should always be available."""
    engine = UpdateEngine()
    engine.discover_builtin()
    reboot = engine._checkers.get("reboot")
    assert reboot is not None
    assert reboot.is_available() is True


class _ConcurrencyProbe:
    """Records how many checkers are simultaneously inside check()."""

    def __init__(self) -> None:
        self.active = 0
        self.peak = 0
        self._lock = threading.Lock()

    def enter(self) -> None:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)

    def exit(self) -> None:
        with self._lock:
            self.active -= 1


class _FakeChecker(UpdateChecker):
    """Slow checker that reports overlap through a shared probe."""

    name = ""
    label = ""

    def __init__(self, name: str, delay: float, probe: _ConcurrencyProbe) -> None:
        self.name = name
        self.label = name
        self._delay = delay
        self._probe = probe

    def is_available(self) -> bool:
        return True

    def check(self) -> list[Update]:
        self._probe.enter()
        time.sleep(self._delay)
        self._probe.exit()
        return [Update(name=self.name, old_version="1", new_version="2", source=self.name)]


def test_checkers_run_concurrently_and_keep_registration_order() -> None:
    """Slow checkers overlap instead of queueing, and results keep order."""
    probe = _ConcurrencyProbe()
    engine = UpdateEngine()
    for index in range(4):
        engine.register(_FakeChecker(f"slow{index}", delay=0.2, probe=probe))

    started = time.monotonic()
    results = engine.check_all()

    elapsed = time.monotonic() - started
    assert [r.source for r in results] == [f"slow{i}" for i in range(4)]
    # Sequential execution would take >= 0.8s; overlap should be well under.
    assert elapsed < 0.7
    assert probe.peak >= 2, "checkers did not run concurrently"

