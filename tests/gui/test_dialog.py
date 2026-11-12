"""Tests for the available-updates, history, and maintenance dialogs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from topgrade_update.core.history import PackageChange, UpgradeSession
from topgrade_update.core.maintenance import MaintenanceFinding
from topgrade_update.core.models import CheckResult, Update

pytest.importorskip("PySide6")

from PySide6.QtGui import QKeySequence, QShortcut  # noqa: E402
from PySide6.QtWidgets import QTreeWidget  # noqa: E402

from topgrade_update.core.topgrade_config import ONLY_STEP_FOR_SOURCE  # noqa: E402
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


def test_history_dialog_has_runs_tab_with_clean_text(qapp, tmp_path) -> None:  # noqa: ANN001
    (tmp_path / "20261105T090000Z-1-1.log").write_text(
        "\x1b[1m── 12:00:00 - Summary ────\x1b[0m\n"
    )
    dialog = HistoryDialog([], runs_dir=tmp_path)

    assert [dialog._tabs.tabText(i) for i in range(dialog._tabs.count())] == [
        "System log",
        "Runs",
    ]
    runs = dialog._tabs.widget(1)
    assert runs._list.count() == 1
    assert "Summary" in runs._text.toPlainText()
    assert "\x1b" not in runs._text.toPlainText()


def _only_dialog(source: str) -> tuple[UpdatesDialog, list[list[str]]]:
    dialog = UpdatesDialog([CheckResult(source=source, updates=[Update("p", "1", "2", source)])])
    calls: list[list[str]] = []
    dialog.set_on_run_only(calls.append)
    return dialog, calls


@pytest.mark.parametrize(
    ("source", "step"), [("pacman", "system"), ("aur", "system"), ("flatpak", "flatpak")]
)
def test_updates_dialog_run_only_passes_topgrade_step(qapp, source, step) -> None:  # noqa: ANN001
    dialog, calls = _only_dialog(source)
    assert ONLY_STEP_FOR_SOURCE[source] == step
    dialog._run_only(step)
    assert calls == [["--only", step]]


def test_updates_dialog_size_is_remembered(qapp) -> None:  # noqa: ANN001
    first, _ = _only_dialog("pacman")
    first.resize(777, 555)
    first.done(0)
    second, _ = _only_dialog("pacman")
    assert (second.width(), second.height()) == (777, 555)


def test_updates_dialog_ctrl_f_focuses_filter(qapp) -> None:  # noqa: ANN001
    dialog, _ = _only_dialog("pacman")
    dialog.show()
    dialog._tree.setFocus()
    shortcut = dialog.findChild(QShortcut)
    assert shortcut is not None
    assert shortcut.key() == QKeySequence(QKeySequence.StandardKey.Find)
    shortcut.activated.emit()
    assert dialog.focusWidget() is dialog._filter
    dialog.close()


@pytest.mark.parametrize(
    ("total", "error", "expected"),
    [
        (1, None, "1 update available"),
        (3, None, "3 updates available"),
        (0, "boom", "Some sources couldn't be checked"),
        (0, None, "No updates available"),
    ],
)
def test_updates_title(total: int, error: str | None, expected: str) -> None:
    from topgrade_update.core.models import CheckResult
    from topgrade_update.gui.dialog import _updates_title

    assert _updates_title(total, [CheckResult(source="pacman", error=error)]) == expected
