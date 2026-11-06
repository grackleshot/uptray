"""Data models for update checking and configuration."""

from __future__ import annotations

from dataclasses import dataclass, field


def custom_checker_name(display_name: str) -> str:
    """Return the stable checker ID used for a custom command display name."""
    return f"custom_{display_name.lower().replace(' ', '_')}"


@dataclass(frozen=True)
class Update:
    """A single available update."""

    name: str
    old_version: str
    new_version: str
    source: str
    branch: str | None = None


@dataclass
class CheckResult:
    """Result of a single checker run."""

    source: str
    updates: list[Update] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0

    @property
    def success(self) -> bool:
        """Return True if the check completed without error."""
        return self.error is None


@dataclass
class SourceConfig:
    """Per-source configuration."""

    enabled: bool = True


@dataclass
class NotificationConfig:
    """Notification settings."""

    enabled: bool = True
    quiet_hours_start: int | None = None  # 0-23, inclusive
    quiet_hours_end: int | None = None  # 0-23, inclusive
    sound: bool = False  # request the server's default notification sound


@dataclass
class TrayConfig:
    """System tray behavior settings."""

    click_action: str = "default"  # "default", "show_updates", "run_topgrade"
    snooze_hours: int = 4
    icon_style: str = "default"  # "default", "colorblind"


@dataclass
class CustomCommandConfig:
    """Configuration for one user-defined update checker command."""

    name: str
    command: list[str]
    enabled: bool = True


@dataclass
class Config:
    """Application configuration."""

    check_interval: int = 3600  # seconds
    sources: dict[str, SourceConfig] = field(
        default_factory=lambda: {
            "pacman": SourceConfig(),
            "aur": SourceConfig(),
            "flatpak": SourceConfig(),
        }
    )
    terminals: list[str] = field(
        default_factory=lambda: [
            "konsole",
            "alacritty",
            "kitty",
            "xterm",
        ]
    )
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    tray: TrayConfig = field(default_factory=TrayConfig)
    custom_commands: list[CustomCommandConfig] = field(default_factory=list)
