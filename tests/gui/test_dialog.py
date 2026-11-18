"""Tests for the available-updates, history, and maintenance dialogs."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uptray.core.history import PackageChange, UpgradeSession
from uptray.core.maintenance import MaintenanceFinding
from uptray.core.models import CheckResult, Update
from uptray.core.run_history import RunSummary

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence, QShortcut  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QTreeWidget  # noqa: E402

from uptray.core.topgrade_config import ONLY_STEP_FOR_SOURCE  # noqa: E402
from uptray.gui.dialog import (  # noqa: E402
    HistoryDialog,
    MaintenanceDialog,
    RunLogsPanel,
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
        "uptray.gui.dialog.open_url", lambda url: opened.append(url)
    )
    results = [
        CheckResult(source="aur", updates=[Update("paru-bin", "1", "2", "aur")]),
    ]
    dialog = UpdatesDialog(results)
    dialog._tree.itemActivated.emit(dialog._tree.topLevelItem(0).child(0), 0)

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


def test_saved_failure_is_visible_even_when_transcript_is_missing(
    qapp, tmp_path, monkeypatch  # noqa: ANN001
) -> None:
    summary = RunSummary(
        path=tmp_path / "missing.log", started=datetime.now(timezone.utc), duration_s=15,
        scope="Preview Flatpak", outcome="failed", returncode=2, failed_steps=("Flatpak",),
        transcript_incomplete=True,
    )
    monkeypatch.setattr("uptray.gui.dialog.list_runs", lambda _dir: [summary])
    runs = RunLogsPanel(runs_dir=tmp_path)
    label = runs._list.item(0).text()
    assert "Preview Flatpak · Failed (exit 2)" in label
    assert "Incomplete log" in label
    assert "Transcript unavailable" in runs._text.toPlainText()


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
    first.resize(1000, 700)  # well above the minimum, so nothing clamps it
    first.done(0)
    second, _ = _only_dialog("pacman")
    assert (second.width(), second.height()) == (1000, 700)


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


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_in_filter_keeps_dialog_open(qapp, key) -> None:  # noqa: ANN001
    dialog, scoped_runs = _only_dialog("flatpak")
    runs: list[str] = []
    dialog.set_on_run(lambda: runs.append("update"))
    dialog.set_on_preview(lambda: runs.append("preview"))
    dialog.show()
    dialog._focus_filter()
    QTest.keyClicks(dialog._filter, "p")
    QTest.keyClick(dialog._filter, key)
    assert dialog.isVisible()
    assert not runs and not scoped_runs
    dialog.close()


def test_keyboard_source_action_uses_selected_visible_scope(qapp) -> None:  # noqa: ANN001
    dialog, calls = _only_dialog("flatpak")
    dialog.show()
    tree = dialog._tree
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Home)
    assert tree.currentItem().text(0) == "flatpak (1)"
    assert dialog._btn_source.text() == "Update Flatpak"
    dialog._filter.setText("no match")
    assert not dialog._btn_source.isEnabled()
    dialog._filter.clear()
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Tab)
    assert dialog.focusWidget() is dialog._btn_source
    QTest.keyClick(dialog._btn_source, Qt.Key.Key_Return)
    assert calls == [["--only", "flatpak"]]
    assert not dialog.isVisible()


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
    from uptray.core.models import CheckResult
    from uptray.gui.dialog import _updates_title

    assert _updates_title(total, [CheckResult(source="pacman", error=error)]) == expected
