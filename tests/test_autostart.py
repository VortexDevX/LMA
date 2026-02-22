"""
Tests for auto-start management module.
"""

import sys
import pytest # type: ignore
from unittest.mock import patch, MagicMock, call
from pathlib import Path


# ── get_exe_path ─────────────────────────────────────────


class TestGetExePath:
    def test_returns_executable_when_frozen(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", r"C:\Agent\LocalMonitorAgent.exe")
        from src.utils.autostart import get_exe_path

        assert get_exe_path() == r"C:\Agent\LocalMonitorAgent.exe"

    def test_returns_none_when_not_frozen(self, monkeypatch):
        if hasattr(sys, "frozen"):
            monkeypatch.delattr(sys, "frozen")
        from src.utils.autostart import get_exe_path

        assert get_exe_path() is None


# ── Windows ──────────────────────────────────────────────


class TestWindowsRegister:
    @patch("src.utils.autostart.get_exe_path", return_value=r"C:\Agent\Agent.exe")
    def test_register_success(self, mock_exe):
        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key) as mock_open, \
             patch("winreg.SetValueEx") as mock_set, \
             patch("winreg.CloseKey") as mock_close:
            from src.utils.autostart import _register_windows

            result = _register_windows()

            assert result is True
            mock_set.assert_called_once_with(
                mock_key, "LocalMonitorAgent", 0,
                1,  # REG_SZ
                '"C:\\Agent\\Agent.exe"',
            )
            mock_close.assert_called_once_with(mock_key)

    @patch("src.utils.autostart.get_exe_path", return_value=None)
    def test_register_not_frozen(self, mock_exe):
        from src.utils.autostart import _register_windows

        result = _register_windows()
        assert result is False

    @patch("src.utils.autostart.get_exe_path", return_value=r"C:\Agent\Agent.exe")
    def test_register_exception(self, mock_exe):
        with patch("winreg.OpenKey", side_effect=OSError("access denied")):
            from src.utils.autostart import _register_windows

            result = _register_windows()
            assert result is False


class TestWindowsUnregister:
    def test_unregister_success(self):
        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key), \
             patch("winreg.DeleteValue") as mock_del, \
             patch("winreg.CloseKey"):
            from src.utils.autostart import _unregister_windows

            result = _unregister_windows()

            assert result is True
            mock_del.assert_called_once_with(mock_key, "LocalMonitorAgent")

    def test_unregister_not_found(self):
        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key), \
             patch("winreg.DeleteValue", side_effect=FileNotFoundError), \
             patch("winreg.CloseKey"):
            from src.utils.autostart import _unregister_windows

            result = _unregister_windows()
            assert result is True  # Not found is still success

    def test_unregister_exception(self):
        with patch("winreg.OpenKey", side_effect=OSError("access denied")):
            from src.utils.autostart import _unregister_windows

            result = _unregister_windows()
            assert result is False


class TestWindowsCheck:
    def test_check_enabled(self):
        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key), \
             patch("winreg.QueryValueEx", return_value=(r'"C:\Agent\Agent.exe"', 1)), \
             patch("winreg.CloseKey"):
            from src.utils.autostart import _check_windows

            assert _check_windows() is True

    def test_check_not_found(self):
        mock_key = MagicMock()
        with patch("winreg.OpenKey", return_value=mock_key), \
             patch("winreg.QueryValueEx", side_effect=FileNotFoundError), \
             patch("winreg.CloseKey"):
            from src.utils.autostart import _check_windows

            assert _check_windows() is False

    def test_check_exception(self):
        with patch("winreg.OpenKey", side_effect=OSError):
            from src.utils.autostart import _check_windows

            assert _check_windows() is False


# ── macOS ────────────────────────────────────────────────


class TestMacOSAutostart:
    @patch("src.utils.autostart.get_exe_path", return_value="/app/Agent")
    def test_register_writes_plist(self, mock_exe, tmp_path, monkeypatch):
        plist_path = tmp_path / "com.company.localmonitoragent.plist"
        monkeypatch.setattr(
            "src.utils.autostart._get_plist_path", lambda: plist_path
        )
        from src.utils.autostart import _register_macos

        result = _register_macos()

        assert result is True
        assert plist_path.exists()
        content = plist_path.read_text()
        assert "/app/Agent" in content
        assert "RunAtLoad" in content

    @patch("src.utils.autostart.get_exe_path", return_value=None)
    def test_register_not_frozen(self, mock_exe):
        from src.utils.autostart import _register_macos

        assert _register_macos() is False

    def test_unregister_removes_plist(self, tmp_path, monkeypatch):
        plist_path = tmp_path / "com.company.localmonitoragent.plist"
        plist_path.write_text("plist content")
        monkeypatch.setattr(
            "src.utils.autostart._get_plist_path", lambda: plist_path
        )
        from src.utils.autostart import _unregister_macos

        result = _unregister_macos()

        assert result is True
        assert not plist_path.exists()

    def test_unregister_missing_file(self, tmp_path, monkeypatch):
        plist_path = tmp_path / "nonexistent.plist"
        monkeypatch.setattr(
            "src.utils.autostart._get_plist_path", lambda: plist_path
        )
        from src.utils.autostart import _unregister_macos

        assert _unregister_macos() is True

    def test_check_enabled(self, tmp_path, monkeypatch):
        plist_path = tmp_path / "com.company.localmonitoragent.plist"
        plist_path.write_text("plist content")
        monkeypatch.setattr(
            "src.utils.autostart._get_plist_path", lambda: plist_path
        )
        from src.utils.autostart import _check_macos

        assert _check_macos() is True

    def test_check_disabled(self, tmp_path, monkeypatch):
        plist_path = tmp_path / "nonexistent.plist"
        monkeypatch.setattr(
            "src.utils.autostart._get_plist_path", lambda: plist_path
        )
        from src.utils.autostart import _check_macos

        assert _check_macos() is False


# ── Linux ────────────────────────────────────────────────


class TestLinuxAutostart:
    @patch("src.utils.autostart.get_exe_path", return_value="/opt/agent/Agent")
    def test_register_writes_desktop(self, mock_exe, tmp_path, monkeypatch):
        desktop_path = tmp_path / "localmonitoragent.desktop"
        monkeypatch.setattr(
            "src.utils.autostart._get_desktop_path", lambda: desktop_path
        )
        from src.utils.autostart import _register_linux

        result = _register_linux()

        assert result is True
        assert desktop_path.exists()
        content = desktop_path.read_text()
        assert "/opt/agent/Agent" in content
        assert "[Desktop Entry]" in content

    @patch("src.utils.autostart.get_exe_path", return_value=None)
    def test_register_not_frozen(self, mock_exe):
        from src.utils.autostart import _register_linux

        assert _register_linux() is False

    def test_unregister_removes_desktop(self, tmp_path, monkeypatch):
        desktop_path = tmp_path / "localmonitoragent.desktop"
        desktop_path.write_text("desktop content")
        monkeypatch.setattr(
            "src.utils.autostart._get_desktop_path", lambda: desktop_path
        )
        from src.utils.autostart import _unregister_linux

        result = _unregister_linux()

        assert result is True
        assert not desktop_path.exists()

    def test_check_enabled(self, tmp_path, monkeypatch):
        desktop_path = tmp_path / "localmonitoragent.desktop"
        desktop_path.write_text("desktop content")
        monkeypatch.setattr(
            "src.utils.autostart._get_desktop_path", lambda: desktop_path
        )
        from src.utils.autostart import _check_linux

        assert _check_linux() is True

    def test_check_disabled(self, tmp_path, monkeypatch):
        desktop_path = tmp_path / "nonexistent.desktop"
        monkeypatch.setattr(
            "src.utils.autostart._get_desktop_path", lambda: desktop_path
        )
        from src.utils.autostart import _check_linux

        assert _check_linux() is False


# ── Public API dispatch ──────────────────────────────────


class TestPublicAPIDispatch:
    @patch("src.utils.autostart._register_windows", return_value=True)
    def test_register_dispatches_windows(self, mock_reg, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.utils.autostart import register_autostart

        assert register_autostart() is True
        mock_reg.assert_called_once()

    @patch("src.utils.autostart._unregister_windows", return_value=True)
    def test_unregister_dispatches_windows(self, mock_unreg, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.utils.autostart import unregister_autostart

        assert unregister_autostart() is True
        mock_unreg.assert_called_once()

    @patch("src.utils.autostart._check_windows", return_value=True)
    def test_check_dispatches_windows(self, mock_check, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        from src.utils.autostart import is_autostart_enabled

        assert is_autostart_enabled() is True
        mock_check.assert_called_once()

    @patch("src.utils.autostart._register_macos", return_value=True)
    def test_register_dispatches_macos(self, mock_reg, monkeypatch):
        monkeypatch.setattr(sys, "platform", "darwin")
        from src.utils.autostart import register_autostart

        assert register_autostart() is True
        mock_reg.assert_called_once()

    @patch("src.utils.autostart._register_linux", return_value=True)
    def test_register_dispatches_linux(self, mock_reg, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        from src.utils.autostart import register_autostart

        assert register_autostart() is True
        mock_reg.assert_called_once()