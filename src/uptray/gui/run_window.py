"""In-app Topgrade run monitor with Simple and Verbose views."""

from __future__ import annotations

import re
import shutil
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent, QKeySequence, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from uptray.core.config import save_run_mode
from uptray.core.logging import get_logger
from uptray.core.notifications import send_message
from uptray.core.run_history import prune_runs
from uptray.core.run_metadata import describe_run_scope
from uptray.core.topgrade_session import (
    AskpassExpired,
    AskpassRequest,
    OutputChunk,
    PromptCleared,
    PromptRequest,
    RetryPrompt,
    SessionFinished,
    StepEvent,
    TopgradeSession,
    TranscriptWarning,
    build_diagnose_prompt,
    default_runs_dir,
)
from uptray.gui.diagnose_panel import DiagnosePanel
from uptray.gui.dialog import ReviewLogDialog
from uptray.gui.icons import ICON_LG, ICON_MD, ICON_SM, IconCache, spinner_pixmaps, status_pixmap
from uptray.gui.run_prompt_bar import build_prompt_bar
from uptray.gui.run_simple_page import build_simple_page
from uptray.gui.style import (
    apply_theme,
    colors,
    restore_window_state,
    save_window_state,
    set_danger,
    set_primary,
    tag_card,
)
from uptray.gui.task_progress import TaskProgress
from uptray.gui.terminal_widget import TerminalWidget

if TYPE_CHECKING:
    from collections.abc import Callable

    from uptray.core.models import Config

_log = get_logger("run_window")

SILENCE_HINT_S = 120
_COMPACT_WIDTH = 750
_ACTIVITY_LINES = 6
_ACTIVITY_CHARS = 1000
_PERCENTAGE = re.compile(r"(?<![\d.])(100|[1-9]?\d)(?:\.\d+)?\s*%")
_STEP_SEPARATOR = re.compile(r"^(?:─{2,}|―{2,}|-{3,})")

_STEP_STATUS: dict[str, tuple[str, str]] = {
    "pending": ("pending", "Waiting"),
    "running": ("running", "Running…"),
    "succeeded": ("done", "Done"),
    "failed": ("failed", "Failed"),
    "skipped": ("skipped", "Skipped"),
    "ended": ("skipped", "Ended"),
}


def _format_elapsed(seconds: int) -> str:
    minutes, secs = divmod(max(0, seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _bounded(text: str, limit: int) -> str:
    """Keep the end of a very long line, where the result often appears."""
    if len(text) <= limit:
        return text
    half = (limit - 1) // 2
    return f"{text[:half]}…{text[-half:]}"


class RunWindow(QMainWindow):
    """Non-modal window that hosts a live Topgrade session."""

    finished = Signal(int)
    session_event = Signal(object)
    monitor_status_changed = Signal(str)
    closed = Signal()  # really closed, not hidden while a run continues

    # Built by run_simple_page and run_prompt_bar.
    _activity: QPlainTextEdit
    _prompt_bar: QFrame
    _prompt_label: QLabel
    _prompt_detail: QLabel
    _btn_prompt_yes: QPushButton
    _btn_prompt_no: QPushButton
    _btn_prompt_term: QPushButton
    _prompt_input: QLineEdit
    _btn_prompt_send: QPushButton
    _btn_prompt_cancel: QPushButton
    _btn_retry: QPushButton
    _btn_skip: QPushButton
    _btn_retry_more: QPushButton

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
        self._scope = describe_run_scope(self._extra_args)
        self._is_dry_run = self._scope.startswith("Preview")
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
        self._started_at: float | None = None
        self._activity_lines: deque[tuple[str, str, str]] = deque(maxlen=_ACTIVITY_LINES)
        self._pty_prompt: PromptRequest | RetryPrompt | None = None
        self._announced_pty_prompt = False
        self._askpass_requests: deque[AskpassRequest] = deque()
        self._prompt_in_terminal = False
        self._run_warnings: list[str] = []
        self._transcript_incomplete = False
        self._state_kind: str | None = None
        self._monitor_status = "Preparing preview" if self._is_dry_run else "Preparing update"
        self._quitting = False
        self._cancelling = False
        self._background_notice_sent = False
        self._task_progress = TaskProgress()
        self._terminal_size = (24, 80)
        self._steps_requested: bool | None = None
        self._spin_frame = 0

        self.setWindowTitle(title or "Uptray — Run")
        self.setMinimumSize(640, 480)
        self.resize(1000, 700)
        self.session_event.connect(self._on_session_event)

        tokens = colors()
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        layout.addLayout(self._build_toolbar(tokens))
        layout.addLayout(self._build_status(tokens))

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._progress.setToolTip(
            "Progress of the current operation when reported. Overall run total is unknown."
        )
        self._progress.setFixedHeight(8)
        layout.addWidget(self._progress)

        self._warning_label = QLabel()
        self._warning_label.setTextFormat(Qt.TextFormat.PlainText)
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet(
            f"background: {tokens['warning_bg']}; color: {tokens['text']};"
            f"border-left: 3px solid {tokens['warning']}; border-radius: 4px; padding: 6px 8px;"
        )
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        body = self._build_body(tokens)
        self._diagnose = DiagnosePanel(cfg, self._runs_dir, self._diagnose_prompt)
        self._splitter = QSplitter(Qt.Orientation.Vertical)
        self._splitter.addWidget(body)
        self._splitter.addWidget(self._diagnose)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, True)
        self._splitter.setSizes([1000, 0])
        layout.addWidget(self._splitter, 1)
        layout.addLayout(self._build_footer(tokens))
        restore_window_state(self, "run_window", self._body)
        self._refresh_step_list_visibility()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._advance_spinner)
        self._set_mode(cfg.run_mode if cfg.run_mode in {"simple", "verbose"} else "simple")
        QTimer.singleShot(0, self._start)

    def _build_toolbar(self, tokens: dict[str, str]) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(IconCache(self._cfg.tray.icon_style).application().pixmap(ICON_MD))
        toolbar.addWidget(icon)
        brand = QLabel("Uptray")
        brand_font = brand.font()
        brand_font.setPointSizeF(brand_font.pointSizeF() + 2)
        brand_font.setBold(True)
        brand.setFont(brand_font)
        toolbar.addWidget(brand)
        toolbar.addStretch()

        self._btn_steps = QPushButton("Steps")
        self._btn_steps.setCheckable(True)
        self._btn_steps.setToolTip("Show or hide the steps list")
        self._btn_steps.clicked.connect(self._show_steps)
        toolbar.addWidget(self._btn_steps)
        self._btn_review = QPushButton("Review log")
        self._btn_review.clicked.connect(self._review_log)
        toolbar.addWidget(self._btn_review)
        self._btn_diagnose = QPushButton("Diagnose")
        self._btn_diagnose.clicked.connect(self._toggle_diagnose)
        toolbar.addWidget(self._btn_diagnose)

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
        mode_frame.setObjectName("runModes")
        mode_frame.setStyleSheet(
            f"QFrame#runModes {{ background: {tokens['card2']};"
            f" border: 1px solid {tokens['border']}; border-radius: 8px; }}"
            "QFrame#runModes QPushButton { background: transparent;"
            " border: 1px solid transparent; padding: 4px 11px; }"
            f"QFrame#runModes QPushButton:checked {{ background: {tokens['card']};"
            f" border-color: {tokens['border']}; color: {tokens['text']}; }}"
            f"QFrame#runModes QPushButton:focus {{ border-color: {tokens['accent']}; }}"
        )
        modes = QHBoxLayout(mode_frame)
        modes.setContentsMargins(3, 3, 3, 3)
        modes.setSpacing(2)
        modes.addWidget(self._mode_simple)
        modes.addWidget(self._mode_verbose)
        mode_frame.setToolTip("Simple activity view (Ctrl+1) or interactive terminal (Ctrl+2)")
        toolbar.addWidget(mode_frame)
        return toolbar

    def _build_status(self, tokens: dict[str, str]) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(10)
        self._state_icon = QLabel()
        self._state_icon.setFixedSize(ICON_LG, ICON_LG)
        self._state_icon.setPixmap(status_pixmap("pending", ICON_LG))
        header.addWidget(self._state_icon, 0, Qt.AlignmentFlag.AlignVCenter)

        state_box = QVBoxLayout()
        state_box.setSpacing(2)
        self._state_label = QLabel(self._monitor_status)
        self._state_label.setTextFormat(Qt.TextFormat.PlainText)
        self._state_label.setWordWrap(True)
        state_font = self._state_label.font()
        state_font.setPointSizeF(state_font.pointSizeF() + 8)
        state_font.setBold(True)
        self._state_label.setFont(state_font)
        self._subtitle_label = QLabel("Starting Topgrade…")
        self._subtitle_label.setTextFormat(Qt.TextFormat.PlainText)
        self._subtitle_label.setWordWrap(True)
        self._subtitle_label.setStyleSheet(f"color: {tokens['muted']};")
        state_box.addWidget(self._state_label)
        state_box.addWidget(self._subtitle_label)
        header.addLayout(state_box, 1)

        elapsed = QVBoxLayout()
        elapsed.setSpacing(1)
        elapsed_title = QLabel("Elapsed time")
        elapsed_title.setStyleSheet(f"color: {tokens['muted']};")
        elapsed_title.setAlignment(Qt.AlignmentFlag.AlignRight)
        elapsed.addWidget(elapsed_title)
        self._elapsed_label = QLabel("0:00")
        self._elapsed_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._elapsed_label.setAccessibleName("Elapsed time")
        elapsed_font = self._elapsed_label.font()
        elapsed_font.setPointSizeF(elapsed_font.pointSizeF() + 3)
        elapsed_font.setBold(True)
        self._elapsed_label.setFont(elapsed_font)
        elapsed.addWidget(self._elapsed_label)
        header.addLayout(elapsed)
        return header

    def _build_body(self, tokens: dict[str, str]) -> QSplitter:
        self._body = body = QSplitter(Qt.Orientation.Horizontal)

        self._steps_panel = QFrame()
        tag_card(self._steps_panel)
        self._steps_panel.setMinimumWidth(148)
        steps_layout = QVBoxLayout(self._steps_panel)
        steps_layout.setContentsMargins(9, 10, 9, 8)
        steps_layout.setSpacing(5)
        heading = QLabel("Steps")
        font = heading.font()
        font.setBold(True)
        heading.setFont(font)
        steps_layout.addWidget(heading)
        self._step_list = QListWidget()
        self._step_list.setAccessibleName("Topgrade steps")
        self._step_list.setIconSize(QSize(ICON_SM, ICON_SM))
        self._step_list.setWordWrap(True)
        self._step_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._step_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; padding: 0; }"
            "QListWidget::item { padding: 5px 3px; border-radius: 4px; }"
        )
        steps_layout.addWidget(self._step_list)
        body.addWidget(self._steps_panel)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(build_prompt_bar(self, tokens))
        self._stack = QStackedWidget()
        self._stack.addWidget(build_simple_page(self, tokens))
        self._term = TerminalWidget()
        self._term.input_ready.connect(self._terminal_input)
        self._term.set_resize_handler(self._on_term_resize)
        self._stack.addWidget(self._term)
        right_layout.addWidget(self._stack, 1)
        body.addWidget(right)
        body.setCollapsible(0, False)
        body.setCollapsible(1, False)
        body.setStretchFactor(1, 1)
        body.setSizes([200, 780])
        return body

    def _build_footer(self, tokens: dict[str, str]) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setSpacing(8)
        scope = QLabel(f"Scope · {_bounded(self._scope, 120)}")
        scope.setToolTip(self._scope)
        scope.setTextFormat(Qt.TextFormat.PlainText)
        scope.setWordWrap(True)
        scope.setStyleSheet(f"color: {tokens['muted']};")
        scope.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        footer.addWidget(scope, 1)
        self._btn_try_again = QPushButton("Try again")
        set_primary(self._btn_try_again)
        self._btn_try_again.clicked.connect(self._try_again)
        self._btn_try_again.hide()
        footer.addWidget(self._btn_try_again)
        self._btn_run_real = QPushButton("Run for real")
        self._btn_run_real.setToolTip("Run the update with this scope")
        self._btn_run_real.clicked.connect(self._run_for_real)
        self._btn_run_real.hide()
        set_primary(self._btn_run_real)
        footer.addWidget(self._btn_run_real)
        self._btn_hide = QPushButton("Hide to tray")
        self._btn_hide.clicked.connect(self.close)
        footer.addWidget(self._btn_hide)
        self._btn_cancel = QPushButton(self._stop_text)
        set_danger(self._btn_cancel)
        self._btn_cancel.clicked.connect(self._cancel)
        footer.addWidget(self._btn_cancel)
        return footer

    @property
    def _stop_text(self) -> str:
        return "Stop preview" if self._is_dry_run else "Stop update"

    @property
    def is_active(self) -> bool:
        """True from launch scheduling until the monitor receives the outcome."""
        return self._returncode is None and not self._quitting

    @property
    def is_dry_run(self) -> bool:
        """True when this window is showing a preview rather than an update."""
        return self._is_dry_run

    @property
    def monitor_status(self) -> str:
        """Compact description for the tray while the monitor is running."""
        return self._monitor_status

    @property
    def _decision(self) -> AskpassRequest | PromptRequest | RetryPrompt | None:
        return self._askpass_requests[0] if self._askpass_requests else self._pty_prompt

    def _show_steps(self, visible: bool) -> None:
        self._steps_requested = visible
        self._refresh_step_list_visibility()

    def _refresh_step_list_visibility(self) -> None:
        visible = self._steps_requested
        if visible is None:
            visible = self.width() >= _COMPACT_WIDTH
        self._steps_panel.setVisible(visible)
        self._btn_steps.setChecked(visible)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "_steps_panel"):
            self._refresh_step_list_visibility()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self.focus_pending_input()

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
        if simple:
            if self._prompt_in_terminal:
                self._prompt_in_terminal = False
                self._render_decision()
            self.focus_pending_input()
        else:
            self._term.focus_terminal()

    def _start(self) -> None:
        if not self.is_active:
            return
        if self._command_override is not None:
            command = list(self._command_override)
        else:
            topgrade = shutil.which("topgrade")
            if topgrade is None:
                self._startup_failed("Topgrade was not found. Install it, then try again.", 127)
                return
            command = [topgrade, *self._extra_args]

        self._started_at = self._last_output = time.monotonic()
        self._refresh_subtitle()
        try:
            self._session = TopgradeSession(
                command,
                runs_dir=self._runs_dir,
                extra_args=self._extra_args,
                on_event=self.session_event.emit,
            )
            self._log_path = self._session.log_path
            self._session.resize(*self._terminal_size)
            self._session.start()
        except (OSError, ValueError) as exc:
            if self._session is not None:
                self._session.close()
                self._session = None
            self._startup_failed(str(exc), 126)
            return
        self._timer.start(1000)
        self._spin_timer.start(120)

    def _startup_failed(self, message: str, code: int) -> None:
        self._returncode = code
        self._progress.hide()
        self._set_stopped_controls()
        self._btn_try_again.show()
        self._set_state("failed", "Could not start", _bounded(message, 240))
        self._subtitle_label.setToolTip(message)
        self._notify_if_unseen("Could not start Topgrade", f"{message}\n{self._scope}")
        self._emit_finished(code)

    def _advance_spinner(self) -> None:
        if not self.is_active:
            self._spin_timer.stop()
            return
        if self._state_kind != "running":
            return
        frames = spinner_pixmaps(ICON_LG)
        self._spin_frame = (self._spin_frame + 1) % len(frames)
        self._state_icon.setPixmap(frames[self._spin_frame])
        item = self._step_items.get(self._current_step or "")
        if item is not None:
            item.setIcon(spinner_pixmaps(ICON_SM)[self._spin_frame])

    def _try_again(self) -> None:
        """Reset the monitor before starting a fresh run with the same scope."""
        if self.is_active:
            return
        self._btn_try_again.hide()
        self._btn_run_real.hide()
        self._run_warnings.clear()
        self._transcript_incomplete = False
        self._warning_label.hide()
        self._subtitle_label.setToolTip("")
        self._btn_diagnose.setDefault(False)
        self._btn_cancel.setDefault(False)
        self._btn_cancel.setText(self._stop_text)
        set_danger(self._btn_cancel)
        self._btn_cancel.setEnabled(True)
        self._btn_hide.show()
        self._returncode = None
        self._session = None
        self._log_path = None
        self._failed_step = None
        self._current_step = None
        self._steps.clear()
        self._step_order.clear()
        self._step_items.clear()
        self._step_list.clear()
        self._activity_lines.clear()
        self._activity.clear()
        self._term.clear()
        self._elapsed = 0
        self._started_at = None
        self._update_elapsed()
        self._cancelling = False
        self._background_notice_sent = False
        self._progress.setRange(0, 0)
        self._progress.show()
        self._spin_frame = 0
        self._start()

    def _tick(self) -> None:
        self._update_elapsed()
        if self._decision is None:
            self._refresh_subtitle()

    def _update_elapsed(self) -> None:
        if self._started_at is not None:
            self._elapsed = int(time.monotonic() - self._started_at)
        self._elapsed_label.setText(_format_elapsed(self._elapsed))

    def _set_state(self, kind: str, title: str, detail: str, *, status: str | None = None) -> None:
        if kind != self._state_kind:
            self._state_kind = kind
            self._state_icon.setPixmap(status_pixmap(kind, ICON_LG))
        if title != self._state_label.text():
            self._state_label.setText(title)
        if detail != self._subtitle_label.text():
            self._subtitle_label.setText(detail)
            self._subtitle_label.setVisible(bool(detail))
        compact = _bounded(status or title, 90)
        if compact != self._monitor_status:
            self._monitor_status = compact
            self.monitor_status_changed.emit(compact)

    def _refresh_subtitle(self) -> None:
        if not self.is_active or self._cancelling or self._decision is not None:
            return
        title = "Previewing changes" if self._is_dry_run else "Updating your computer…"
        status = "Previewing changes" if self._is_dry_run else "Updating"
        detail = "Starting Topgrade…" if not self._step_order else "Running Topgrade…"
        if self._current_step is not None:
            step = _bounded(self._current_step, 100)
            ordinal = self._step_order.index(self._current_step) + 1
            status = f"{status} · {step}"
            if self._is_dry_run:
                detail = f"Step {ordinal} · {step}"
            else:
                title, detail = step, f"Step {ordinal} · In progress"
            silent = int(time.monotonic() - self._last_output)
            if silent >= SILENCE_HINT_S:
                detail += f" · no output for {_format_elapsed(silent)}"
        self._set_state("running", title, detail, status=status)

    def _refresh_progress(self) -> None:
        """Show current-operation percentages and pause progress while blocked."""
        if not self.is_active:
            return
        if self._decision is not None or self._cancelling:
            self._progress.hide()
            self._task_progress.update(None)
            return
        self._progress.show()
        step = self._steps.get(self._current_step or "")
        match = _PERCENTAGE.search(step.latest_line) if step else None
        if match is None:
            self._progress.setRange(0, 0)
            self._task_progress.update(None)
        else:
            percentage = int(match.group(1))
            self._progress.setRange(0, 100)
            self._progress.setValue(percentage)
            self._task_progress.update(percentage / 100)

    def _on_session_event(self, event: object) -> None:
        if self._quitting:
            return
        if isinstance(event, OutputChunk):
            self._term.write(event.text)
        elif isinstance(event, StepEvent):
            self._apply_step(event)
        elif isinstance(event, (RetryPrompt, PromptRequest)):
            self._handle_pty_prompt(event)
        elif isinstance(event, AskpassRequest):
            self._handle_askpass(event)
        elif isinstance(event, AskpassExpired):
            self._expire_askpass(event.request_id)
        elif isinstance(event, PromptCleared):
            if isinstance(self._pty_prompt, PromptRequest):
                self._clear_pty_prompt()
        elif isinstance(event, TranscriptWarning):
            self._transcript_incomplete |= event.transcript_incomplete
            self._show_run_warning(event.message)
        elif isinstance(event, SessionFinished):
            self._finish(event)

    def _apply_step(self, event: StepEvent) -> None:
        if self._returncode is not None:
            return
        # Parsed lines, rather than terminal redraws, indicate progress.
        self._last_output = time.monotonic()
        prior = self._steps.get(event.name)
        if prior is None:
            self._step_order.append(event.name)
        self._steps[event.name] = event
        if event.status == "running":
            self._current_step = event.name
        elif self._current_step == event.name:
            self._current_step = None
        if event.status == "failed":
            self._failed_step = event.name

        self._update_step_item(event.name)
        self._record_activity(event, prior)
        self._refresh_progress()
        self._refresh_subtitle()

    def _record_activity(self, event: StepEvent, prior: StepEvent | None) -> None:
        if (
            event.status == "running"
            and (prior is None or prior.status != "running")
            and (not event.latest_line or _STEP_SEPARATOR.match(event.latest_line))
        ):
            text = f"Started {event.name}"
        elif event.status == "succeeded":
            text = f"{event.name} completed"
        elif event.status in {"skipped", "ended"}:
            text = f"{event.name} {event.status}"
        elif event.status == "failed":
            text = f"{event.name} failed" + (f": {event.reason}" if event.reason else "")
        else:
            text = event.reason or event.latest_line
        if not text:
            return
        text = _bounded(text, _ACTIVITY_CHARS)
        latest = next((line for _, step, line in self._activity_lines if step == event.name), None)
        if text == latest:  # also the Summary repeating a failure already shown
            return
        if self._activity_lines:
            _, step, previous = self._activity_lines[0]
            # A failure report grows a line at a time: keep only its latest form.
            growing_failure = event.status == "failed" and prior is not None and (
                prior.status == "failed"
            )
            if step == event.name and (
                growing_failure
                or (
                    _PERCENTAGE.search(text)
                    and _PERCENTAGE.sub("%", text) == _PERCENTAGE.sub("%", previous)
                )
            ):
                self._activity_lines.popleft()
        if self._started_at is not None:
            self._update_elapsed()
        self._activity_lines.appendleft((_format_elapsed(self._elapsed), event.name, text))
        self._activity.setPlainText(
            "\n\n".join(f"{timestamp}   {line}" for timestamp, _, line in self._activity_lines)
        )

    def _update_step_item(self, name: str) -> None:
        step = self._steps.get(name)
        if step is None:
            return
        icon_kind, word = _STEP_STATUS.get(step.status, ("pending", "…"))
        decision = self._decision
        if (
            isinstance(decision, RetryPrompt)
            and decision.step_name == name
            or isinstance(decision, PromptRequest)
            and self._current_step == name
        ):
            icon_kind, word = "warning", "Needs your answer"
        elif isinstance(decision, AskpassRequest) and self._current_step == name:
            icon_kind, word = "warning", "Needs a password"
        item = self._step_items.get(name)
        if item is None:
            item = QListWidgetItem()
            self._step_items[name] = item
            self._step_list.addItem(item)
            self._step_list.scrollToBottom()
        item.setText(f"{name}\n{word}")
        item.setIcon(status_pixmap(icon_kind, ICON_SM))
        item.setToolTip(f"{name} · {word}\n{step.reason or step.latest_line}".strip())

    def _handle_pty_prompt(self, event: PromptRequest | RetryPrompt) -> None:
        if isinstance(event, RetryPrompt) and event.step_name is None:
            event = RetryPrompt(self._failed_step or self._current_step)
        if not self.is_active or self._cancelling or self._pty_prompt == event:
            return
        self._pty_prompt = event
        self._announced_pty_prompt = False
        self._prompt_in_terminal = False
        if self._askpass_requests:
            return
        self._show_new_decision()

    def _handle_askpass(self, event: AskpassRequest) -> None:
        if not self.is_active or self._cancelling:
            return
        if event not in self._askpass_requests:
            self._askpass_requests.append(event)
            if len(self._askpass_requests) == 1:
                self._show_new_decision()

    def _expire_askpass(self, request_id: int) -> None:
        request = next(
            (request for request in self._askpass_requests if request.request_id == request_id),
            None,
        )
        if request is None:
            return
        visible = request is self._askpass_requests[0]
        self._askpass_requests.remove(request)
        if visible:
            self._show_next_decision()

    def _show_new_decision(self) -> None:
        self._render_decision()
        if isinstance(self._decision, AskpassRequest):
            self._notify_if_unseen("Topgrade needs a password", self._prompt_label.text())
        elif not self._announced_pty_prompt:
            self._announced_pty_prompt = True
            self._notify_if_unseen("Topgrade needs your answer", self._prompt_label.text())
        if self.isHidden() or self.isMinimized():
            self.showNormal()
            self.raise_()
            self.activateWindow()
        self.focus_pending_input()

    def _render_decision(self) -> None:
        decision = self._decision
        if decision is None:
            self._prompt_bar.hide()
            self._prompt_input.clear()
            self._refresh_progress()
            self._refresh_subtitle()
        else:
            self._render_prompt_controls(decision)
            self._refresh_progress()
        for name in self._step_order:
            self._update_step_item(name)

    def _render_prompt_controls(
        self, decision: AskpassRequest | PromptRequest | RetryPrompt
    ) -> None:
        prompt_detail = ""
        step = self._current_step
        status = "Waiting for your answer"
        retry = isinstance(decision, RetryPrompt)
        yesno = isinstance(decision, PromptRequest) and not decision.free_text
        password = isinstance(decision, AskpassRequest)
        typed = isinstance(decision, PromptRequest) and decision.free_text

        if isinstance(decision, RetryPrompt):
            step = decision.step_name or self._failed_step or step
            question = f"Retry the {step} step?" if step else "Retry the failed step?"
            failed = self._steps.get(step or "")
            if failed is not None:
                prompt_detail = failed.reason or failed.latest_line
        elif isinstance(decision, AskpassRequest):
            status = "Waiting for a password"
            question = f"Password required for {step}" if step else "Password required"
            prompt_detail = decision.prompt
        else:
            question = decision.question
        detail = "Answer in the terminal" if self._prompt_in_terminal and not password else ""
        if isinstance(decision, PromptRequest) and step and not detail:
            detail = f"Step · {_bounded(step, 100)}"
        tray_status = f"{status} · {step}" if step else status
        self._set_state("warning", status, detail, status=tray_status)

        self._prompt_label.setText(_bounded(question, 350))
        self._prompt_label.setToolTip(question)
        self._prompt_detail.setText(_bounded(prompt_detail, 350))
        self._prompt_detail.setToolTip(prompt_detail)
        self._prompt_detail.setVisible(bool(prompt_detail))
        self._btn_prompt_yes.setVisible(yesno)
        self._btn_prompt_no.setVisible(yesno)
        self._btn_prompt_term.setVisible(yesno or typed)
        self._btn_retry.setVisible(retry)
        self._btn_skip.setVisible(retry)
        self._btn_retry_more.setVisible(retry)
        self._prompt_input.clear()
        self._prompt_input.setVisible(password or typed)
        self._prompt_input.setEchoMode(
            QLineEdit.EchoMode.Password if password else QLineEdit.EchoMode.Normal
        )
        placeholder = "Password" if password else "Answer"
        self._prompt_input.setPlaceholderText(placeholder)
        self._prompt_input.setAccessibleName(placeholder)
        self._btn_prompt_send.setText("Authenticate" if password else "Send")
        self._btn_prompt_send.setVisible(password or typed)
        self._btn_prompt_cancel.setVisible(password)
        self._prompt_bar.setVisible(password or not self._prompt_in_terminal)

    def focus_pending_input(self) -> None:
        """Restore keyboard focus to the latest answer or its terminal."""
        decision = self._decision
        if isinstance(decision, AskpassRequest):
            self._prompt_input.setFocus()
        elif self._prompt_in_terminal:
            self._term.focus_terminal()
        elif isinstance(decision, RetryPrompt):
            self._btn_retry.setFocus()
        elif isinstance(decision, PromptRequest):
            if decision.free_text:
                self._prompt_input.setFocus()
            elif "[Y/n]" in decision.question:
                # Enter answers with the capitalised default, as it does in a terminal.
                self._btn_prompt_yes.setFocus()
            else:
                self._btn_prompt_no.setFocus()

    def _notify_if_unseen(self, summary: str, body: str) -> None:
        if not self._cfg.notifications.enabled:
            return
        if self.isVisible() and self.isActiveWindow() and not self.isMinimized():
            return
        send_message(summary, body)

    def _send_prompt_text(self) -> None:
        text = self._prompt_input.text()
        if isinstance(self._decision, AskpassRequest):
            self._answer_password(text)
        else:
            # An empty answer is meaningful: Enter accepts the command's default.
            self._answer_prompt(text)

    def _answer_password(self, password: str | None) -> None:
        if not self._askpass_requests:
            return
        request = self._askpass_requests.popleft()
        if self._session is not None:
            self._session.reply_askpass(request.request_id, password)
        self._show_next_decision()

    def _show_next_decision(self) -> None:
        if self._decision is not None:
            self._show_new_decision()
        else:
            self._render_decision()

    def _answer_retry(self, key: str) -> None:
        if not isinstance(self._decision, RetryPrompt):
            return
        self._clear_pty_prompt()
        if key == "s":
            self._set_mode("verbose")
        self._pty_write(key)

    def _answer_prompt(self, answer: str) -> None:
        if isinstance(self._decision, PromptRequest):
            self._clear_pty_prompt()
            self._pty_write(f"{answer}\n")

    def _prompt_to_terminal(self) -> None:
        self._prompt_in_terminal = True
        self._set_mode("verbose")
        self._render_decision()

    def _clear_pty_prompt(self) -> None:
        self._pty_prompt = None
        self._prompt_in_terminal = False
        if not self._askpass_requests:
            self._render_decision()

    def _terminal_input(self, data: str) -> None:
        self._pty_write(data)
        submitted = "\r" in data or "\n" in data or data == "\x04"
        retry_choice = isinstance(self._pty_prompt, RetryPrompt) and data.lower() in {
            "y",
            "n",
            "s",
            "q",
        }
        if self._pty_prompt is not None and (submitted or retry_choice):
            self._clear_pty_prompt()

    def _pty_write(self, data: str) -> None:
        if self._session is not None:
            self._session.write(data)

    def _on_term_resize(self, rows: int, cols: int) -> None:
        self._terminal_size = (rows, cols)
        if self._session is not None:
            self._session.resize(rows, cols)

    def confirm_stop(self) -> bool:
        """Ask before interrupting an active update."""
        if self._session is None or not self._session.running:
            return True
        if self._is_dry_run:
            prompt = "Stop this preview?"
        else:
            prompt = "Stopping Topgrade partway can leave packages half-installed. Stop anyway?"
        answer = QMessageBox.question(
            self,
            self._stop_text + "?",
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _cancel(self) -> None:
        if self._session is None or not self.is_active:
            self.close()
        elif self._session.running and self.confirm_stop() and self.is_active:
            self._cancelling = True
            self._pty_prompt = None
            self._askpass_requests.clear()
            self._prompt_in_terminal = False
            self._render_decision()
            self._set_state("warning", "Stopping Topgrade…", "")
            self._btn_cancel.setEnabled(False)
            self._session.cancel()

    def _set_stopped_controls(self) -> None:
        self._btn_hide.hide()
        self._btn_cancel.setEnabled(True)
        self._btn_cancel.setText("Close")
        self._btn_cancel.setProperty("class", None)
        self._btn_cancel.style().unpolish(self._btn_cancel)
        self._btn_cancel.style().polish(self._btn_cancel)

    def _show_run_warning(self, message: str) -> None:
        if message not in self._run_warnings:
            self._run_warnings.append(message)
        warnings = "\n".join(self._run_warnings)
        self._warning_label.setText(_bounded(warnings, 260))
        self._warning_label.setToolTip(warnings)
        self._warning_label.show()

    def _finish(self, event: SessionFinished) -> None:
        if self._returncode is not None:
            return
        self._timer.stop()
        self._spin_timer.stop()
        self._update_elapsed()
        self._returncode = event.returncode
        self._task_progress.update(None)
        self._log_path = event.log_path
        self._failed_step = event.failed_step
        self._pty_prompt = None
        self._askpass_requests.clear()
        self._prompt_in_terminal = False
        self._prompt_bar.hide()
        self._prompt_input.clear()
        self._sweep_open_steps()
        self._set_stopped_controls()
        prune_runs(self._runs_dir)
        if event.transcript_incomplete and not self._transcript_incomplete:
            self._show_run_warning("Transcript is incomplete. Verbose still has the live output.")

        run_name = "Preview" if self._is_dry_run else "Update"
        if event.cancelled:
            self._progress.hide()
            self._btn_try_again.show()
            summary = f"{run_name} stopped after {_format_elapsed(self._elapsed)}."
            self._set_state("skipped", f"{run_name} cancelled", summary)
            notice = f"{run_name} cancelled"
        elif event.returncode == 0:
            self._progress.show()
            self._progress.setRange(0, 1)
            self._progress.setValue(1)
            notice = f"{run_name} finished"
            summary = (
                "No changes were made." if self._is_dry_run else "Topgrade finished successfully."
            )
            self._set_state("done", f"{run_name} complete", summary)
            if self._is_dry_run and self._on_run_for_real is not None:
                self._btn_run_real.show()
                self._btn_run_real.setDefault(True)
            else:
                self._btn_cancel.setDefault(True)
                set_primary(self._btn_cancel)
        else:
            self._progress.hide()
            failed = self._failed_step or self._current_step
            detail = f"Exit code {event.returncode}"
            if failed:
                detail = f"{_bounded(failed, 100)} failed · {detail}"
            reason = self._failure_reason()
            summary = f"{detail}\n{reason}" if reason else detail
            self._set_state("failed", f"{run_name} failed", summary)
            self._subtitle_label.setToolTip(self._failure_reason(full=True) or "")
            self._btn_try_again.show()
            self._btn_diagnose.setDefault(True)
            notice = f"{run_name} failed"
        self._notify_if_unseen(notice, f"{summary}\n{self._scope}")
        self._emit_finished(event.returncode)

    def _emit_finished(self, returncode: int) -> None:
        self.finished.emit(returncode)
        if self._on_finished is not None:
            self._on_finished(returncode)

    def _failure_reason(self, *, full: bool = False) -> str | None:
        step = self._steps.get(self._failed_step or "")
        reason = step.reason if step is not None else None
        if not reason or full:
            return reason
        return _bounded(" ".join(reason.split()), 240)

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
        """Clear incomplete step statuses while preserving confirmed outcomes."""
        for name in self._step_order:
            if self._steps[name].status in {"pending", "running"}:
                item = self._step_items.get(name)
                if item is not None:
                    item.setText(f"{name}\nEnded")
                    item.setIcon(status_pixmap("skipped", ICON_SM))
            else:
                self._update_step_item(name)

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

    def shutdown(self) -> None:
        """Stop any running session and close for real (used on app quit)."""
        self._quitting = True
        self._task_progress.update(None)
        self.close()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        # Terminal keys must still reach the PTY when Verbose has focus.
        if event.key() == Qt.Key.Key_Escape and not self.is_active:
            self.close()
            return
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and self._decision is not None:
            focus = self.focusWidget()
            if isinstance(focus, QPushButton) and self._prompt_bar.isAncestorOf(focus):
                focus.click()
                return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        save_window_state(self, "run_window", self._body)
        if self.is_active and self._session is not None:
            event.ignore()
            self.hide()
            if not self._background_notice_sent:
                # This confirms the user's action, even with notifications disabled.
                self._background_notice_sent = True
                send_message(
                    "Still running in the background",
                    "Choose Open current run in the tray to bring the window back.",
                )
            return
        self._quitting = True  # A queued _start must not run after closing.
        self._timer.stop()
        self._spin_timer.stop()
        self._prompt_input.clear()
        if self._session is not None and self._session.running:
            self._session.cancel()
            self._session.wait(timeout=2)
            self._session.close()
        self._diagnose.close_session()
        super().closeEvent(event)
        self.closed.emit()
