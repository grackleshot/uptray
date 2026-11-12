"""In-app topgrade run window: Simple/Verbose views, logs, and diagnose agents."""

from __future__ import annotations

import functools
import html
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from topgrade_update.core.config import save_run_mode
from topgrade_update.core.logging import get_logger
from topgrade_update.core.notifications import send_message
from topgrade_update.core.topgrade_session import (
    AskpassRequest,
    OutputChunk,
    PromptCleared,
    PromptRequest,
    RetryPrompt,
    SessionFinished,
    StepEvent,
    TopgradeSession,
    build_diagnose_prompt,
    default_runs_dir,
)
from topgrade_update.gui.diagnose_panel import DiagnosePanel
from topgrade_update.gui.dialog import ReviewLogDialog
from topgrade_update.gui.icons import (
    ICON_LG,
    ICON_SM,
    ICON_XL,
    spinner_pixmaps,
    status_pixmap,
)
from topgrade_update.gui.run_simple_page import build_simple_page
from topgrade_update.gui.style import (
    apply_theme,
    colors,
    restore_window_state,
    save_window_state,
    set_danger,
    set_primary,
)
from topgrade_update.gui.terminal_widget import TerminalWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from topgrade_update.core.models import Config

_log = get_logger("run_window")

# A step this quiet for this long gets a "no output for m:ss" hint (alive vs hung).
SILENCE_HINT_S = 120

# status -> (icon kind, human word shown next to the step name)
_STEP_STATUS: dict[str, tuple[str, str]] = {
    "pending": ("pending", "Waiting"),
    "running": ("running", "Running…"),
    "succeeded": ("done", "Done"),
    "failed": ("failed", "Failed"),
    "skipped": ("skipped", "Skipped"),
}


def _format_elapsed(seconds: int) -> str:
    """Render seconds as H:MM:SS or M:SS for the header."""
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class RunWindow(QMainWindow):
    """Non-modal window that hosts a live topgrade (or diagnose) session."""

    finished = Signal(int)
    session_event = Signal(object)

    # Built by run_simple_page.build_simple_page.
    _big_icon: QLabel
    _big_title: QLabel
    _big_subtitle: QLabel
    _activity_label: QLabel
    _hero_actions: QWidget
    _btn_try_again: QPushButton

    def __init__(
        self,
        cfg: Config,
        *,
        extra_args: list[str] | None = None,
        command: list[str] | None = None,
        title: str | None = None,
        on_finished: Callable[[int], None] | None = None,
        on_run_for_real: Callable[[], None] | None = None,
        runs_dir: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        apply_theme(self)
        self._cfg = cfg
        self._runs_dir = runs_dir if runs_dir is not None else default_runs_dir()
        self._extra_args = list(extra_args or [])
        self._command_override = command
        self._on_finished = on_finished
        self._on_run_for_real = on_run_for_real
        self._is_dry_run = "--dry-run" in self._extra_args
        self._last_output = time.monotonic()
        self._session: TopgradeSession | None = None
        self._steps: dict[str, StepEvent] = {}
        self._step_order: list[str] = []
        self._step_items: dict[str, QListWidgetItem] = {}
        self._current_step: str | None = None
        self._failed_step: str | None = None
        self._returncode: int | None = None
        self._log_path: Path | None = None
        self._elapsed = 0
        self._retry_visible = False
        self._activity_line = ""
        self._state_kind: str | None = None
        self._quitting = False
        self._background_notice_sent = False

        self.setWindowTitle(title or "Topgrade Update — Run")
        self.setMinimumSize(840, 560)
        self.session_event.connect(self._on_session_event)

        tokens = colors()
        self._spin_frame = 0
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        # --- Header: live status + mode + actions -----------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        self._state_icon = QLabel()
        self._state_icon.setPixmap(status_pixmap("running", ICON_LG))
        header.addWidget(self._state_icon, 0, Qt.AlignmentFlag.AlignTop)

        state_box = QVBoxLayout()
        state_box.setSpacing(1)
        self._state_label = QLabel("Getting ready…")
        state_font = self._state_label.font()
        state_font.setPointSizeF(state_font.pointSizeF() + 4)
        state_font.setBold(True)
        self._state_label.setFont(state_font)
        self._subtitle_label = QLabel(
            f'<span style="color:{tokens["muted"]}">Starting topgrade…</span>'
        )
        self._subtitle_label.setWordWrap(True)
        state_box.addWidget(self._state_label)
        state_box.addWidget(self._subtitle_label)
        header.addLayout(state_box, 1)

        self._mode_simple = QPushButton("Simple")
        self._mode_simple.setCheckable(True)
        self._mode_verbose = QPushButton("Verbose")
        self._mode_verbose.setCheckable(True)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_group.addButton(self._mode_simple)
        self._mode_group.addButton(self._mode_verbose)
        self._mode_simple.clicked.connect(lambda: self._set_mode("simple"))
        self._mode_verbose.clicked.connect(lambda: self._set_mode("verbose"))
        self._mode_simple.setShortcut(QKeySequence("Ctrl+1"))
        self._mode_verbose.setShortcut(QKeySequence("Ctrl+2"))
        mode_frame = QFrame()
        mode_frame.setStyleSheet(
            f"QFrame {{"
            f" background: {tokens['card']};"
            f" border: 1px solid {tokens['border']};"
            f" border-radius: 8px; }}"
            f"QFrame QPushButton {{ background: transparent; border: none;"
            f" color: {tokens['muted']}; padding: 5px 16px; border-radius: 6px; }}"
            f"QFrame QPushButton:checked {{"
            f" background: {tokens['accent']};"
            f" color: {tokens['accent_text']};"
            f" font-weight: 600; }}"
            f"QFrame QPushButton:hover:!checked {{"
            f" color: {tokens['text']}; }}"
        )
        mode_layout = QHBoxLayout(mode_frame)
        mode_layout.setContentsMargins(3, 3, 3, 3)
        mode_layout.setSpacing(2)
        mode_layout.addWidget(self._mode_simple)
        mode_layout.addWidget(self._mode_verbose)
        mode_frame.setToolTip(
            "Simple (Ctrl+1): friendly progress anyone can follow.\n"
            "Verbose (Ctrl+2): full terminal output with every detail."
        )
        header.addWidget(mode_frame)

        self._btn_review = QPushButton("Review log")
        self._btn_review.clicked.connect(self._review_log)
        self._btn_cancel = QPushButton("Cancel")
        set_danger(self._btn_cancel)
        self._btn_cancel.clicked.connect(self._cancel)
        self._btn_diagnose = QPushButton("Diagnose")
        self._btn_diagnose.clicked.connect(self._toggle_diagnose)
        self._btn_run_real = QPushButton("Run for real")
        self._btn_run_real.setToolTip("The preview looked good: run the actual update")
        self._btn_run_real.clicked.connect(self._run_for_real)
        self._btn_run_real.hide()
        header.addWidget(self._btn_review)
        header.addWidget(self._btn_diagnose)
        header.addWidget(self._btn_run_real)
        header.addWidget(self._btn_cancel)
        layout.addLayout(header)

        # Progress bar directly under the header.
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # busy pulse until steps are known
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        layout.addWidget(self._progress)

        # --- Body: step checklist + Simple/Verbose stack -----------------
        self._body = body = QSplitter(Qt.Orientation.Horizontal)
        self._step_list = QListWidget()
        self._step_list.setMinimumWidth(230)
        self._step_list.setIconSize(QSize(18, 18))
        body.addWidget(self._step_list)

        self._stack = QStackedWidget()

        simple_page = build_simple_page(self, tokens)
        self._stack.addWidget(simple_page)

        self._term = TerminalWidget()
        self._term.input_ready.connect(self._pty_write)
        self._term.set_resize_handler(self._on_term_resize)
        self._stack.addWidget(self._term)
        body.addWidget(self._stack)
        body.setStretchFactor(1, 1)
        body.setSizes([260, 580])
        layout.addWidget(body, 1)

        # --- Retry prompt strip ------------------------------------------
        self._retry_bar = QFrame()
        self._retry_bar.setStyleSheet(
            f"QFrame {{ background: {tokens['warning_bg']};"
            f" border: 1px solid {tokens['warning']}; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }"
            "QPushButton { background: transparent; }"
        )
        retry_layout = QHBoxLayout(self._retry_bar)
        retry_layout.setContentsMargins(12, 8, 12, 8)
        retry_layout.setSpacing(8)
        retry_icon = QLabel()
        retry_icon.setPixmap(status_pixmap("warning", ICON_SM))
        retry_layout.addWidget(retry_icon)
        retry_layout.addWidget(QLabel("<b>Topgrade asks:</b> retry the failed step?"))
        for label, key in (
            ("Yes, retry", "y"),
            ("No, skip", "n"),
            ("Open terminal", "s"),
            ("Quit", "q"),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(lambda _checked=False, k=key: self._answer_retry(k))
            retry_layout.addWidget(btn)
        retry_layout.addStretch()
        self._retry_bar.hide()
        layout.addWidget(self._retry_bar)

        # --- Interactive prompt strip --------------------------------------
        # Surfaced whenever the running command asks a [Y/n]-style question.
        self._prompt_bar = QFrame()
        self._prompt_bar.setStyleSheet(
            f"QFrame {{ background: {tokens['warning_bg']};"
            f" border: 1px solid {tokens['warning']}; border-radius: 8px; }}"
            "QLabel { background: transparent; border: none; }"
            "QPushButton { background: transparent; }"
        )
        prompt_layout = QHBoxLayout(self._prompt_bar)
        prompt_layout.setContentsMargins(12, 8, 12, 8)
        prompt_layout.setSpacing(8)
        prompt_icon = QLabel()
        prompt_icon.setPixmap(status_pixmap("warning", ICON_SM))
        prompt_layout.addWidget(prompt_icon)
        self._prompt_label = QLabel("")
        self._prompt_label.setWordWrap(True)
        prompt_layout.addWidget(self._prompt_label, 1)
        self._btn_prompt_yes = QPushButton("Yes")
        self._btn_prompt_no = QPushButton("No")
        self._btn_prompt_term = QPushButton("Answer in terminal")
        self._btn_prompt_yes.clicked.connect(lambda: self._answer_prompt("y"))
        self._btn_prompt_no.clicked.connect(lambda: self._answer_prompt("n"))
        self._btn_prompt_term.clicked.connect(
            functools.partial(self._answer_prompt, None)
        )
        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText("Type your answer…")
        self._prompt_input.setMaximumWidth(220)
        self._prompt_input.returnPressed.connect(self._send_prompt_text)
        self._btn_prompt_send = QPushButton("Send")
        self._btn_prompt_send.clicked.connect(self._send_prompt_text)
        prompt_layout.addWidget(self._btn_prompt_yes)
        prompt_layout.addWidget(self._btn_prompt_no)
        prompt_layout.addWidget(self._prompt_input)
        prompt_layout.addWidget(self._btn_prompt_send)
        prompt_layout.addWidget(self._btn_prompt_term)
        self._prompt_bar.hide()
        layout.addWidget(self._prompt_bar)

        # --- Diagnose drawer ---------------------------------------------
        self._diagnose = DiagnosePanel(cfg, self._runs_dir, self._diagnose_prompt)

        # Resizable vertical split: the diagnose drawer must be drag-resizable,
        # not squeezed into whatever space the layout has left over.
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(body)
        self._splitter.addWidget(self._diagnose)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, True)
        self._splitter.setSizes([1000, 0])
        layout.addWidget(self._splitter, 1)
        restore_window_state(self, "run_window", self._body)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._advance_spinner)
        self._set_mode(cfg.run_mode if cfg.run_mode in {"simple", "verbose"} else "simple")
        QTimer.singleShot(0, self._start)

    @property
    def is_active(self) -> bool:
        """True while the topgrade session is still running."""
        return self._session is not None and self._session.running

    def _set_mode(self, mode: str) -> None:
        simple = mode != "verbose"
        self._mode_simple.setChecked(simple)
        self._mode_verbose.setChecked(not simple)
        self._stack.setCurrentIndex(0 if simple else 1)
        if self._cfg.run_mode != mode:
            self._cfg.run_mode = mode
            try:
                # Reload-from-disk so we do not clobber newer tray settings.
                self._cfg = save_run_mode(mode)
            except (OSError, ValueError) as exc:
                _log.warning("Could not save run_mode: %s", exc)
        if not simple:
            self._term.focus_terminal()

    def _start(self) -> None:
        if self._command_override is not None:
            command = list(self._command_override)
        else:
            topgrade = shutil.which("topgrade")
            if topgrade is None:
                QMessageBox.warning(
                    self, "Topgrade not found", "Install topgrade before trying to run it."
                )
                self._set_state(
                    "failed", "Topgrade is missing", "Install topgrade, then try again."
                )
                self._hero_actions.hide()
                self._btn_cancel.setEnabled(False)
                return
            command = [topgrade, *self._extra_args]

        self._session = TopgradeSession(
            command,
            runs_dir=self._runs_dir,
            on_event=self.session_event.emit,
        )
        self._log_path = self._session.log_path
        self._set_state("running", "Updating your computer…", "Starting topgrade…")
        self._timer.start(1000)
        self._spin_timer.start(120)
        try:
            self._session.start()
        except OSError as exc:
            self._spin_timer.stop()
            self._set_state("failed", "Could not start", str(exc))
            self._btn_cancel.setEnabled(False)

    def _advance_spinner(self) -> None:
        """Rotate the activity spinner on the header and the running step."""
        running = self._session is not None and self._session.running
        if not running:
            self._spin_timer.stop()
            return
        self._spin_frame = (self._spin_frame + 1) % len(spinner_pixmaps())
        frames = spinner_pixmaps()
        self._state_icon.setPixmap(frames[self._spin_frame])
        for name in self._step_order:
            if self._steps[name].status == "running":
                item = self._step_items.get(name)
                if item is not None:
                    item.setIcon(spinner_pixmaps(ICON_SM)[self._spin_frame])

    def _try_again(self) -> None:
        """Reset the run state and start a fresh topgrade session."""
        self._hero_actions.hide()
        self._prompt_bar.hide()
        self._state_kind = None
        self._progress.setRange(0, 0)
        self._progress.show()
        self._btn_diagnose.setDefault(False)
        self._btn_diagnose.setProperty("class", None)
        self._btn_diagnose.style().unpolish(self._btn_diagnose)
        self._btn_diagnose.style().polish(self._btn_diagnose)
        self._btn_cancel.setText("Cancel")
        set_danger(self._btn_cancel)
        self._btn_cancel.setEnabled(True)
        self._returncode = None
        self._failed_step = None
        self._current_step = None
        self._steps.clear()
        self._step_order.clear()
        self._step_items.clear()
        self._step_list.clear()
        self._elapsed = 0
        self._last_output = time.monotonic()
        self._activity_line = ""
        self._activity_label.setText("")
        self._progress.setRange(0, 0)
        self._spin_frame = 0
        self._start()

    def _tick(self) -> None:
        self._elapsed += 1
        self._refresh_subtitle()

    # ------------------------------------------------------------------
    # Header / Simple-pane state

    def _set_state(self, kind: str, title: str, subtitle_html: str) -> None:
        """Update the header and Simple-pane hero for a run state.

        Icons are only swapped when the kind *changes*: the running state
        redraws every second and must not fight the animated spinner.
        """
        tokens = colors()
        if kind != self._state_kind:
            self._state_kind = kind
            self._state_icon.setPixmap(status_pixmap(kind, ICON_LG))
            self._big_icon.setPixmap(status_pixmap(kind, ICON_XL))
        self._state_label.setText(title)
        self._big_title.setText(title)
        self._subtitle_label.setText(
            f'<span style="color:{tokens["muted"]}">{subtitle_html}</span>'
        )
        self._big_subtitle.setText(
            f'<span style="color:{tokens["muted"]}">{subtitle_html}</span>'
        )

    def _refresh_subtitle(self) -> None:
        """Rebuild the live subtitle: step ordinal, current step, elapsed.

        topgrade discovers steps lazily, so a "Step N of M" total would keep
        moving; report the ordinal alone.
        """
        if self._returncode is not None:
            return
        parts: list[str] = []
        if self._current_step is not None and self._current_step in self._step_order:
            ordinal = self._step_order.index(self._current_step) + 1
            parts.append(f"Step {ordinal} · {self._current_step}")
        elif self._step_order:
            parts.append(f"{len(self._step_order)} steps done")
        parts.append(_format_elapsed(self._elapsed))
        silent = int(time.monotonic() - self._last_output)
        if self._current_step is not None and silent >= SILENCE_HINT_S:
            parts.append(f"no output for {_format_elapsed(silent)}")
        self._set_state("running", "Updating your computer…", " · ".join(parts))

    def _refresh_progress(self) -> None:
        """The bar stays a busy pulse while the run is underway (totals unknown)."""
        if self._returncode is not None:
            return
        self._progress.setRange(0, 0)

    # ------------------------------------------------------------------
    # Session events

    def _on_session_event(self, event: object) -> None:
        if isinstance(event, OutputChunk):
            self._term.write(event.text)
            return
        if isinstance(event, StepEvent):
            self._apply_step(event)
            return
        if isinstance(event, RetryPrompt):
            self._retry_bar.show()
            self._retry_visible = True
            self._btn_diagnose.setDefault(False)
            return
        if isinstance(event, AskpassRequest):
            self._handle_askpass(event)
            return
        if isinstance(event, PromptRequest):
            self._show_prompt(event.question, buttons="text" if event.free_text else "yesno")
            self._notify_if_unseen("Topgrade needs your answer", event.question)
            return
        if isinstance(event, PromptCleared):
            self._prompt_bar.hide()
            return
        if isinstance(event, SessionFinished):
            self._finish(event)

    def _apply_step(self, event: StepEvent) -> None:
        # Parsed lines, not raw chunks: a spinner redrawing in place is not progress.
        self._last_output = time.monotonic()
        if event.name not in self._steps:
            self._step_order.append(event.name)
        self._steps[event.name] = event
        if event.status == "running":
            self._current_step = event.name
        if event.status == "failed":
            self._failed_step = event.name
            self._btn_diagnose.setDefault(True)
        self._refresh_steps()
        if event.latest_line:
            self._activity_line = event.latest_line
            shown = self._activity_line if len(self._activity_line) <= 120 else (
                self._activity_line[:117] + "…"
            )
            self._activity_label.setText(shown)
        if event.status in {"succeeded", "failed", "skipped"} and (
            self._current_step == event.name
        ):
            self._current_step = None
        self._refresh_progress()
        self._refresh_subtitle()

    def _refresh_steps(self) -> None:
        for name in self._step_order:
            step = self._steps[name]
            icon_kind, word = _STEP_STATUS.get(step.status, ("pending", "…"))
            item = self._step_items.get(name)
            if item is None:
                item = QListWidgetItem(f"{name} — {word}")
                self._step_items[name] = item
                self._step_list.addItem(item)
                self._step_list.scrollToBottom()
            else:
                item.setText(f"{name} — {word}")
            item.setIcon(status_pixmap(icon_kind, ICON_SM))
            tooltip = f"{name}: {word}"
            if step.latest_line:
                tooltip = f"{tooltip}\n{step.latest_line}"
            item.setToolTip(tooltip)

    def _show_prompt(self, text: str, *, buttons: str = "yesno") -> None:
        """Show the prompt strip; buttons: "yesno", "text" (typed answer) or "none"."""
        self._prompt_label.setText(text)
        yesno = buttons == "yesno"
        typed = buttons == "text"
        self._btn_prompt_yes.setVisible(yesno)
        self._btn_prompt_no.setVisible(yesno)
        self._prompt_input.setVisible(typed)
        self._btn_prompt_send.setVisible(typed)
        self._btn_prompt_term.setVisible(buttons != "none")
        self._prompt_bar.show()
        if typed:
            self._prompt_input.clear()
            self._prompt_input.setFocus()

    def _send_prompt_text(self) -> None:
        # An empty answer is meaningful: Enter accepts the prompt's default.
        text = self._prompt_input.text()
        self._prompt_input.clear()
        self._answer_prompt(text)

    def _notify_if_unseen(self, summary: str, body: str) -> None:
        """Desktop-notify only when the user can't see this window right now."""
        if not self._cfg.notifications.enabled:
            return
        if self.isVisible() and self.isActiveWindow():
            return
        send_message(summary, body)

    def _handle_askpass(self, event: AskpassRequest) -> None:
        step = self._current_step
        notice = f"Password required for “{step}”" if step else "Password required"
        self._notify_if_unseen(notice, event.prompt)
        if self.isHidden():
            self.showNormal()
        self._show_prompt(notice, buttons="none")
        password, ok = QInputDialog.getText(
            self,
            "Authentication required",
            event.prompt,
            QLineEdit.EchoMode.Password,
        )
        self._prompt_bar.hide()
        if self._session is not None:
            self._session.reply_askpass(event.request_id, password if ok else None)

    def _answer_retry(self, key: str) -> None:
        self._retry_bar.hide()
        self._retry_visible = False
        if key == "s":
            self._set_mode("verbose")
        self._pty_write(f"{key}\n")

    def _pty_write(self, data: str) -> None:
        if self._session is not None:
            self._session.write(data)

    def _on_term_resize(self, rows: int, cols: int) -> None:
        if self._session is not None:
            self._session.resize(rows, cols)

    def _cancel(self) -> None:
        if self._session is not None and self._session.running:
            answer = QMessageBox.question(
                self,
                "Stop the update?",
                "Stopping topgrade part-way can leave packages half-installed.\n\n"
                "Stop it anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes or not self.is_active:
                return
            self._state_label.setText("Cancelling…")
            self._session.cancel()
        else:
            self.close()

    def _finish(self, event: SessionFinished) -> None:
        self._timer.stop()
        self._spin_timer.stop()
        self._returncode = event.returncode
        self._log_path = event.log_path
        self._failed_step = event.failed_step or self._failed_step
        self._retry_bar.hide()
        self._prompt_bar.hide()
        self._sweep_open_steps()
        self._btn_cancel.setText("Close")
        # Cancel was marked destructive; as a plain Close it loses the role.
        self._btn_cancel.setProperty("class", None)
        self._btn_cancel.style().unpolish(self._btn_cancel)
        self._btn_cancel.style().polish(self._btn_cancel)
        elapsed = _format_elapsed(self._elapsed)
        if event.returncode == 0:
            self._progress.setRange(0, 1)
            self._progress.setValue(1)
            self._hero_actions.hide()
            if self._is_dry_run:
                summary = f"Nothing was changed · finished in {elapsed}"
                self._set_state("done", "Preview complete", summary)
            else:
                summary = f"Up to date · finished in {elapsed}"
                self._set_state("done", "All done!", summary)
            if self._is_dry_run and self._on_run_for_real is not None:
                self._btn_run_real.show()
                self._btn_run_real.setDefault(True)
                set_primary(self._btn_run_real)
            else:
                self._btn_cancel.setDefault(True)
                set_primary(self._btn_cancel)
            self._notify_if_unseen("Update finished", summary)
        else:
            # A determinate fraction would imply a known total; drop the bar.
            self._progress.hide()
            failed = self._failed_step or self._current_step
            detail = f"Exit code {event.returncode} · {elapsed}"
            if failed:
                detail = f"“{failed}” failed · {detail}"
            reason = self._failure_reason()
            if reason:
                detail = f"{detail}\n{reason}"
            self._set_state(
                "failed", "Something went wrong", html.escape(detail).replace("\n", "<br>")
            )
            self._hero_actions.show()
            # Keyboard default lands on Diagnose; the hero's "Try again" stays
            # the single visually-primary action.
            self._btn_diagnose.setDefault(True)
            self._notify_if_unseen("Update failed", f"{detail}\nDetails in Update History.")
        self.finished.emit(event.returncode)
        if self._on_finished is not None:
            self._on_finished(event.returncode)

    def _failure_reason(self, *, full: bool = False) -> str | None:
        """topgrade's reason for the failed step; first line (≤80 chars) unless full."""
        step = self._steps.get(self._failed_step or "")
        reason = step.reason if step is not None else None
        if not reason or full:
            return reason
        line = reason.splitlines()[0]
        return line if len(line) <= 80 else line[:79] + "…"

    def _diagnose_prompt(self) -> str:
        return build_diagnose_prompt(
            returncode=self._returncode,
            failed_step=self._failed_step or self._current_step,
            log_path=self._log_path or Path("."),
            reason=self._failure_reason(full=True),
        )

    def _run_for_real(self) -> None:
        if self._on_run_for_real is not None:
            self._on_run_for_real()

    def _sweep_open_steps(self) -> None:
        """Mark steps left pending/running at exit so nothing shows 'Running…'."""
        for name in self._step_order:
            if self._steps[name].status in {"pending", "running"}:
                item = self._step_items.get(name)
                if item is not None:
                    item.setText(f"{name} — Ended")
                    item.setIcon(status_pixmap("skipped", ICON_SM))

    def _review_log(self) -> None:
        ReviewLogDialog(current=self._log_path, runs_dir=self._runs_dir, parent=self).exec()

    def _toggle_diagnose(self) -> None:
        if self._diagnose.isVisible():
            save_window_state(None, "run_window/diagnose", self._splitter)
            self._diagnose.hide()
            self._splitter.setSizes([1000, 0])
            return
        self._diagnose.show()
        if restore_window_state(None, "run_window/diagnose", self._splitter):
            return
        total = max(1, sum(self._splitter.sizes()) or self._splitter.height())
        self._splitter.setSizes([int(total * 0.62), int(total * 0.38)])

    def _answer_prompt(self, answer: str | None) -> None:
        """Reply to a detected prompt, or hand control to the terminal."""
        if answer is None:
            self._prompt_bar.hide()
            self._set_mode("verbose")
            return
        self._pty_write(f"{answer}\n")
        self._prompt_bar.hide()

    def shutdown(self) -> None:
        """Stop any running session and close for real (used on app quit)."""
        self._quitting = True
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Not a QShortcut: the terminal (vim, pacdiff) must still receive Esc.
        if event.key() == Qt.Key.Key_Escape and not self.is_active:
            self.close()
            return
        super().keyPressEvent(event)

    def _save_layout(self) -> None:
        save_window_state(self, "run_window", self._body)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_layout()
        if self.is_active and not self._quitting:
            # Closing must never kill an upgrade mid-transaction: keep it running.
            event.ignore()
            self.hide()
            if not self._background_notice_sent:
                self._background_notice_sent = True
                self._notify_if_unseen(
                    "Still updating in the background",
                    "Choose Run Topgrade in the tray to bring the window back.",
                )
            return
        if self._session is not None and self._session.running:
            self._session.cancel()
            self._session.wait(timeout=2)
            self._session.close()
        self._diagnose.close_session()
        super().closeEvent(event)

