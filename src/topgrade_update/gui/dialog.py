"""Dialogs for the system tray applet."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QSize, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFontDatabase,
    QKeySequence,
    QShortcut,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from topgrade_update.core.links import upstream_url
from topgrade_update.core.run_history import RunSummary, list_runs
from topgrade_update.core.topgrade_config import ONLY_STEP_FOR_SOURCE
from topgrade_update.core.topgrade_session import default_runs_dir, strip_ansi
from topgrade_update.gui.icons import ICON_MD, ICON_SM, status_pixmap
from topgrade_update.gui.style import (
    apply_theme,
    colors,
    restore_window_state,
    save_window_state,
    set_primary,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


def _make_header(title: str, subtitle: str | None = None) -> QWidget:
    """Build a title/subtitle header block with typographic hierarchy."""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    label = QLabel(title)
    font = label.font()
    font.setPointSizeF(font.pointSizeF() + 4)
    font.setBold(True)
    label.setFont(font)
    layout.addWidget(label)
    if subtitle:
        tokens = colors()
        sub = QLabel(f'<span style="color:{tokens["muted"]}">{subtitle}</span>')
        layout.addWidget(sub)
    return box


def _banner(text: str, detail: str, kind: str = "warning") -> QFrame:
    """Build a tinted banner strip with a status icon and two-line message."""
    tokens = colors()
    fg_key, bg_key = (
        ("warning", "warning_bg") if kind == "warning" else ("danger", "danger_bg")
    )
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background: {tokens[bg_key]};"
        f" border: 1px solid {tokens[fg_key]}; border-radius: 10px; }}"
        "QLabel { background: transparent; border: none; }"
    )
    row = QHBoxLayout(frame)
    row.setContentsMargins(12, 8, 12, 8)
    row.setSpacing(10)
    icon = QLabel()
    icon.setPixmap(status_pixmap(kind, ICON_MD))
    row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    text_box = QVBoxLayout()
    text_box.setSpacing(0)
    title = QLabel(f"<b>{text}</b>")
    sub = QLabel(f'<span style="color:{tokens[fg_key]}">{detail}</span>')
    text_box.addWidget(title)
    text_box.addWidget(sub)
    row.addLayout(text_box, 1)
    return frame


def _monospace() -> str:
    """Return the platform fixed-pitch font family for log panes."""
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()


def _updates_title(total: int, results: list[CheckResult]) -> str:
    """Headline for the updates dialog, which also opens for errors or a reboot."""
    if total:
        return f"{total} update{'s' if total != 1 else ''} available"
    if any(r.error is not None for r in results):
        return "Some sources couldn't be checked"
    return "No updates available"


class UpdatesDialog(QDialog):
    """Dialog showing available updates grouped by source in a tree."""

    def __init__(self, results: list[CheckResult], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        apply_theme(self)
        self.setWindowTitle(f"{APP_NAME} — Available Updates")
        self.setMinimumSize(640, 480)
        self._results = [r for r in results if r.source != "reboot"]
        self._reboot_pending = any(r.source == "reboot" and r.updates for r in results)
        self._source_of_item: dict[QTreeWidgetItem, str] = {}
        self._on_run: Callable[[], None] | None = None
        self._on_preview: Callable[[], None] | None = None
        self._on_run_only: Callable[[list[str]], None] | None = None
        self._source_of_header: dict[QTreeWidgetItem, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        total = sum(len(r.updates) for r in self._results)
        counts = [f"{r.source} {len(r.updates)}" for r in self._results if r.updates]
        subtitle = " · ".join(counts) if counts else "Nothing to update right now"
        layout.addWidget(_make_header(_updates_title(total, self._results), subtitle))

        if self._reboot_pending:
            layout.addWidget(
                _banner(
                    "Reboot required",
                    "Restart to finish applying system updates.",
                    kind="warning",
                )
            )

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter packages… (Ctrl+F)")
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)
        layout.addWidget(self._filter)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self).activated.connect(
            self._focus_filter
        )

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderLabels(["Package", "Current", "New"])
        self._tree.setRootIsDecorated(True)
        self._tree.setIconSize(QSize(ICON_SM, ICON_SM))
        self._tree.setUniformRowHeights(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setToolTip("Double-click a package to open its project page.")
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._source_menu)
        layout.addWidget(self._tree, 1)

        for result in self._results:
            if result.updates:
                source_item = QTreeWidgetItem(
                    self._tree, [f"{result.source} ({len(result.updates)})"]
                )
                source_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self._source_of_header[source_item] = result.source
                font = source_item.font(0)
                font.setBold(True)
                source_item.setFont(0, font)
                for update in result.updates:
                    branch = f" ({update.branch})" if update.branch else ""
                    child = QTreeWidgetItem(
                        source_item,
                        [f"{update.name}{branch}", update.old_version, update.new_version],
                    )
                    self._source_of_item[child] = result.source
            if result.error is not None:
                tokens = colors()
                error_item = QTreeWidgetItem(
                    self._tree,
                    [f"{result.source}: check failed — {result.error}"],
                )
                error_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                error_item.setIcon(0, status_pixmap("warning", ICON_SM))
                error_item.setForeground(0, QColor(tokens["warning"]))
                error_item.setToolTip(0, result.error)

        self._tree.expandAll()
        self._tree.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        muted = colors()["muted"]
        hint = QLabel(
            f'<span style="color:{muted}">'
            "Double-click a package to see what changed upstream.</span>"
        )
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Copy List")
        btn_copy.setToolTip("Copy the full update list as plain text")
        btn_copy.clicked.connect(self._copy_list)
        btn_preview = QPushButton("Preview (Dry Run)")
        btn_preview.clicked.connect(self._preview)
        btn_upgrade = QPushButton("Update Now")
        btn_upgrade.setToolTip("Run topgrade to bring everything up to date")
        set_primary(btn_upgrade)
        btn_upgrade.setDefault(True)
        btn_upgrade.clicked.connect(self._run_topgrade)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_preview)
        btn_row.addWidget(btn_upgrade)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
        restore_window_state(self, "updates_dialog")

    def done(self, result: int) -> None:
        save_window_state(self, "updates_dialog")
        super().done(result)

    def set_on_run(self, callback: Callable[[], None]) -> None:
        """Set the callback for the Update Now button."""
        self._on_run = callback

    def set_on_preview(self, callback: Callable[[], None]) -> None:
        """Set the callback for the Preview (Dry Run) button."""
        self._on_preview = callback

    def set_on_run_only(self, callback: Callable[[list[str]], None]) -> None:
        """Set the callback for "Update only this source" (receives topgrade args)."""
        self._on_run_only = callback

    def _focus_filter(self) -> None:
        self._filter.setFocus()
        self._filter.selectAll()

    def _source_menu(self, pos: QPoint) -> None:
        item = self._tree.itemAt(pos)
        source = self._source_of_header.get(item) if item is not None else None
        step = ONLY_STEP_FOR_SOURCE.get(source or "")
        if step is None or self._on_run_only is None:
            return
        menu = QMenu(self)
        # pacman and AUR share topgrade's "system" step, so say so in the label.
        label = "Update only system packages (pacman + AUR)" if step == "system" else (
            "Update only this source"
        )
        action = menu.addAction(label)
        action.triggered.connect(lambda: self._run_only(step))
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _run_only(self, step: str) -> None:
        if self._on_run_only:
            self._on_run_only(["--only", step])
        self.close()

    def _apply_filter(self, text: str) -> None:
        """Show only packages whose name matches the filter text."""
        needle = text.strip().lower()
        for row in range(self._tree.topLevelItemCount()):
            root = self._tree.topLevelItem(row)
            if root is None:
                continue
            if root.childCount() == 0:
                # Error rows stay visible unless they clearly don't match.
                root.setHidden(bool(needle) and needle not in root.text(0).lower())
                continue
            visible_children = 0
            for child_row in range(root.childCount()):
                child = root.child(child_row)
                if child is None:
                    continue
                match = needle in child.text(0).lower()
                child.setHidden(bool(needle) and not match)
                if match or not needle:
                    visible_children += 1
            root.setHidden(needle != "" and visible_children == 0)

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


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def _run_label(run: RunSummary) -> str:
    stamp = run.started.astimezone().strftime("%Y-%m-%d %H:%M")
    label = f"{stamp} · {_format_duration(run.duration_s)} · {run.outcome}"
    return f"{label} · {run.failed_steps[0]}" if run.failed_steps else label


class RunLogsPanel(QWidget):
    """Saved topgrade run transcripts: a summary list beside the log text."""

    def __init__(
        self,
        current: Path | None = None,
        *,
        runs_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._runs_dir = runs_dir if runs_dir is not None else default_runs_dir()
        runs = list_runs(self._runs_dir)
        self._paths = [run.path for run in runs]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        body = QHBoxLayout()
        body.setSpacing(12)
        self._list = QListWidget()
        for run in runs:
            label = _run_label(run)
            self._list.addItem(f"● {label}" if run.path == current else label)
        self._list.currentRowChanged.connect(self._show_row)
        body.addWidget(self._list, 2)
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        body.addWidget(self._text, 3)
        layout.addLayout(body, 1)

        btn_folder = QPushButton("Open folder")
        btn_folder.clicked.connect(
            lambda: open_url(QUrl.fromLocalFile(str(self._runs_dir)).toString())
        )
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(self._text.toPlainText())
        )
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_folder)
        row.addWidget(btn_copy)
        layout.addLayout(row)

        if runs:
            self._list.setCurrentRow(
                self._paths.index(current) if current in self._paths else 0
            )
        else:
            self._text.setPlainText("No run logs found.")

    def _show_row(self, row: int) -> None:
        if not 0 <= row < len(self._paths):
            return
        path = self._paths[row]
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self._text.setPlainText(f"Could not read {path}: {exc}")
            return
        self._text.setPlainText(strip_ansi(text))
        self._text.moveCursor(QTextCursor.MoveOperation.Start)


class ReviewLogDialog(QDialog):
    """Browse the current run transcript and earlier saved runs."""

    def __init__(
        self,
        current: Path | None,
        *,
        runs_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        apply_theme(self)
        self.setWindowTitle(f"{APP_NAME} — Logs")
        self.setMinimumSize(760, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(_make_header("Run logs", "Full transcripts of past update runs"))
        self._panel = RunLogsPanel(current, runs_dir=runs_dir)
        self._list = self._panel._list
        layout.addWidget(self._panel, 1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class HistoryDialog(QDialog):
    """Dialog listing recent upgrade sessions parsed from pacman.log."""

    def __init__(
        self,
        sessions: list[UpgradeSession],
        parent: QDialog | None = None,
        *,
        runs_dir: Path | None = None,
    ) -> None:
        super().__init__(parent)
        apply_theme(self)
        self.setWindowTitle(f"{APP_NAME} — Update History")
        self.setMinimumSize(680, 460)
        self._sessions = list(reversed(sessions))  # newest first

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(
            _make_header(
                "Update History",
                "Past updates: pacman’s log and your in-app runs",
            )
        )

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.setContentsMargins(0, 8, 0, 0)
        self._tabs.addTab(system_tab, "System log")
        self._tabs.addTab(RunLogsPanel(runs_dir=runs_dir), "Runs")

        body = QHBoxLayout()
        body.setSpacing(12)

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
        body.addWidget(self._list, 1)

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        body.addWidget(self._detail, 2)

        system_layout.addLayout(body, 1)

        if self._sessions:
            self._list.setCurrentRow(0)
        else:
            tokens = colors()
            self._detail.setHtml(
                f'<span style="color:{tokens["muted"]}">'
                "No recorded upgrade sessions found.</span>"
            )

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

    def _on_row_changed(self, row: int) -> None:
        if not 0 <= row < len(self._sessions):
            return
        tokens = colors()
        session = self._sessions[row]
        finished = (
            session.finished.strftime("%Y-%m-%d %H:%M")
            if session.finished
            else "(unknown)"
        )
        action_colors = {
            "upgraded": tokens["accent"],
            "installed": tokens["success"],
            "removed": tokens["danger"],
        }
        lines = [
            f'<span style="color:{tokens["muted"]}">Started '
            f"{session.started.strftime('%Y-%m-%d %H:%M')} — Finished {finished}</span>",
            "",
        ]
        for change in session.changes:
            color = action_colors.get(change.action, tokens["text"])
            if change.action == "upgraded":
                text = (
                    f"upgraded {change.name} "
                    f"({change.old_version} → {change.new_version})"
                )
            elif change.action == "installed":
                text = f"installed {change.name} ({change.new_version})"
            else:
                text = f"removed {change.name} ({change.old_version})"
            lines.append(f'<span style="color:{color}">{text}</span>')
        self._detail.setHtml("<br>".join(lines))


class MaintenanceDialog(QDialog):
    """Dialog showing post-update maintenance findings."""

    def __init__(
        self,
        findings: list[MaintenanceFinding],
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        apply_theme(self)
        self.setWindowTitle(f"{APP_NAME} — Maintenance")
        self.setMinimumSize(560, 400)
        tokens = colors()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        if findings:
            layout.addWidget(
                _make_header(
                    "Maintenance suggested",
                    "Post-update cleanup worth running soon",
                )
            )
        else:
            layout.addWidget(
                _make_header(
                    f'<span style="color:{tokens["success"]}">All clean</span>',
                    "No maintenance needed right now",
                )
            )

        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        parts: list[str] = []
        for finding in findings:
            body = "<br>".join(
                f'<span style="color:{tokens["muted"]}">&nbsp;&nbsp;· {detail}</span>'
                for detail in finding.detail
            )
            parts.append(f"<b>{finding.summary}</b>" + (f"<br>{body}" if body else ""))
        self._detail.setHtml("<br><br>".join(parts))
        layout.addWidget(self._detail, 1)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
