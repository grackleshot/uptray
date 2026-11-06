"""Settings dialog exposing the TOML configuration graphically."""

from __future__ import annotations

from dataclasses import replace

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
    QSpinBox,
    QVBoxLayout,
)

from topgrade_update.core.models import Config, SourceConfig

CLICK_ACTIONS = {"default": "Default (updates dialog or topgrade)",
                 "show_updates": "Show updates dialog",
                 "run_topgrade": "Run topgrade"}
ICON_STYLES = {"default": "Default", "colorblind": "Colorblind-safe"}


class SettingsDialog(QDialog):
    """Edit the topgrade-update configuration without touching TOML."""

    def __init__(self, cfg: Config, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Topgrade Update — Settings")
        self.setMinimumWidth(480)
        self._cfg = cfg
        self._source_boxes: dict[str, QCheckBox] = {}
        self._custom_boxes: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)

        form = QFormLayout()

        self._interval = QSpinBox()
        self._interval.setRange(300, 86400)
        self._interval.setSingleStep(300)
        self._interval.setSuffix(" s")
        self._interval.setValue(cfg.check_interval)
        form.addRow("Check interval", self._interval)

        self._terminals = QLineEdit(", ".join(cfg.terminals))
        self._terminals.setPlaceholderText("konsole, alacritty, kitty")
        form.addRow("Terminal priority", self._terminals)

        self._click_action = QComboBox()
        for value, label in CLICK_ACTIONS.items():
            self._click_action.addItem(label, value)
        self._click_action.setCurrentIndex(
            max(0, list(CLICK_ACTIONS).index(cfg.tray.click_action))
        )
        form.addRow("Tray click action", self._click_action)

        self._snooze_hours = QSpinBox()
        self._snooze_hours.setRange(1, 24)
        self._snooze_hours.setSuffix(" h")
        self._snooze_hours.setValue(cfg.tray.snooze_hours)
        form.addRow("Snooze duration", self._snooze_hours)

        self._icon_style = QComboBox()
        for value, label in ICON_STYLES.items():
            self._icon_style.addItem(label, value)
        self._icon_style.setCurrentIndex(
            max(0, list(ICON_STYLES).index(cfg.tray.icon_style))
        )
        form.addRow("Icon style", self._icon_style)

        root.addLayout(form)

        notifications = QGroupBox("Notifications")
        notifications_layout = QVBoxLayout(notifications)

        self._notifications_enabled = QCheckBox("Enable desktop notifications")
        self._notifications_enabled.setChecked(cfg.notifications.enabled)
        notifications_layout.addWidget(self._notifications_enabled)

        self._notifications_sound = QCheckBox("Play notification sound")
        self._notifications_sound.setChecked(cfg.notifications.sound)
        notifications_layout.addWidget(self._notifications_sound)

        quiet_row = QHBoxLayout()
        quiet_row.addWidget(QLabel("Quiet hours"))
        self._quiet_start = _hour_combo(cfg.notifications.quiet_hours_start)
        self._quiet_end = _hour_combo(cfg.notifications.quiet_hours_end)
        quiet_row.addWidget(self._quiet_start)
        quiet_row.addWidget(QLabel("to"))
        quiet_row.addWidget(self._quiet_end)
        quiet_row.addStretch()
        notifications_layout.addLayout(quiet_row)

        root.addWidget(notifications)

        sources = QGroupBox("Update sources")
        sources_layout = QVBoxLayout(sources)
        for name in sorted(cfg.sources):
            box = QCheckBox(name)
            box.setChecked(cfg.sources[name].enabled)
            self._source_boxes[name] = box
            sources_layout.addWidget(box)
        for custom in cfg.custom_commands:
            box = QCheckBox(f"custom: {custom.name}")
            box.setChecked(custom.enabled)
            self._custom_boxes[custom.name] = box
            sources_layout.addWidget(box)
        root.addWidget(sources)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def get_config(self) -> Config:
        """Build a new Config from the current widget state."""
        terminals = [term.strip() for term in self._terminals.text().split(",")]
        sources: dict[str, SourceConfig] = {}
        for name, box in self._source_boxes.items():
            existing = self._cfg.sources.get(name, SourceConfig())
            sources[name] = replace(existing, enabled=box.isChecked())
        custom_commands = []
        for custom in self._cfg.custom_commands:
            custom_box: QCheckBox | None = self._custom_boxes.get(custom.name)
            if custom_box is None:
                custom_commands.append(custom)
                continue
            custom_commands.append(replace(custom, enabled=custom_box.isChecked()))
        return Config(
            check_interval=self._interval.value(),
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
        )


def _hour_combo(value: int | None) -> QComboBox:
    """Combo box for a quiet-hours hour, with a disabled option."""
    combo = QComboBox()
    combo.addItem("(off)", None)
    for hour in range(24):
        combo.addItem(f"{hour:02d}:00", hour)
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo
