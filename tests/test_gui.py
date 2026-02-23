"""
Tests for Phase 15: GUI Enhancement.
Covers setup wizard module, agent core GUI fallback, and tray employee display.
"""

import sys
import pytest # type: ignore
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================
# Setup wizard module tests
# ============================================================

class TestSetupWizardModule:
    """Basic tests for the setup_wizard module."""

    def test_is_tk_available_returns_bool(self):
        from src.ui.setup_wizard import is_tk_available

        result = is_tk_available()
        assert isinstance(result, bool)

    def test_is_tk_available_true_in_test_env(self):
        """tkinter should be available in our test environment."""
        from src.ui.setup_wizard import is_tk_available

        assert is_tk_available() is True

    def test_detect_device_type_laptop(self):
        from src.ui.setup_wizard import SetupWizard

        mock_battery = MagicMock()
        with patch("psutil.sensors_battery", return_value=mock_battery):
            assert SetupWizard._detect_device_type() == "laptop"

    def test_detect_device_type_desktop(self):
        from src.ui.setup_wizard import SetupWizard

        with patch("psutil.sensors_battery", return_value=None):
            assert SetupWizard._detect_device_type() == "desktop"

    def test_detect_device_type_exception(self):
        from src.ui.setup_wizard import SetupWizard

        with patch("psutil.sensors_battery", side_effect=RuntimeError("nope")):
            assert SetupWizard._detect_device_type() == "desktop"

    def test_run_setup_wizard_returns_false_when_tk_unavailable(self):
        from src.ui import setup_wizard

        with patch.object(setup_wizard, "_TK_AVAILABLE", False):
            result = setup_wizard.run_setup_wizard(MagicMock(), MagicMock())
            assert result is False

    def test_run_setup_wizard_catches_exception(self):
        """If wizard crashes on launch, returns False instead of raising."""
        from src.ui import setup_wizard

        with patch.object(setup_wizard, "_TK_AVAILABLE", True), \
             patch.object(setup_wizard, "SetupWizard", side_effect=RuntimeError("boom")):
            result = setup_wizard.run_setup_wizard(MagicMock(), MagicMock())
            assert result is False


# ============================================================
# Wizard login logic tests (no GUI)
# ============================================================

class TestWizardLoginLogic:
    """Test the _do_login method directly (mocked Tk root)."""

    def _make_wizard(self):
        from src.ui.setup_wizard import SetupWizard

        mock_buffer = MagicMock()
        mock_sender = MagicMock()

        mock_info = MagicMock()
        mock_info.hostname = "TEST-PC"
        mock_info.mac_address = "aa:bb:cc:dd:ee:ff"
        mock_info.local_ip = "192.168.1.50"
        mock_info.os_name = "windows"
        mock_info.os_version = "10"

        mock_platform = MagicMock()
        mock_platform.get_system_info.return_value = mock_info

        with patch("src.platform.get_platform", return_value=mock_platform):
            wizard = SetupWizard(mock_buffer, mock_sender)

        wizard._root = MagicMock()  # Mock Tk root
        return wizard

    def test_do_login_success(self):
        wizard = self._make_wizard()

        wizard._sender.get_immediate.return_value = {"id": 1, "is_active": True}
        wizard._sender.send_immediate.side_effect = [
            # Login response
            {
                "access_token": "tok_abc",
                "full_name": "Test User",
                "employee_code": "EMP001",
            },
            # Device registration response
            {"id": 5},
        ]

        wizard._do_login("EMP001", "password", "123456")

        # Should save identity
        wizard._buffer.set_config.assert_any_call("employee_id", "1")
        wizard._buffer.set_config.assert_any_call("device_mac", "aa:bb:cc:dd:ee:ff")
        wizard._buffer.set_config.assert_any_call("employee_name", "Test User")
        wizard._buffer.set_config.assert_any_call("access_token", "tok_abc")

        # Should schedule success callback on main thread
        wizard._root.after.assert_called() # type: ignore
        call_args = wizard._root.after.call_args_list[-1] # type: ignore
        assert call_args[0][0] == 0  # schedule immediately

    def test_do_login_network_error(self):
        wizard = self._make_wizard()

        wizard._sender.get_immediate.return_value = None  # Network failure

        wizard._do_login("EMP001", "password", "123456")

        # Should schedule error callback
        wizard._root.after.assert_called() # type: ignore
        call_args = wizard._root.after.call_args_list[-1] # type: ignore
        assert call_args[0][0] == 0
        # Error message should mention server/network
        error_msg = call_args[0][2]
        assert "server" in error_msg.lower() or "network" in error_msg.lower()

    def test_do_login_employee_inactive(self):
        wizard = self._make_wizard()

        wizard._sender.get_immediate.return_value = {"id": 1, "is_active": False}

        wizard._do_login("EMP001", "password", "123456")

        wizard._root.after.assert_called() # type: ignore
        call_args = wizard._root.after.call_args_list[-1] # type: ignore
        error_msg = call_args[0][2]
        assert "inactive" in error_msg.lower()

    def test_do_login_invalid_credentials(self):
        wizard = self._make_wizard()

        wizard._sender.get_immediate.return_value = {"id": 1, "is_active": True}
        wizard._sender.send_immediate.return_value = {
            "detail": "Invalid password"
        }

        wizard._do_login("EMP001", "wrong", "123456")

        wizard._root.after.assert_called() # type: ignore
        call_args = wizard._root.after.call_args_list[-1] # type: ignore
        error_msg = call_args[0][2]
        assert "Invalid password" in error_msg

    def test_do_login_device_registration_failure_still_succeeds(self):
        """Device reg failure should not prevent setup completion."""
        wizard = self._make_wizard()

        wizard._sender.get_immediate.return_value = {"id": 1, "is_active": True}
        wizard._sender.send_immediate.side_effect = [
            {"access_token": "tok", "full_name": "User"},  # Login OK
            None,  # Device registration fails
        ]

        wizard._do_login("EMP001", "pass", "123456")

        # Should still save identity and call success
        wizard._buffer.set_config.assert_any_call("employee_id", "1")
        # Last after() call should be success, not error
        last_call = wizard._root.after.call_args_list[-1] # type: ignore
        callback = last_call[0][1]
        assert callback == wizard._on_login_success


# ============================================================
# Agent core GUI fallback tests
# ============================================================

class TestAgentCoreGUIFallback:
    """Test _ensure_configured GUI vs CLI selection."""

    def _make_agent(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        agent._buffer = MagicMock()
        agent._sender = MagicMock()

        mock_sm = MagicMock()
        mock_sm.is_configured = False
        agent._session_manager = mock_sm

        return agent

    def test_cli_used_when_terminal_available(self):
        agent = self._make_agent()

        new_sm = MagicMock()
        new_sm.is_configured = True

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch("sys.stdin", mock_stdin), \
             patch("src.agent_core.run_first_launch", return_value=True) as mock_cli, \
             patch("src.agent_core.SessionManager", return_value=new_sm), \
             patch("src.agent_core.register_autostart", return_value=False):
            result = agent._ensure_configured()

        assert result is True
        mock_cli.assert_called_once_with(agent._buffer, agent._sender)

    def test_gui_wizard_when_no_terminal(self):
        agent = self._make_agent()

        new_sm = MagicMock()
        new_sm.is_configured = True

        with patch("sys.stdin", None), \
             patch("src.ui.setup_wizard.is_tk_available", return_value=True), \
             patch("src.ui.setup_wizard.run_setup_wizard", return_value=True) as mock_wiz, \
             patch("src.agent_core.SessionManager", return_value=new_sm):
            result = agent._ensure_configured()

        assert result is True
        mock_wiz.assert_called_once_with(agent._buffer, agent._sender)

    def test_fails_when_no_terminal_no_gui(self):
        agent = self._make_agent()

        with patch("sys.stdin", None), \
             patch("src.ui.setup_wizard.is_tk_available", return_value=False):
            result = agent._ensure_configured()

        assert result is False

    def test_gui_wizard_failure_returns_false(self):
        agent = self._make_agent()

        with patch("sys.stdin", None), \
             patch("src.ui.setup_wizard.is_tk_available", return_value=True), \
             patch("src.ui.setup_wizard.run_setup_wizard", return_value=False):
            result = agent._ensure_configured()

        assert result is False

    def test_cli_autostart_registered_on_success(self):
        agent = self._make_agent()

        new_sm = MagicMock()
        new_sm.is_configured = True

        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True

        with patch("sys.stdin", mock_stdin), \
             patch("src.agent_core.run_first_launch", return_value=True), \
             patch("src.agent_core.SessionManager", return_value=new_sm), \
             patch("src.agent_core.register_autostart", return_value=True) as mock_auto:
            agent._ensure_configured()

        mock_auto.assert_called_once()

    def test_gui_does_not_call_register_autostart(self):
        """GUI wizard handles auto-start via checkbox, agent core should not."""
        agent = self._make_agent()

        new_sm = MagicMock()
        new_sm.is_configured = True

        with patch("sys.stdin", None), \
             patch("src.ui.setup_wizard.is_tk_available", return_value=True), \
             patch("src.ui.setup_wizard.run_setup_wizard", return_value=True), \
             patch("src.agent_core.SessionManager", return_value=new_sm), \
             patch("src.agent_core.register_autostart") as mock_auto:
            agent._ensure_configured()

        mock_auto.assert_not_called()


# ============================================================
# Status dict employee_name tests
# ============================================================

class TestStatusEmployeeName:
    """Test that get_status includes employee_name from buffer."""

    def test_status_includes_employee_name(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        agent._buffer = MagicMock()
        agent._buffer.get_config.return_value = "Rahul Shah"
        agent._buffer.get_pending_count.return_value = 0
        agent._buffer.get_stats.return_value = {}
        agent._buffer.db_size_mb = 1.5

        agent._session_manager = MagicMock()
        agent._session_manager.get_status.return_value = {"running": True}

        agent._sender = MagicMock()
        agent._sender.get_status.return_value = {"running": True}

        agent._tray = MagicMock()
        agent._tray.is_running = True
        agent._tray.is_paused = False

        agent._running = True

        status = agent.get_status()
        assert status["employee_name"] == "Rahul Shah"

    def test_status_employee_name_default(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        agent._buffer = MagicMock()
        agent._buffer.get_config.return_value = "Unknown"
        agent._buffer.get_pending_count.return_value = 0
        agent._buffer.get_stats.return_value = {}
        agent._buffer.db_size_mb = 0.1

        status = agent.get_status()
        assert status["employee_name"] == "Unknown"


# ============================================================
# Tray employee text tests
# ============================================================

class TestTrayEmployeeText:
    """Test tray menu employee text generation."""

    def test_employee_text_with_name_and_id(self):
        from src.ui.tray import SystemTray

        status = {
            "employee_name": "Rahul Shah",
            "session": {"employee_id": 6},
        }
        tray = SystemTray(get_status_fn=lambda: status, stop_fn=lambda: None)

        text = tray._employee_text(None)
        assert "Rahul Shah" in text
        assert "6" in text

    def test_employee_text_missing_name(self):
        from src.ui.tray import SystemTray

        status = {
            "session": {"employee_id": 6},
        }
        tray = SystemTray(get_status_fn=lambda: status, stop_fn=lambda: None)

        text = tray._employee_text(None)
        assert "Unknown" in text
        assert "6" in text

    def test_employee_text_exception_fallback(self):
        from src.ui.tray import SystemTray

        def bad_status():
            raise RuntimeError("oops")

        tray = SystemTray(get_status_fn=bad_status, stop_fn=lambda: None)

        text = tray._employee_text(None)
        assert "Unknown" in text

    def test_employee_text_no_session(self):
        from src.ui.tray import SystemTray

        status = {"employee_name": "Test User"}
        tray = SystemTray(get_status_fn=lambda: status, stop_fn=lambda: None)

        text = tray._employee_text(None)
        assert "Test User" in text
        assert "?" in text  # employee_id defaults to "?"
