from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def sent_messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record RunWindow desktop notifications instead of sending real ones.

    Offscreen windows are never the active window, so every finished run
    would otherwise pop a real notification.
    """
    sent: list[tuple[str, str]] = []
    try:
        import uptray.gui.run_window  # noqa: F401
    except ImportError:  # PySide6 missing: GUI tests skip themselves
        return sent
    for target in ("run_window", "diagnose_panel"):
        monkeypatch.setattr(
            f"uptray.gui.{target}.send_message",
            lambda summary, body, **_kw: sent.append((summary, body)),
        )
    return sent


@pytest.fixture(autouse=True)
def _delete_leftover_windows() -> Iterator[None]:
    """Destroy each test's windows while Qt is fully alive.

    Hundreds of leftover windows made PySide's exit-time cleanup crash the
    test process after every test had passed (exit 139 or 134 on CI).
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
    except ImportError:  # PySide6 missing: GUI tests skip themselves
        return
    if QApplication.instance() is None:
        return
    for widget in QApplication.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(scope="session", autouse=True)
def _no_real_update_checks() -> object:
    """Tray CheckThreads (startup timers can fire in later tests) do no real work.

    Real checks hit the network, and a thread still running at interpreter
    exit makes Qt abort the whole test process (exit 134 on CI).
    """
    try:
        from uptray.gui.tray import CheckThread
    except ImportError:  # PySide6 missing: GUI tests skip themselves
        yield None
        return
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(CheckThread, "run", lambda _self: None)
        yield None
