from __future__ import annotations

import os
import sys
from pathlib import Path

# A realistic 1920x1080 screen: the default offscreen screen is 800x800, smaller
# than RunWindow's minimum width, so restored geometry got clamped by font metrics.
os.environ.setdefault(
    "QT_QPA_PLATFORM",
    f"offscreen:configfile={Path(__file__).with_name('offscreen-screen.json')}",
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolate_qsettings(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point QSettings at a temp dir before anything caches the real path."""
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        return
    path = str(tmp_path_factory.mktemp("qsettings"))
    for fmt in (QSettings.Format.NativeFormat, QSettings.Format.IniFormat):
        QSettings.setPath(fmt, QSettings.Scope.UserScope, path)


@pytest.fixture(autouse=True)
def _isolate_xdg_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test touch the real ~/.config, ~/.local/share or ~/.local/state."""
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / "xdg" / var.lower()))
