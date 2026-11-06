"""Dialogs for the system tray applet."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from topgrade_update.core.links import upstream_url

if TYPE_CHECKING:
    from collections.abc import Callable

    from topgrade_update.core.history import UpgradeSession
    from topgrade_update.core.maintenance import MaintenanceFinding
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"


def open_url(url: str) -> None:
    """Open a URL in the user's default browser; empty URLs are ignored."""
    if url:
        QDesktopServices.openUrl(QUrl(url))


def format_updates_text(results: list[CheckResult]) -> str:
    """Render check results as the shared plain-text update listing."""
    lines: list[str] = []
    for result in results:
        if result.updates:
            lines.append(f"{result.source} ({len(result.updates)})")
            for update in result.updates:
                branch = f" ({update.branch})" if update.branch else ""
                lines.append(f"  {update.name}{branch} {update.old_version} → {update.new_version}")
            lines.append("")
        if result.error is not None:
            lines.append(f"{result.source}: check failed — {result.error}")
            lines.append("")
    return "\n".join(lines).rstrip()


class UpdatesDialog(QDialog):
    """Dialog showing available updates grouped by source in a tree."""

    def __init__(self, results: list[CheckResult], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Available Updates")
        self.setMinimumSize(560, 420)
        self._results = results
        self._source_of_item: dict[QTreeWidgetItem, str] = {}

        layout = QVBoxLayout(self)

        total = sum(len(r.updates) for r in results)
        header = QLabel(f"<b>{total} update(s) available</b>")
        layout.addWidget(header)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Package", "Current", "New"])
        self._tree.setRootIsDecorated(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree)

        for result in results:
            if result.updates:
                source_item = QTreeWidgetItem(
                    self._tree, [f"{result.source} ({len(result.updates)})"]
                )
                source_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                for update in result.updates:
                    branch = f" ({update.branch})" if update.branch else ""
                    child = QTreeWidgetItem(
                        source_item,
                        [f"{update.name}{branch}", update.old_version, update.new_version],
                    )
                    self._source_of_item[child] = result.source
            if result.error is not None:
                error_item = QTreeWidgetItem(
                    self._tree, [f"{result.source}: check failed — {result.error}"]
                )
                error_item.setFlags(Qt.ItemFlag.ItemIsEnabled)

        self._tree.expandAll()
        self._tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy List")
        btn_copy.clicked.connect(self._copy_list)
        btn_preview = QPushButton("Preview (Dry Run)")
        btn_preview.clicked.connect(self._preview)
        btn_upgrade = QPushButton("Run Topgrade")
        btn_upgrade.clicked.connect(self._run_topgrade)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_preview)
        btn_row.addWidget(btn_upgrade)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._on_run: Callable[[], None] | None = None
        self._on_preview: Callable[[], None] | None = None

    def set_on_run(self, callback: Callable[[], None]) -> None:
        """Set the callback for the Run Topgrade button."""
        self._on_run = callback

    def set_on_preview(self, callback: Callable[[], None]) -> None:
        """Set the callback for the Preview (Dry Run) button."""
        self._on_preview = callback

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        source = self._source_of_item.get(item)
        if source is None:
            return
        package = item.text(0).split(" (")[0]
        open_url(upstream_url(package, source))

    def _copy_list(self) -> None:
        from PySide6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(format_updates_text(self._results))

    def _preview(self) -> None:
        if self._on_preview:
            self._on_preview()
        self.close()

    def _run_topgrade(self) -> None:
        if self._on_run:
            self._on_run()
        self.close()


class HistoryDialog(QDialog):
    """Dialog listing recent upgrade sessions parsed from pacman.log."""

    def __init__(
        self,
        sessions: list[UpgradeSession],
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Update History")
        self.setMinimumSize(640, 420)
        self._sessions = list(reversed(sessions))  # newest first

        layout = QHBoxLayout(self)

        self._list = QListWidget()
        for index, session in enumerate(self._sessions):
            counts = session.counts()
            label = (
                f"{session.started.strftime('%Y-%m-%d %H:%M')} — "
                f"{counts['upgraded']} upgraded, {counts['installed']} installed, "
                f"{counts['removed']} removed"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, index)
            self._list.addItem(item)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list, 1)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        layout.addWidget(self._detail, 2)

        if self._sessions:
            self._list.setCurrentRow(0)
        else:
            self._detail.setPlainText("No recorded upgrade sessions found.")

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        outer = QVBoxLayout()
        outer.addLayout(layout)
        outer.addLayout(btn_row)
        self.setLayout(outer)

    def _on_row_changed(self, row: int) -> None:
        if not 0 <= row < len(self._sessions):
            return
        session = self._sessions[row]
        lines = [
            f"Started: {session.started.strftime('%Y-%m-%d %H:%M')}",
            (
                f"Finished: {session.finished.strftime('%Y-%m-%d %H:%M')}"
                if session.finished
                else "Finished: (unknown)"
            ),
            "",
        ]
        for change in session.changes:
            if change.action == "upgraded":
                lines.append(
                    f"upgraded {change.name} ({change.old_version} → {change.new_version})"
                )
            elif change.action == "installed":
                lines.append(f"installed {change.name} ({change.new_version})")
            else:
                lines.append(f"removed {change.name} ({change.old_version})")
        self._detail.setPlainText("\n".join(lines))


class MaintenanceDialog(QDialog):
    """Dialog showing post-update maintenance findings."""

    def __init__(
        self,
        findings: list[MaintenanceFinding],
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Maintenance")
        self.setMinimumSize(480, 360)

        layout = QVBoxLayout(self)

        if findings:
            layout.addWidget(QLabel("<b>Post-update maintenance suggestions</b>"))
        else:
            layout.addWidget(QLabel("No maintenance needed. Your system looks clean."))

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        lines: list[str] = []
        for finding in findings:
            lines.append(f"• {finding.summary}")
            lines.extend(f"    {detail}" for detail in finding.detail)
            lines.append("")
        self._detail.setPlainText("\n".join(lines).rstrip())
        layout.addWidget(self._detail)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
