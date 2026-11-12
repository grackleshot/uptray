"""Notification deduplication and quiet-hours deferral logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TypedDict

from topgrade_update.core.checkers.facade import total_updates

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult


class DeferredNotification(TypedDict):
    """Queued notification payload captured during quiet hours."""

    results: list[CheckResult]
    total: int
    sources: dict[str, int]


@dataclass
class NotificationState:
    """Mutable notification decision state."""

    prev_total: int = -1
    quiet_hours_active: bool = False
    deferred_notifications: list[DeferredNotification] = field(default_factory=list)


class NotificationEngine:
    """Decide when notifications should be sent or deferred."""

    def __init__(self) -> None:
        self._state = NotificationState()

    @property
    def prev_total(self) -> int:
        """Return the update count seen by the last notification decision."""
        return self._state.prev_total

    @prev_total.setter
    def prev_total(self, value: int) -> None:
        """Restore a persisted decision count (e.g. after a tray restart)."""
        self._state.prev_total = value

    def should_notify(self, results: list[CheckResult]) -> bool:
        """Return True if a notification should be sent for these results.

        Rules:
        - notify when updates first appear (0 -> N)
        - notify when total update count increases (N -> M where M > N)
        - do not notify on no updates, same count, or decreases
        """
        total = total_updates(results)
        prev = self._state.prev_total
        self._state.prev_total = total
        return total > 0 and (prev == 0 or total > prev)

    def enter_quiet_hours(self) -> None:
        """Mark quiet hours active."""
        self._state.quiet_hours_active = True

    def reset_deduplication(self) -> None:
        """Allow the current updates to notify again after an explicit snooze."""
        self._state.prev_total = 0

    def exit_quiet_hours(self) -> list[DeferredNotification]:
        """Mark quiet hours inactive, return queued notifications, and clear the queue."""
        self._state.quiet_hours_active = False
        deferred = self._state.deferred_notifications
        self._state.deferred_notifications = []
        return deferred

    def maybe_defer(self, results: list[CheckResult]) -> bool:
        """Queue results if quiet hours are active.

        Returns True when queued; returns False when caller should send immediately.
        """
        if not self._state.quiet_hours_active:
            return False
        self._state.deferred_notifications.append(
            {
                "results": results,
                "total": total_updates(results),
                "sources": _source_counts(results),
            }
        )
        return True


def _source_counts(results: list[CheckResult]) -> dict[str, int]:
    return {
        result.source: len(result.updates)
        for result in results
        if result.updates and result.source != "reboot"
    }
