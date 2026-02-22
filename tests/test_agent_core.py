"""
Tests for the Agent Core and First Launch.
Run with: python -m pytest tests/test_agent_core.py -v
"""

import time
import threading
import pytest  # type: ignore
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.agent_core import AgentCore
from src.storage.sqlite_buffer import SQLiteBuffer
from src.network.api_sender import APISender
from src.setup.first_launch import (
    _prompt_employee_id,
    _verify_login,
    _register_device,
    _detect_device_type,
)
from src.platform.base import SystemInfo


@pytest.fixture
def buffer(tmp_path):
    db_path = tmp_path / "test_core.db"
    buf = SQLiteBuffer(db_path=db_path)
    yield buf
    buf.close()


@pytest.fixture
def sender(buffer):
    s = APISender(buffer)
    yield s


@pytest.fixture
def system_info():
    return SystemInfo(
        mac_address="aa:bb:cc:dd:ee:ff",
        hostname="TEST-PC",
        local_ip="192.168.1.100",
        os_name="windows",
        os_version="10.0.19045",
    )


class TestAgentCoreInit:
    """Test agent core creation."""

    def test_creates_successfully(self):
        agent = AgentCore()
        assert agent is not None
        assert agent._running is False

    def test_get_status_before_init(self):
        agent = AgentCore()
        status = agent.get_status()
        assert status["running"] is False
        assert status["agent_version"] == "1.0.0"


class TestFirstLaunchPrompts:
    """Test first launch input prompts."""

    @patch("builtins.input", return_value="42")
    def test_prompt_employee_id_valid(self, mock_input):
        result = _prompt_employee_id()
        assert result == 42

    @patch("builtins.input", side_effect=["", "", ""])
    def test_prompt_employee_id_empty_retries(self, mock_input):
        result = _prompt_employee_id()
        assert result is None

    @patch("builtins.input", side_effect=["abc", "xyz", "!!!"])
    def test_prompt_employee_id_invalid_retries(self, mock_input):
        result = _prompt_employee_id()
        assert result is None

    @patch("builtins.input", side_effect=["0", "-1", "5"])
    def test_prompt_employee_id_rejects_non_positive(self, mock_input):
        result = _prompt_employee_id()
        assert result == 5

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_prompt_employee_id_keyboard_interrupt(self, mock_input):
        result = _prompt_employee_id()
        assert result is None


class TestLoginVerification:
    """Test login verification flow."""

    @patch("builtins.input", return_value="123456")
    @patch("src.setup.first_launch.getpass.getpass", return_value="password123")
    def test_verify_login_success(self, mock_getpass, mock_input, sender):
        with patch.object(
            sender,
            "send_immediate",
            return_value={
                "access_token": "tok_abc123",
                "employee_id": 1,
                "full_name": "Test User",
            },
        ):
            result = _verify_login(sender, employee_id=1)
            assert result is not None
            assert result["access_token"] == "tok_abc123"
            assert result["full_name"] == "Test User"

    @patch("builtins.input", side_effect=["000000", "000000", "000000"])
    @patch("src.setup.first_launch.getpass.getpass", return_value="wrong")
    def test_verify_login_invalid_retries(self, mock_getpass, mock_input, sender):
        with patch.object(
            sender,
            "send_immediate",
            return_value={"detail": "Invalid credentials"},
        ):
            result = _verify_login(sender, employee_id=1)
            assert result is None

    @patch("builtins.input", return_value="123456")
    @patch("src.setup.first_launch.getpass.getpass", return_value="password123")
    def test_verify_login_network_error(self, mock_getpass, mock_input, sender):
        with patch.object(sender, "send_immediate", return_value=None):
            result = _verify_login(sender, employee_id=1)
            assert result is None

    @patch("src.setup.first_launch.getpass.getpass", side_effect=KeyboardInterrupt)
    def test_verify_login_keyboard_interrupt(self, mock_getpass, sender):
        result = _verify_login(sender, employee_id=1)
        assert result is None


class TestDeviceRegistration:
    """Test device registration."""

    def test_register_device_success(self, sender, system_info):
        with patch.object(
            sender,
            "send_immediate",
            return_value={"id": 5, "mac_address": "aa:bb:cc:dd:ee:ff"},
        ):
            result = _register_device(sender, employee_id=1, system_info=system_info)
            assert result is True

    def test_register_device_failure(self, sender, system_info):
        with patch.object(sender, "send_immediate", return_value=None):
            result = _register_device(sender, employee_id=1, system_info=system_info)
            assert result is False


class TestDeviceTypeDetection:
    """Test device type detection."""

    def test_returns_string(self):
        result = _detect_device_type()
        assert result in ("laptop", "desktop")


class TestIdentityPersistence:
    """Test that setup saves identity correctly."""

    def test_identity_saved_to_buffer(self, buffer):
        buffer.set_config("employee_id", "42")
        buffer.set_config("device_mac", "aa:bb:cc:dd:ee:ff")
        buffer.set_config("employee_name", "Test User")

        assert buffer.get_config("employee_id") == "42"
        assert buffer.get_config("device_mac") == "aa:bb:cc:dd:ee:ff"
        assert buffer.get_config("employee_name") == "Test User"

    def test_session_manager_loads_identity(self, buffer):
        buffer.set_config("employee_id", "7")
        buffer.set_config("device_mac", "11:22:33:44:55:66")

        from src.session.session_manager import SessionManager

        mgr = SessionManager(buffer)
        assert mgr.is_configured
        assert mgr.employee_id == 7
        assert mgr.device_mac == "11:22:33:44:55:66"


class TestAgentCoreWithMockSetup:
    """Test agent core with pre-configured identity (skip first launch)."""

    def test_runs_with_preconfigured_identity(self, tmp_path):
        """Agent should start and stop cleanly with saved identity."""
        # Pre-configure
        db_path = tmp_path / "agent.db"
        buf = SQLiteBuffer(db_path=db_path)
        buf.set_config("employee_id", "1")
        buf.set_config("device_mac", "aa:bb:cc:dd:ee:ff")
        buf.close()

        agent = AgentCore()

        with patch.object(
            agent, "_check_single_instance"
        ), patch(
            "src.agent_core.config"
        ) as mock_config, patch(
            "src.agent_core.SQLiteBuffer"
        ) as MockBuffer, patch(
            "src.agent_core.APISender"
        ) as MockSender, patch(
            "src.agent_core.SessionManager"
        ) as MockSession:

            mock_config.LOG_DIR = tmp_path
            mock_config.LOG_LEVEL = "WARNING"
            mock_config.LOCK_FILE = tmp_path / "agent.lock"
            mock_config.AGENT_VERSION = "1.0.0"
            mock_config.API_BASE_URL = "https://test.example.com"
            mock_config.DATA_DIR = tmp_path
            mock_config.DB_PATH = db_path

            mock_buffer_instance = MagicMock()
            mock_buffer_instance.db_size_mb = 0.01
            mock_buffer_instance.get_pending_count.return_value = 0
            mock_buffer_instance.get_config.return_value = None
            mock_buffer_instance.get_stats.return_value = {}
            MockBuffer.return_value = mock_buffer_instance

            mock_sender_instance = MagicMock()
            MockSender.return_value = mock_sender_instance

            mock_session_instance = MagicMock()
            mock_session_instance.is_configured = True
            mock_session_instance.employee_id = 1
            mock_session_instance.device_mac = "aa:bb:cc:dd:ee:ff"
            MockSession.return_value = mock_session_instance

            def stop_agent():
                time.sleep(1)
                agent._running = False

            stopper = threading.Thread(target=stop_agent, daemon=True)
            stopper.start()

            exit_code = agent.run()
            stopper.join(timeout=3)

            assert exit_code == 0
            mock_session_instance.start.assert_called_once()
            mock_sender_instance.start.assert_called_once()
            mock_session_instance.stop.assert_called_once()
            mock_sender_instance.stop.assert_called_once()