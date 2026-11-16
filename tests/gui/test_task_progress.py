"""LauncherEntry protocol and optional-session-bus behavior."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from uptray.gui.task_progress import TaskProgress  # noqa: E402


def test_launcher_updates_use_desktop_entry_and_native_variants(qapp, monkeypatch) -> None:  # noqa: ANN001
    progress = TaskProgress()
    messages = []

    class Bus:
        def isConnected(self) -> bool:  # noqa: N802
            return True

        def send(self, message) -> bool:  # noqa: ANN001
            messages.append(message)
            return True

    monkeypatch.setattr(progress, "_bus", Bus())
    progress.update(.43)
    progress.update(.43)  # Avoid flooding Plasma with repeated percentages.
    progress.update(None)
    assert len(messages) == 2
    assert messages[0].interface() == "com.canonical.Unity.LauncherEntry"
    assert messages[0].member() == "Update"
    assert messages[0].arguments() == [
        "application://uptray.desktop", {"progress": .43, "progress-visible": True},
    ]
    assert messages[1].arguments()[1] == {"progress": 0.0, "progress-visible": False}


def test_missing_session_bus_is_harmless(qapp, monkeypatch) -> None:  # noqa: ANN001
    progress = TaskProgress()

    class Bus:
        def isConnected(self) -> bool:  # noqa: N802
            return False

    monkeypatch.setattr(progress, "_bus", Bus())
    progress.update(.5)
    progress.update(None)
