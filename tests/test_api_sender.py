"""
Tests for the API Sender.
Run with: python -m pytest tests/test_api_sender.py -v
"""

import time
import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

import responses

from src.network.api_sender import APISender, ENDPOINTS
from src.storage.sqlite_buffer import SQLiteBuffer
from src.config import config


@pytest.fixture
def buffer(tmp_path):
    """Create a fresh SQLite buffer."""
    db_path = tmp_path / "test_sender.db"
    buf = SQLiteBuffer(db_path=db_path)
    yield buf
    buf.close()


@pytest.fixture
def sender(buffer):
    """Create an API sender."""
    s = APISender(buffer)
    yield s
    if s.is_running:
        s.stop()


@pytest.fixture
def base_url():
    return config.API_BASE_URL.rstrip("/")


class TestSenderInit:
    """Test sender initialization."""

    def test_creates_successfully(self, sender):
        assert sender is not None
        assert not sender.is_running

    def test_endpoints_defined(self):
        assert "pending_sessions" in ENDPOINTS
        assert "pending_app_usage" in ENDPOINTS
        assert "pending_domain_visits" in ENDPOINTS


class TestSenderLifecycle:
    """Test start/stop lifecycle."""

    def test_start_stop(self, sender):
        sender.start()
        assert sender.is_running
        time.sleep(0.5)
        sender.stop()
        assert not sender.is_running

    def test_double_start_safe(self, sender):
        sender.start()
        sender.start()
        assert sender.is_running
        sender.stop()

    def test_stop_without_start_safe(self, sender):
        sender.stop()  # Should not crash


class TestSendImmediate:
    """Test immediate (non-buffered) sending."""

    @responses.activate
    def test_send_immediate_success(self, sender, base_url):
        responses.add(
            responses.POST,
            f"{base_url}/api/v1/auth/verify",
            json={"valid": True, "employee_id": 1},
            status=200,
        )

        result = sender.send_immediate(
            "/api/v1/auth/verify",
            {"employee_id": 1, "totp_code": "123456"},
        )

        assert result is not None
        assert result["valid"] is True
        assert result["employee_id"] == 1

    @responses.activate
    def test_send_immediate_failure(self, sender, base_url):
        responses.add(
            responses.POST,
            f"{base_url}/api/v1/auth/verify",
            json={"valid": False},
            status=401,
        )

        result = sender.send_immediate(
            "/api/v1/auth/verify",
            {"employee_id": 1, "totp_code": "000000"},
        )

        assert result is None

    @responses.activate
    def test_send_immediate_server_error(self, sender, base_url):
        responses.add(
            responses.POST,
            f"{base_url}/api/v1/test",
            json={"error": "internal"},
            status=500,
        )

        result = sender.send_immediate("/api/v1/test", {"data": "test"})
        assert result is None

    def test_send_immediate_connection_error(self, sender):
        # Use a definitely-unreachable URL
        sender._base_url = "https://192.0.2.1"
        sender._session.headers.update(config.api_headers)

        result = sender.send_immediate("/api/v1/test", {"data": "test"})
        assert result is None


class TestGetImmediate:
    """Test immediate GET requests."""

    @responses.activate
    def test_get_immediate_success(self, sender, base_url):
        responses.add(
            responses.GET,
            f"{base_url}/api/v1/config/categories",
            json={"version": 2, "apps": {}},
            status=200,
        )

        result = sender.get_immediate("/api/v1/config/categories")
        assert result is not None
        assert result["version"] == 2

    @responses.activate
    def test_get_immediate_not_found(self, sender, base_url):
        responses.add(
            responses.GET,
            f"{base_url}/api/v1/nonexistent",
            status=404,
        )

        result = sender.get_immediate("/api/v1/nonexistent")
        assert result is None


class TestBufferedSending:
    """Test sending buffered records."""

    @responses.activate
    def test_sends_pending_session(self, sender, buffer, base_url):
        # Buffer a session record
        payload = {
            "employee_id": 1,
            "device_mac": "aa:bb:cc:dd:ee:ff",
            "session_start": "2026-02-18T09:00:00Z",
            "session_end": None,
            "active_duration_sec": 0,
            "idle_duration_sec": 0,
            "bytes_uploaded": 0,
            "bytes_downloaded": 0,
            "avg_bandwidth_kbps": 0.0,
            "source": "local_agent",
        }
        buffer.insert_pending("pending_sessions", payload)

        # Mock the API endpoint
        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"id": 1, "status": "created"},
            status=201,
        )

        # Patch network check
        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        # Record should be marked as sent
        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 0
        assert sender._total_sent == 1

    @responses.activate
    def test_sends_pending_app_usage(self, sender, buffer, base_url):
        payload = {
            "employee_id": 1,
            "device_mac": "aa:bb:cc:dd:ee:ff",
            "recorded_at": "2026-02-18T09:05:00Z",
            "apps": [
                {
                    "app_name": "VSCode",
                    "process_id": 12345,
                    "active_duration_sec": 240,
                    "idle_duration_sec": 60,
                    "switch_count": 8,
                }
            ],
        }
        buffer.insert_pending("pending_app_usage", payload)

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/app-usage",
            json={"message": "1 app usage records saved"},
            status=200,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        pending = buffer.get_pending("pending_app_usage")
        assert len(pending) == 0

    @responses.activate
    def test_sends_pending_domain_visit(self, sender, buffer, base_url):
        payload = {
            "employee_id": 1,
            "device_mac": "aa:bb:cc:dd:ee:ff",
            "app_name": "Chrome",
            "domain": "github.com",
            "category": "productivity",
            "bytes_uploaded": 50000,
            "bytes_downloaded": 200000,
            "duration_sec": 600,
            "visited_at": "2026-02-18T09:10:00Z",
        }
        buffer.insert_pending("pending_domain_visits", payload)

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/domain-visits",
            json={"id": 1},
            status=201,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        pending = buffer.get_pending("pending_domain_visits")
        assert len(pending) == 0


class TestErrorHandling:
    """Test response error handling."""

    @responses.activate
    def test_400_marks_permanently_failed(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"bad": "data"})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"error": "validation failed"},
            status=400,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        # Should not be pending anymore
        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 0

        # Should be permanently failed (not retryable)
        retryable = buffer.get_retryable("pending_sessions")
        assert len(retryable) == 0

    @responses.activate
    def test_500_marks_failed_for_retry(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"test": True})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"error": "internal server error"},
            status=500,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        # Should not be in pending (status changed to failed)
        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 0

        # Should be retryable after backoff
        # Manually set last_retry_at to past
        buffer._conn.execute(
            "UPDATE pending_sessions SET last_retry_at = ?",
            (time.time() - 99999,),
        )
        buffer._conn.commit()

        retryable = buffer.get_retryable("pending_sessions")
        assert len(retryable) == 1

    @responses.activate
    def test_404_marks_permanently_failed(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"test": True})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            status=404,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 0

        retryable = buffer.get_retryable("pending_sessions")
        assert len(retryable) == 0

    @responses.activate
    def test_429_rate_limited(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"test": True})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"error": "rate limited"},
            status=429,
            headers={"Retry-After": "30"},
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        assert sender._last_error is not None
        assert "Rate limited" in sender._last_error


class TestNetworkDetection:
    """Test network availability checks."""

    def test_network_check_returns_bool(self, sender):
        result = sender._is_network_available()
        assert isinstance(result, bool)

    def test_skips_send_when_offline(self, sender, buffer):
        buffer.insert_pending("pending_sessions", {"test": True})

        with patch.object(sender, "_is_network_available", return_value=False):
            sender._send_all_pending()

        # Record should still be pending (not attempted)
        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 1


class TestMultipleRecords:
    """Test sending multiple records."""

    @responses.activate
    def test_sends_multiple_records(self, sender, buffer, base_url):
        for i in range(5):
            buffer.insert_pending("pending_sessions", {"i": i})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"status": "ok"},
            status=200,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        pending = buffer.get_pending("pending_sessions")
        assert len(pending) == 0
        assert sender._total_sent == 5

    @responses.activate
    def test_sends_across_tables(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"type": "session"})
        buffer.insert_pending("pending_app_usage", {"type": "app"})
        buffer.insert_pending("pending_domain_visits", {"type": "domain"})

        for endpoint in ENDPOINTS.values():
            responses.add(
                responses.POST,
                f"{base_url}{endpoint}",
                json={"status": "ok"},
                status=200,
            )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        assert buffer.get_pending_count() == 0
        assert sender._total_sent == 3


class TestStatus:
    """Test status reporting."""

    def test_status_structure(self, sender):
        status = sender.get_status()
        assert "running" in status
        assert "total_sent" in status
        assert "total_failed" in status
        assert "last_send_time" in status
        assert "last_error" in status
        assert "consecutive_failures" in status
        assert "network_available" in status
        assert "pending_count" in status

    def test_initial_status(self, sender):
        status = sender.get_status()
        assert status["running"] is False
        assert status["total_sent"] == 0
        assert status["total_failed"] == 0
        assert status["last_send_time"] is None
        assert status["last_error"] is None
        assert status["consecutive_failures"] == 0


class TestForceSend:
    """Test manual force send."""

    @responses.activate
    def test_force_send(self, sender, buffer, base_url):
        buffer.insert_pending("pending_sessions", {"force": True})

        responses.add(
            responses.POST,
            f"{base_url}/api/v1/telemetry/sessions",
            json={"status": "ok"},
            status=200,
        )

        with patch.object(sender, "_is_network_available", return_value=True):
            sender.force_send()

        assert buffer.get_pending_count() == 0
        assert sender._total_sent == 1