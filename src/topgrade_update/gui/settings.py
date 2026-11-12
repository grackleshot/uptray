"""Settings dialog exposing the TOML configuration graphically."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from topgrade_update.core import autostart
from topgrade_update.core.models import Config, SourceConfig
from topgrade_update.gui.style import apply_theme, colors, set_primary

if TYPE_CHECKING:
    from collections.abc import Mapping

CLICK_ACTIONS = {"default": "Default (show updates)",
                 "show_updates": "Show updates dialog",
                 "run_topgrade": "Run topgrade"}
ICON_STYLES = {"default": "Default", "colorblind": "Colorblind-safe"}
RUN_MODES = {"simple": "Simple", "verbose": "Verbose"}

# Plain-language descriptions for built-in update sources.
_SOURCE_LABELS: Mapping[str, str] = {
    "pacman": "Official Arch repositories (pacman)",
    "aur": "AUR helpers (paru, yay, pikaur)",
    "flatpak": "Flatpak apps & runtimes",
    "firmware": "Device firmware (fwupdmgr)",
    "reboot": "Reboot-required indicator",
}


def _caption(text: str) -> QLabel:
    """Small muted helper text explaining the setting above it."""
    muted = colors().get("muted", "#98a1ab")
    label = QLabel(f'<span style="color:{muted}; font-size: 8.5pt;">{text}</span>')
    label.setWordWrap(True)
    return label


class SettingsDialog(QDialog):
    """Edit the topgrade-update configuration without touching TOML."""

    def __init__(self, cfg: Config, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        apply_theme(self)
        self.setWindowTitle("Topgrade Update — Settings")
        self.setMinimumWidth(540)
        self._cfg = cfg
        self._source_boxes: dict[str, QCheckBox] = {}
        self._custom_boxes: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(10)

        # --- Checking for updates ----------------------------------------
        checking = QGroupBox("Checking for updates")
        checking_form = QFormLayout(checking)
        checking_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._interval = QSpinBox()
        self._interval.setRange(5, 1440)
        self._interval.setSingleStep(5)
        self._interval.setSuffix(" min")
        checking_form.addRow("Check every", self._interval)
        checking_form.addRow("", _caption("How often updates are looked for (5–1440 minutes)."))

        self._terminals = QLineEdit()
        self._terminals.setPlaceholderText("konsole, alacritty, kitty")
        checking_form.addRow("Terminal priority", self._terminals)
        checking_form.addRow(
            "", _caption(
                "Used only when xdg-terminal-exec and $TERMINAL are not available; "
                "tried in order."
            )
        )

        sources_row = QVBoxLayout()
        sources_row.setSpacing(6)
        for name in [*_SOURCE_LABELS, *sorted(set(cfg.sources) - set(_SOURCE_LABELS))]:
            box = QCheckBox(_SOURCE_LABELS.get(name, name))
            self._source_boxes[name] = box
            sources_row.addWidget(box)
        for custom in cfg.custom_commands:
            box = QCheckBox(f"custom: {custom.name}")
            self._custom_boxes[custom.name] = box
            sources_row.addWidget(box)
        sources_widget = QWidget()
        sources_widget.setLayout(sources_row)
        checking_form.addRow("Update sources", sources_widget)
        checking_form.addRow(
            "", _caption("Places to look for updates. Untick a source to skip it.")
        )
        root.addWidget(checking)

        # --- Running updates ---------------------------------------------
        running = QGroupBox("Running updates")
        running_form = QFormLayout(running)
        running_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._run_mode = QComboBox()
        for value, label in RUN_MODES.items():
            self._run_mode.addItem(label, value)
        running_form.addRow("Run mode", self._run_mode)
        running_form.addRow(
            "",
            _caption(
                "Simple shows friendly step-by-step progress; "
                "Verbose shows the full terminal output."
            ),
        )
        root.addWidget(running)

        # --- Tray & notifications ----------------------------------------
        tray = QGroupBox("Tray && notifications")
        tray_form = QFormLayout(tray)
        tray_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self._click_action = QComboBox()
        for value, label in CLICK_ACTIONS.items():
            self._click_action.addItem(label, value)
        tray_form.addRow("Left-click on tray icon", self._click_action)

        self._snooze_hours = QSpinBox()
        self._snooze_hours.setRange(1, 24)
        self._snooze_hours.setSuffix(" h")
        tray_form.addRow("Snooze duration", self._snooze_hours)
        tray_form.addRow(
            "", _caption("How long notifications stay silent after snoozing.")
        )

        self._icon_style = QComboBox()
        for value, label in ICON_STYLES.items():
            self._icon_style.addItem(label, value)
        tray_form.addRow("Icon style", self._icon_style)

        self._notifications_enabled = QCheckBox("Enable desktop notifications")
        tray_form.addRow("", self._notifications_enabled)
        self._notifications_sound = QCheckBox("Play notification sound")
        tray_form.addRow("", self._notifications_sound)
        quiet_row = QHBoxLayout()
        quiet_row.setSpacing(6)
        self._quiet_start = _hour_combo()
        self._quiet_end = _hour_combo()
        quiet_row.addWidget(self._quiet_start)
        quiet_row.addWidget(QLabel("to"))
        quiet_row.addWidget(self._quiet_end)
        quiet_row.addStretch()
        tray_form.addRow("Quiet hours", quiet_row)
        tray_form.addRow(
            "", _caption("During quiet hours, checks still run but nothing pops up.")
        )
        self._quiet_warning = QLabel(
            "Quiet hours need different start and end times, or both set to (off)."
        )
        self._quiet_warning.setWordWrap(True)
        self._quiet_warning.setStyleSheet(f"color: {colors().get('warning', '#d9a441')};")
        tray_form.addRow("", self._quiet_warning)
        self._quiet_start.currentIndexChanged.connect(self._update_quiet_warning)
        self._quiet_end.currentIndexChanged.connect(self._update_quiet_warning)

        self._autostart_initial = autostart.AUTOSTART_FILE.exists()
        self._autostart = QCheckBox("Start the tray applet at login")
        self._autostart.setChecked(self._autostart_initial)
        tray_form.addRow("", self._autostart)
        root.addWidget(tray)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        ok_button = QPushButton("Save")
        ok_button.setDefault(True)
        set_primary(ok_button)
        buttons.addButton(ok_button, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            lambda: self._populate(Config())
        )
        root.addWidget(buttons)
        self._populate(cfg)

    def _populate(self, cfg: Config) -> None:
        """Fill every widget from cfg (also used by Restore Defaults)."""
        self._interval.setValue(cfg.check_interval // 60)
        self._terminals.setText(", ".join(cfg.terminals))
        for name, box in self._source_boxes.items():
            box.setChecked(cfg.sources.get(name, SourceConfig()).enabled)
        enabled = {custom.name: custom.enabled for custom in cfg.custom_commands}
        for name, custom_box in self._custom_boxes.items():
            custom_box.setChecked(enabled.get(name, True))
        _select(self._run_mode, cfg.run_mode if cfg.run_mode in RUN_MODES else "simple")
        _select(self._click_action, cfg.tray.click_action)
        self._snooze_hours.setValue(cfg.tray.snooze_hours)
        _select(self._icon_style, cfg.tray.icon_style)
        self._notifications_enabled.setChecked(cfg.notifications.enabled)
        self._notifications_sound.setChecked(cfg.notifications.sound)
        _select(self._quiet_start, cfg.notifications.quiet_hours_start)
        _select(self._quiet_end, cfg.notifications.quiet_hours_end)
        self._update_quiet_warning()

    def _update_quiet_warning(self) -> None:
        """Show the warning when quiet hours would silently do nothing."""
        start = self._quiet_start.currentData()
        end = self._quiet_end.currentData()
        one_sided = (start is None) != (end is None)
        self._quiet_warning.setVisible(one_sided or (start is not None and start == end))

    def accept(self) -> None:
        """Apply the autostart toggle (if changed), then close."""
        if self._autostart.isChecked() != self._autostart_initial:
            try:
                if self._autostart.isChecked():
                    autostart.enable_autostart()
                else:
                    autostart.disable_autostart()
            except OSError as exc:
                QMessageBox.warning(self, "Autostart", f"Could not change autostart: {exc}")
        super().accept()

    def get_config(self) -> Config:
        """Build a new Config from the current widget state."""
        terminals = [term.strip() for term in self._terminals.text().split(",")]
        sources: dict[str, SourceConfig] = {}
        for name, box in self._source_boxes.items():
            existing = self._cfg.sources.get(name)
            if existing is None and box.isChecked():
                continue  # untouched default: keep the config file minimal
            sources[name] = replace(existing or SourceConfig(), enabled=box.isChecked())
        custom_commands = []
        for custom in self._cfg.custom_commands:
            custom_box: QCheckBox | None = self._custom_boxes.get(custom.name)
            if custom_box is None:
                custom_commands.append(custom)
                continue
            custom_commands.append(replace(custom, enabled=custom_box.isChecked()))
        return Config(
            check_interval=self._interval.value() * 60,
            terminals=[term for term in terminals if term],
            sources=sources,
            notifications=replace(
                self._cfg.notifications,
                enabled=self._notifications_enabled.isChecked(),
                sound=self._notifications_sound.isChecked(),
                quiet_hours_start=self._quiet_start.currentData(),
                quiet_hours_end=self._quiet_end.currentData(),
            ),
            tray=replace(
                self._cfg.tray,
                click_action=self._click_action.currentData(),
                snooze_hours=self._snooze_hours.value(),
                icon_style=self._icon_style.currentData(),
            ),
            custom_commands=custom_commands,
            run_mode=self._run_mode.currentData(),
        )


def _select(combo: QComboBox, value: object) -> None:
    """Select the item whose data equals value (first item if absent)."""
    combo.setCurrentIndex(max(0, combo.findData(value)))


def _hour_combo() -> QComboBox:
    """Combo box for a quiet-hours hour, with a disabled option."""
    combo = QComboBox()
    combo.addItem("(off)", None)
    for hour in range(24):
        combo.addItem(f"{hour:02d}:00", hour)
    return combo
