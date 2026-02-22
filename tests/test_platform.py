"""
Tests for the platform abstraction layer.
Run with: python -m pytest tests/test_platform.py -v
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from src.platform.base import ForegroundAppInfo, NetworkConnection, SystemInfo
from src.platform import get_platform


class TestPlatformFactory:
    """Test that the factory returns the correct platform."""

    def test_returns_platform_instance(self):
        platform = get_platform()
        assert platform is not None

    def test_returns_singleton(self):
        p1 = get_platform()
        p2 = get_platform()
        assert p1 is p2


class TestCurrentPlatform:
    """Test platform methods on the current OS (integration tests)."""

    @pytest.fixture
    def platform(self):
        return get_platform()

    def test_get_foreground_app(self, platform):
        result = platform.get_foreground_app()
        # Can be None if no window focused (e.g., in CI)
        if result is not None:
            assert isinstance(result, ForegroundAppInfo)
            assert len(result.app_name) > 0
            assert result.process_id > 0
            assert len(result.raw_process_name) > 0

    def test_get_idle_duration(self, platform):
        idle = platform.get_idle_duration_sec()
        assert isinstance(idle, float)
        assert idle >= 0.0

    def test_is_user_idle(self, platform):
        result = platform.is_user_idle(threshold_sec=999999)
        assert isinstance(result, bool)

    def test_is_screen_locked(self, platform):
        result = platform.is_screen_locked()
        assert isinstance(result, bool)

    def test_get_system_info(self, platform):
        info = platform.get_system_info()
        assert isinstance(info, SystemInfo)
        assert len(info.mac_address) == 17  # "xx:xx:xx:xx:xx:xx"
        assert ":" in info.mac_address
        assert len(info.hostname) > 0
        assert len(info.local_ip) > 0
        assert info.os_name in ("windows", "macos", "linux")
        assert len(info.os_version) > 0

    def test_get_mac_address(self, platform):
        mac = platform.get_mac_address()
        assert len(mac) == 17
        assert mac.count(":") == 5

    def test_get_hostname(self, platform):
        hostname = platform.get_hostname()
        assert len(hostname) > 0
        assert hostname != "UNKNOWN"

    def test_get_local_ip(self, platform):
        ip = platform.get_local_ip()
        assert len(ip) > 0
        parts = ip.split(".")
        assert len(parts) == 4

    def test_get_active_connections(self, platform):
        connections = platform.get_active_connections()
        assert isinstance(connections, list)
        for conn in connections:
            assert isinstance(conn, NetworkConnection)
            assert conn.pid > 0
            assert len(conn.remote_ip) > 0
            assert conn.remote_port in (80, 443, 8080, 8443)
            assert conn.status == "ESTABLISHED"

    def test_normalize_app_name(self, platform):
        # Common across all platforms
        assert platform.normalize_app_name("") == "unknown"
        assert platform.normalize_app_name(None) == "unknown"

        # Platform-specific normalization
        if sys.platform == "win32":
            assert platform.normalize_app_name("chrome.exe") == "Chrome"
            assert platform.normalize_app_name("code.exe") == "VSCode"
            assert platform.normalize_app_name("NOTEPAD.EXE") == "Notepad"
        elif sys.platform == "darwin":
            assert platform.normalize_app_name("Google Chrome") == "Chrome"
            assert platform.normalize_app_name("Code") == "VSCode"
        elif sys.platform.startswith("linux"):
            assert platform.normalize_app_name("google-chrome") == "Chrome"
            assert platform.normalize_app_name("code") == "VSCode"


class TestDataClasses:
    """Test data class instantiation."""

    def test_foreground_app_info(self):
        info = ForegroundAppInfo(
            app_name="Chrome",
            process_id=12345,
            raw_process_name="chrome.exe",
        )
        assert info.app_name == "Chrome"
        assert info.process_id == 12345

    def test_network_connection(self):
        conn = NetworkConnection(
            pid=12345,
            process_name="Chrome",
            remote_ip="140.82.121.4",
            remote_port=443,
            status="ESTABLISHED",
            family="ipv4",
        )
        assert conn.remote_port == 443

    def test_system_info(self):
        info = SystemInfo(
            mac_address="58:1c:f8:f4:c3:d8",
            hostname="LAPTOP-HOME",
            local_ip="192.168.1.100",
            os_name="windows",
            os_version="10.0.19045",
        )
        assert info.os_name == "windows"