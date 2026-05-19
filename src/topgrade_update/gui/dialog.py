"""Updates dialog for the system tray applet."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from topgrade_update.core.models import CheckResult

APP_NAME = "Topgrade Update"


class UpdatesDialog(QDialog):  # type: ignore[misc]
    """Dialog showing available updates with a Run Topgrade button."""

    def __init__(self, results: list[CheckResult], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — Available Updates")
        self.setMinimumSize(520, 400)

        layout = QVBoxLayout(self)

        total = sum(len(r.updates) for r in results)
        header = QLabel(f"<b>{total} update(s) available</b>")
        layout.addWidget(header)

        text = QTextEdit()
        text.setReadOnly(True)
        lines: list[str] = []
        for r in results:
            if r.updates:
                lines.append(f"<b>{r.source} ({len(r.updates)})</b>")
                for up in r.updates:
                    lines.append(f"&nbsp;&nbsp;{up.name} {up.old_version} → {up.new_version}")
                lines.append("")
        text.setHtml("<br>".join(lines))
        layout.addWidget(text)

        btn_row = QHBoxLayout()
        btn_upgrade = QPushButton("Run Topgrade")
        btn_upgrade.clicked.connect(self._run_topgrade)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addStretch()
        btn_row.addWidget(btn_upgrade)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._on_run: Callable[[], None] | None = None

    def set_on_run(self, callback: Callable[[], None]) -> None:
        """Set the callback for the Run Topgrade button."""
        self._on_run = callback

    def _run_topgrade(self) -> None:
        if self._on_run:
            self._on_run()
        self.close()
