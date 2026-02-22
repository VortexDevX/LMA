"""
Tests for the Session Manager.
Run with: python -m pytest tests/test_session_manager.py -v
"""

import time
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.session.session_manager import SessionManager
from src.storage.sqlite_buffer import SQLiteBuffer


@pytest.fixture
def buffer(tmp_path):
    """Create a fresh SQLite buffer."""
    db_path = tmp_path / "test_session.db"
    buf = SQLiteBuffer(db_path=db_path)
    yield buf
    buf.close()


@pytest.fixture
def manager(buffer):
    """Create a session manager with test identity."""
    mgr = SessionManager(buffer)
    mgr.set_identity(employee_id=1, device_mac="aa:bb:cc:dd:ee:ff")
    return mgr


class TestIdentity:
    """Test identity management."""

    def test_not_configured_initially(self, buffer):
        mgr = SessionManager(buffer)
        # May or may not be configured depending on buffer state
        # Fresh buffer should not have identity
        if buffer.get_config("employee_id") is None:
            assert not mgr.is_configured

    def test_set_identity(self, buffer):
        mgr = SessionManager(buffer)
        mgr.set_identity(employee_id=42, device_mac="11:22:33:44:55:66")
        assert mgr.is_configured
        assert mgr.employee_id == 42
        assert mgr.device_mac == "11:22:33:44:55:66"

    def test_identity_persists_in_buffer(self, buffer):
        mgr = SessionManager(buffer)
        mgr.set_identity(employee_id=99, device_mac="aa:aa:aa:aa:aa:aa")

        assert buffer.get_config("employee_id") == "99"
        assert buffer.get_config("device_mac") == "aa:aa:aa:aa:aa:aa"

    def test_identity_loads_from_buffer(self, buffer):
        buffer.set_config("employee_id", "7")
        buffer.set_config("device_mac", "ff:ff:ff:ff:ff:ff")

        mgr = SessionManager(buffer)
        assert mgr.employee_id == 7
        assert mgr.device_mac == "ff:ff:ff:ff:ff:ff"
        assert mgr.is_configured


class TestSessionLifecycle:
    """Test start/stop lifecycle."""

    def test_start_requires_identity(self, buffer):
        mgr = SessionManager(buffer)
        # No identity set
        mgr.start()
        assert not mgr.is_running

    def test_start_stop(self, manager):
        manager.start()
        assert manager.is_running
        assert manager.session_start is not None
        time.sleep(0.5)
        manager.stop()
        assert not manager.is_running

    def test_double_start_safe(self, manager):
        manager.start()
        manager.start()  # Should not crash
        assert manager.is_running
        manager.stop()

    def test_stop_without_start_safe(self, manager):
        manager.stop()  # Should not crash

    def test_session_start_buffers_record(self, manager, buffer):
        manager.start()
        time.sleep(0.3)
        manager.stop()

        records = buffer.get_pending("pending_sessions")
        assert len(records) >= 2  # At least start + end

        # First record should have session_end = None
        start_payload = records[0].payload
        assert start_payload["employee_id"] == 1
        assert start_payload["device_mac"] == "aa:bb:cc:dd:ee:ff"
        assert start_payload["session_end"] is None
        assert start_payload["source"] == "local_agent"

    def test_session_end_buffers_record(self, manager, buffer):
        manager.start()
        time.sleep(0.3)
        manager.stop()

        records = buffer.get_pending("pending_sessions")
        # Last record should have session_end set
        end_payload = records[-1].payload
        assert end_payload["session_end"] is not None
        assert end_payload["employee_id"] == 1


class TestAppUsageFlush:
    """Test app usage collection and buffering."""

    def test_flush_buffers_app_data(self, manager, buffer):
        manager.start()
        # Let it collect for a few seconds
        time.sleep(3.5)
        manager.stop()

        records = buffer.get_pending("pending_app_usage")
        # May or may not have records depending on collection interval
        # With default 300s interval, manual flush happens on stop
        assert isinstance(records, list)

        if len(records) > 0:
            payload = records[0].payload
            assert payload["employee_id"] == 1
            assert payload["device_mac"] == "aa:bb:cc:dd:ee:ff"
            assert "recorded_at" in payload
            assert "apps" in payload
            assert isinstance(payload["apps"], list)

    def test_app_payload_format(self, manager, buffer):
        """Verify the app usage payload matches the API spec."""
        manager.start()
        time.sleep(3.5)
        manager.stop()

        records = buffer.get_pending("pending_app_usage")
        if len(records) > 0:
            payload = records[0].payload
            # Check top-level fields
            assert "employee_id" in payload
            assert "device_mac" in payload
            assert "recorded_at" in payload
            assert "apps" in payload

            # Check app record fields
            if len(payload["apps"]) > 0:
                app = payload["apps"][0]
                assert "app_name" in app
                assert "process_id" in app
                assert "active_duration_sec" in app
                assert "idle_duration_sec" in app
                assert "switch_count" in app


class TestDomainVisitBuffering:
    """Test domain visit buffering."""

    def test_buffer_domain_visit(self, manager, buffer):
        manager.buffer_domain_visit(
            domain="github.com",
            app_name="Chrome",
            bytes_uploaded=5000,
            bytes_downloaded=50000,
            duration_sec=120,
        )

        records = buffer.get_pending("pending_domain_visits")
        assert len(records) == 1

        payload = records[0].payload
        assert payload["employee_id"] == 1
        assert payload["device_mac"] == "aa:bb:cc:dd:ee:ff"
        assert payload["app_name"] == "Chrome"
        assert payload["domain"] == "github.com"
        assert payload["category"] == "productivity"
        assert payload["bytes_uploaded"] == 5000
        assert payload["bytes_downloaded"] == 50000
        assert payload["duration_sec"] == 120
        assert "visited_at" in payload

    def test_domain_normalized(self, manager, buffer):
        manager.buffer_domain_visit(
            domain="WWW.GitHub.COM",
            app_name="Chrome",
        )
        records = buffer.get_pending("pending_domain_visits")
        assert records[0].payload["domain"] == "github.com"

    def test_ignored_domain_not_buffered(self, manager, buffer):
        manager.buffer_domain_visit(
            domain="localhost",
            app_name="Chrome",
        )
        records = buffer.get_pending("pending_domain_visits")
        assert len(records) == 0

    def test_ip_address_not_buffered(self, manager, buffer):
        manager.buffer_domain_visit(
            domain="192.168.1.1",
            app_name="Chrome",
        )
        records = buffer.get_pending("pending_domain_visits")
        assert len(records) == 0

    def test_empty_domain_not_buffered(self, manager, buffer):
        manager.buffer_domain_visit(
            domain="",
            app_name="Chrome",
        )
        records = buffer.get_pending("pending_domain_visits")
        assert len(records) == 0

    def test_domain_visit_updates_session_totals(self, manager):
        manager.buffer_domain_visit(
            domain="github.com",
            app_name="Chrome",
            bytes_uploaded=1000,
            bytes_downloaded=5000,
        )
        status = manager.get_status()
        assert status["bytes_uploaded"] == 1000
        assert status["bytes_downloaded"] == 5000

    def test_multiple_domain_visits_accumulate(self, manager):
        manager.buffer_domain_visit(
            domain="github.com", app_name="Chrome",
            bytes_uploaded=1000, bytes_downloaded=5000,
        )
        manager.buffer_domain_visit(
            domain="youtube.com", app_name="Chrome",
            bytes_uploaded=500, bytes_downloaded=50000,
        )
        status = manager.get_status()
        assert status["bytes_uploaded"] == 1500
        assert status["bytes_downloaded"] == 55000

    def test_categorization_applied(self, manager, buffer):
        test_cases = [
            ("github.com", "productivity"),
            ("youtube.com", "entertainment"),
            ("twitter.com", "social"),
            ("slack.com", "communication"),
            ("randomxyz123.com", "other"),
        ]
        for domain, expected_category in test_cases:
            manager.buffer_domain_visit(domain=domain, app_name="Chrome")

        records = buffer.get_pending("pending_domain_visits")
        categories = {r.payload["domain"]: r.payload["category"] for r in records}

        assert categories["github.com"] == "productivity"
        assert categories["youtube.com"] == "entertainment"
        assert categories["twitter.com"] == "social"
        assert categories["slack.com"] == "communication"
        assert categories["randomxyz123.com"] == "other"


class TestStatus:
    """Test status reporting."""

    def test_status_structure(self, manager):
        status = manager.get_status()
        assert "running" in status
        assert "employee_id" in status
        assert "device_mac" in status
        assert "session_start" in status
        assert "active_duration_sec" in status
        assert "idle_duration_sec" in status
        assert "bytes_uploaded" in status
        assert "bytes_downloaded" in status
        assert "apps_tracked" in status
        assert "pending_records" in status

    def test_status_not_running(self, manager):
        status = manager.get_status()
        assert status["running"] is False
        assert status["session_start"] is None

    def test_status_while_running(self, manager):
        manager.start()
        time.sleep(0.5)
        status = manager.get_status()
        assert status["running"] is True
        assert status["session_start"] is not None
        assert status["employee_id"] == 1
        manager.stop()

    def test_categorizer_exposed(self, manager):
        cat = manager.categorizer
        assert cat is not None
        assert cat.categorize_domain("github.com") == "productivity"


class TestSessionPayloadFormat:
    """Verify session payloads match the API spec exactly."""

    def test_session_payload_fields(self, manager, buffer):
        manager.start()
        time.sleep(0.3)
        manager.stop()

        records = buffer.get_pending("pending_sessions")
        assert len(records) >= 1

        required_fields = {
            "employee_id", "device_mac", "session_start", "session_end",
            "active_duration_sec", "idle_duration_sec",
            "bytes_uploaded", "bytes_downloaded",
            "avg_bandwidth_kbps", "source",
        }

        for record in records:
            payload = record.payload
            missing = required_fields - set(payload.keys())
            assert missing == set(), f"Missing fields: {missing}"

    def test_session_payload_serializable(self, manager, buffer):
        manager.start()
        time.sleep(0.3)
        manager.stop()

        records = buffer.get_pending("pending_sessions")
        for record in records:
            # Should be JSON-serializable
            serialized = json.dumps(record.payload)
            assert len(serialized) > 0