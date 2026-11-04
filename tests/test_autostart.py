from __future__ import annotations

import topgrade_update.core.autostart as autostart


def _point_at(tmp_path, monkeypatch):
    dest_dir = tmp_path / "autostart"
    monkeypatch.setattr(autostart, "AUTOSTART_DIR", dest_dir)
    monkeypatch.setattr(autostart, "AUTOSTART_FILE", dest_dir / "topgrade-update-tray.desktop")


def test_enable_creates_desktop_file(tmp_path, monkeypatch, capsys) -> None:
    _point_at(tmp_path, monkeypatch)

    autostart.enable_autostart()

    file = autostart.AUTOSTART_FILE
    assert file.exists()
    content = file.read_text()
    assert content.startswith("[Desktop Entry]")
    assert "Exec=topgrade-update --tray" in content
    assert "Autostart enabled" in capsys.readouterr().out


def test_disable_removes_desktop_file(tmp_path, monkeypatch, capsys) -> None:
    _point_at(tmp_path, monkeypatch)
    autostart.enable_autostart()

    autostart.disable_autostart()

    assert not autostart.AUTOSTART_FILE.exists()
    assert "Autostart disabled" in capsys.readouterr().out


def test_disable_when_absent_prints_not_enabled(tmp_path, monkeypatch, capsys) -> None:
    _point_at(tmp_path, monkeypatch)

    autostart.disable_autostart()

    assert capsys.readouterr().out == "Autostart was not enabled.\n"
