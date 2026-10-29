"""Tests for the system tray applet."""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from topgrade_update.core.models import Config, TrayConfig
from topgrade_update.gui.tray import Tray

@pytest.fixture
def mock_cfg():
    """Mock configuration for the tray applet."""
    return Config(
        tray=TrayConfig(
            click_action="show_updates",
            snooze_hours=1,
        ),
        notifications={
            "enabled": True,
            "quiet_hours_start": "00:00",
            "quiet_hours_end": "08:00",
        },
    )

def test_tray_initialization(mock_cfg):
    """Test that the tray icon is initialized with correct values."""
    with patch("topgrade_update.gui.tray.Tray.setIcon") as mock_set_icon, \
         patch("topgrade_update.gui.tray.Tray.setToolTip") as mock_set_tooltip, \
         patch("topgrade_update.gui.tray.IconCache") as mock_cache_class, \
         patch("topgrade_update.gui.tray.QMenu") as mock_menu_class, \
         patch("topgrade_update.gui.tray.QSystemTrayIcon.__init__", lambda *args, **kwargs: None):
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.idle.return_value = "idle_icon"
        
        mock_menu = mock_menu_class.return_value
        mock_menu.addAction.return_value = MagicMock()
        
        tray = Tray(mock_cfg)
        
        assert mock_cache_instance.idle.called
        assert mock_set_tooltip.called
        assert mock_set_icon.called
        assert len(tray._menu.actions()) > 0

def test_snooze_logic(mock_cfg):
    """Test that snoozing correctly updates the state and tooltip."""
    with patch("topgrade_update.gui.tray.IconCache") as mock_cache_class, \
         patch("topgrade_update.gui.tray.QMenu") as mock_menu_class, \
         patch("topgrade_update.gui.tray.QSystemTrayIcon.__init__", lambda *args, **kwargs: None):
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.idle.return_value = "idle_icon"
        
        mock_menu = mock_menu_class.return_value
        mock_menu.addAction.return_value = MagicMock()
        
        tray = Tray(mock_cfg)
        
        # Snooze for 2 hours
        tray._snooze(2)
        assert tray._snooze_until is not None
        assert (datetime.now() + timedelta(hours=2)) in str(tray._snooze_until)
        
        # Verify update_status_action was called (implicitly checked by status action)
        assert "2 hours" in tray._action_status.text()

def test_is_snoozed(mock_cfg):
    """Test the is_snoozed helper method."""
    with patch("topgrade_update.gui.tray.IconCache") as mock_cache_class, \
         patch("topgrade_update.gui.tray.QMenu") as mock_menu_class, \
         patch("topgrade_update.gui.tray.QSystemTrayIcon.__init__", lambda *args, **kwargs: None):
        
        mock_cache_instance = mock_cache_class.return_value
        mock_cache_instance.idle.return_value = "idle_icon"
        
        mock_menu = mock_menu_class.return_value
        mock_menu.addAction.return_value = MagicMock()
        
        tray = Tray(mock_cfg)
        
        # Initially not snoozed
        assert tray._is_snoozed() is False
        
        # Snooze for 1 hour
        tray._snooze(1)
        assert tray._is_snoozed() is True
        
        # Advance time manually (mocking datetime might be cleaner but let's just check if it expires)
        tray._snooze_until = datetime.now() - timedelta(seconds=1)
        assert tray._is_snoozed() is False
