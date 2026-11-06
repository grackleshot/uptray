"""Tests for the available-updates, history, and maintenance dialogs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from topgrade_update.core.history import PackageChange, UpgradeSession
from topgrade_update.core.maintenance import MaintenanceFinding
from topgrade_update.core.models import CheckResult, Update

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QTreeWidget  # noqa: E402

from topgrade_update.gui.dialog import (  # noqa: E402
    HistoryDialog,
    MaintenanceDialog,
    UpdatesDialog,
)


def test_updates_dialog_groups_packages_by_source(qapp) -> None:  # noqa: ANN001
    """Users can see which sources failed alongside successful updates."""
    results = [
        CheckResult(
            source="pacman",
            updates=[Update("package", "1", "2", "pacman", branch="stable")],
        ),
        CheckResult(source="flatpak", error="remote unavailable"),
    ]
    dialog = UpdatesDialog(results)

    tree = dialog.findChild(QTreeWidget)
    assert tree is not None
    top_level = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]
    assert "pacman (1)" in top_level
    assert any("flatpak: check failed — remote unavailable" in label for label in top_level)

    package_item = tree.topLevelItem(0).child(0)
    assert package_item.text(0) == "package (stable)"
    assert package_item.text(1) == "1"
    assert package_item.text(2) == "2"


def test_updates_dialog_double_click_opens_upstream_url(
    qapp, monkeypatch  # noqa: ANN001
) -> None:
    opened: list[str] = []

    monkeypatch.setattr(
        "topgrade_update.gui.dialog.open_url", lambda url: opened.append(url)
    )
    results = [
        CheckResult(source="aur", updates=[Update("paru-bin", "1", "2", "aur")]),
    ]
    dialog = UpdatesDialog(results)
    dialog._on_item_double_clicked(dialog._tree.topLevelItem(0).child(0), 0)

    assert opened == ["https://aur.archlinux.org/packages/paru-bin/"]


def test_updates_dialog_copy_list_uses_shared_formatter(
    qapp, monkeypatch  # noqa: ANN001
) -> None:
    copied: list[str] = []

    class FakeClipboard:
        def setText(self, text: str) -> None:  # noqa: N802
            copied.append(text)

    monkeypatch.setattr(
        "PySide6.QtWidgets.QApplication.clipboard",
        staticmethod(lambda: FakeClipboard()),
    )
    results = [
        CheckResult(source="pacman", updates=[Update("pkg", "1.0", "2.0", "pacman")]),
    ]
    dialog = UpdatesDialog(results)

    dialog._copy_list()

    assert copied == ["pacman (1)\n  pkg 1.0 → 2.0"]


def _session() -> UpgradeSession:
    started = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
    return UpgradeSession(
        started=started,
        finished=started,
        changes=[
            PackageChange("upgraded", "firefox", "130.0", "130.1"),
            PackageChange("installed", "newpkg", "", "1.0"),
        ],
    )


def test_history_dialog_lists_sessions_newest_first(qapp) -> None:  # noqa: ANN001
    dialog = HistoryDialog([_session()])

    labels = [dialog._list.item(i).text() for i in range(dialog._list.count())]
    assert labels == ["2026-11-05 09:00 — 1 upgraded, 1 installed, 0 removed"]
    assert "upgraded firefox (130.0 → 130.1)" in dialog._detail.toPlainText()
    assert "installed newpkg (1.0)" in dialog._detail.toPlainText()


def test_history_dialog_empty_state(qapp) -> None:  # noqa: ANN001
    dialog = HistoryDialog([])

    assert dialog._detail.toPlainText() == "No recorded upgrade sessions found."


def test_maintenance_dialog_lists_findings(qapp) -> None:  # noqa: ANN001
    findings = [
        MaintenanceFinding(
            kind="orphans",
            summary="2 orphan package(s) installed",
            detail=["foo", "bar"],
        )
    ]
    dialog = MaintenanceDialog(findings)

    assert "2 orphan package(s) installed" in dialog._detail.toPlainText()
    assert "foo" in dialog._detail.toPlainText()
