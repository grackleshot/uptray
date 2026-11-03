"""Tests for the available-updates dialog."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QTextEdit  # noqa: E402

from topgrade_update.core.models import CheckResult, Update  # noqa: E402
from topgrade_update.gui.dialog import UpdatesDialog  # noqa: E402


def test_dialog_shows_partial_checker_failures(qapp) -> None:  # noqa: ANN001
    """Users can see which sources failed alongside successful updates."""
    results = [
        CheckResult(
            source="pacman",
            updates=[Update("package", "1", "2", "pacman", branch="stable")],
        ),
        CheckResult(source="flatpak", error="remote unavailable"),
    ]
    dialog = UpdatesDialog(results)

    text = dialog.findChild(QTextEdit)
    assert text is not None
    assert "pacman (1)" in text.toPlainText()
    assert "package (stable) 1 → 2" in text.toPlainText()
    assert "flatpak: check failed — remote unavailable" in text.toPlainText()
