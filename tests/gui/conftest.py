from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def sent_messages(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record RunWindow desktop notifications instead of sending real ones.

    Offscreen windows are never the active window, so every finished run
    would otherwise pop a real notification.
    """
    sent: list[tuple[str, str]] = []
    try:
        import topgrade_update.gui.run_window  # noqa: F401
    except ImportError:  # PySide6 missing: GUI tests skip themselves
        return sent
    monkeypatch.setattr(
        "topgrade_update.gui.run_window.send_message",
        lambda summary, body, **_kw: sent.append((summary, body)),
    )
    return sent
