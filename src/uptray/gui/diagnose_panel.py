"""Diagnose drawer: pick an agent CLI and run it in an embedded terminal."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from uptray.core.notifications import send_message
from uptray.core.topgrade_session import (
    OutputChunk,
    SessionFinished,
    TopgradeSession,
    available_agents,
    build_agent_command,
)
from uptray.gui.style import colors
from uptray.gui.terminal_widget import TerminalWidget, webengine_available

if TYPE_CHECKING:
    from collections.abc import Callable

    from uptray.core.models import Config


class DiagnosePanel(QFrame):
    """Agent picker + terminal frame; owns the agent session."""

    agent_event = Signal(object)

    def __init__(
        self,
        cfg: Config,
        runs_dir: Path,
        prompt: Callable[[], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._runs_dir = runs_dir
        self._diagnose_prompt = prompt
        self._agent_session: TopgradeSession | None = None
        self.agent_event.connect(self._on_agent_event)

        tokens = colors()
        self.setStyleSheet(
            f"QFrame {{ background: {tokens['card']};"
            f" border: 1px solid {tokens['border']}; border-radius: 10px; }}"
            "QLabel { background: transparent; border: none; }"
        )
        diag_layout = QVBoxLayout(self)
        diag_layout.setContentsMargins(12, 10, 12, 12)
        diag_layout.setSpacing(8)
        picker = QHBoxLayout()
        picker.setSpacing(8)
        diag_title = QLabel("<b>Diagnose the failure</b>")
        picker.addWidget(diag_title)
        picker.addStretch()
        picker.addWidget(QLabel(f'<span style="color:{tokens["muted"]}">Agent</span>'))
        self._agent_combo = QComboBox()
        for name in available_agents():
            self._agent_combo.addItem(name)
        picker.addWidget(self._agent_combo)
        self._btn_start_agent = QPushButton("Start session")
        self._btn_start_agent.clicked.connect(self._start_agent)
        self._btn_end_agent = QPushButton("End session")
        self._btn_end_agent.clicked.connect(self._end_agent)
        self._btn_end_agent.setEnabled(False)
        picker.addWidget(self._btn_start_agent)
        picker.addWidget(self._btn_end_agent)
        if not webengine_available():
            open_term = QPushButton("Open in terminal")
            open_term.clicked.connect(self._open_agent_external)
            picker.addWidget(open_term)
        diag_layout.addLayout(picker)
        self._agent_term = TerminalWidget()
        self._agent_term.input_ready.connect(self._agent_write)
        self._agent_term.set_resize_handler(self._on_agent_resize)
        diag_layout.addWidget(self._agent_term)
        self.setMinimumHeight(200)
        self.hide()

    def _agent_write(self, data: str) -> None:
        if self._agent_session is not None:
            self._agent_session.write(data)

    def _on_agent_resize(self, rows: int, cols: int) -> None:
        if self._agent_session is not None:
            self._agent_session.resize(rows, cols)

    def _start_agent(self) -> None:
        if self._agent_combo.count() == 0:
            QMessageBox.information(
                self, "No agents", "Install claude, codex, or pi to diagnose failures."
            )
            return
        agent = self._agent_combo.currentText()
        prompt = self._diagnose_prompt()
        try:
            command = build_agent_command(agent, prompt)
        except ValueError as exc:
            QMessageBox.warning(self, "Agent error", str(exc))
            return
        self._end_agent()
        self._agent_term.clear()
        self._agent_session = TopgradeSession(
            command,
            cwd=Path.home(),
            # Kept apart so diagnose transcripts never show up as update runs.
            runs_dir=self._runs_dir / "agents",
            enable_askpass=False,
            on_event=self.agent_event.emit,
        )
        try:
            self._agent_session.start()
        except OSError as exc:
            QMessageBox.warning(self, "Could not start agent", str(exc))
            self._agent_session = None
            return
        self._btn_start_agent.setEnabled(False)
        self._btn_end_agent.setEnabled(True)
        self._agent_term.focus_terminal()

    def _on_agent_event(self, event: object) -> None:
        # Marshal to GUI thread via the same signal pattern used for topgrade.
        if isinstance(event, OutputChunk):
            self._agent_term.write(event.text)
        elif isinstance(event, SessionFinished):
            self._btn_start_agent.setEnabled(True)
            self._btn_end_agent.setEnabled(False)

    def _end_agent(self) -> None:
        if self._agent_session is None:
            return
        self._agent_session.cancel()
        self._agent_session.close()
        self._agent_session = None
        self._btn_start_agent.setEnabled(True)
        self._btn_end_agent.setEnabled(False)

    def _open_agent_external(self) -> None:
        import subprocess

        from uptray.core.checkers import find_terminal

        if self._agent_combo.count() == 0:
            return
        agent = self._agent_combo.currentText()
        prompt = self._diagnose_prompt()
        command = build_agent_command(agent, prompt)
        term, args = find_terminal(self._cfg)
        if term is None:
            send_message("Error", "No terminal emulator found.")
            return
        try:
            subprocess.Popen([term, *args, *command])
        except OSError as exc:
            send_message("Could not launch agent", str(exc))

    def close_session(self) -> None:
        """End any running agent session (called when the run window closes)."""
        self._end_agent()
