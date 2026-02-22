"""
Tests for the Application Activity Collector.
Run with: python -m pytest tests/test_app_collector.py -v
"""

import time
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.collectors.app_collector import AppCollector, AppRecord
from src.platform.base import ForegroundAppInfo


class TestAppRecord:
    """Test the AppRecord data class."""

    def test_default_values(self):
        record = AppRecord(app_name="Chrome", process_id=1234)
        assert record.app_name == "Chrome"
        assert record.process_id == 1234
        assert record.active_duration_sec == 0.0
        assert record.idle_duration_sec == 0.0
        assert record.switch_count == 0

    def test_to_dict(self):
        record = AppRecord(
            app_name="VSCode",
            process_id=5678,
            active_duration_sec=120.7,
            idle_duration_sec=30.3,
            switch_count=5,
        )
        d = record.to_dict()
        assert d["app_name"] == "VSCode"
        assert d["process_id"] == 5678
        assert d["active_duration_sec"] == 121  # rounded
        assert d["idle_duration_sec"] == 30  # rounded
        assert d["switch_count"] == 5

    def test_to_dict_has_all_required_fields(self):
        record = AppRecord(app_name="Test", process_id=1)
        d = record.to_dict()
        required = {"app_name", "process_id", "active_duration_sec", "idle_duration_sec", "switch_count"}
        assert set(d.keys()) == required


class TestAppCollectorInit:
    """Test collector initialization."""

    def test_creates_successfully(self):
        collector = AppCollector()
        assert collector is not None
        assert not collector.is_running
        assert collector.current_app_count == 0

    def test_loads_ignored_apps(self):
        collector = AppCollector()
        assert len(collector._ignored_apps) > 0
        assert "explorer" in collector._ignored_apps or "explorer.exe" in collector._ignored_apps


class TestAppCollectorPolling:
    """Test the polling and accumulation logic."""

    @pytest.fixture
    def collector(self):
        c = AppCollector()
        yield c
        if c.is_running:
            c.stop()

    def test_start_stop(self, collector):
        collector.start()
        assert collector.is_running
        time.sleep(0.5)
        collector.stop()
        assert not collector.is_running

    def test_double_start_safe(self, collector):
        collector.start()
        collector.start()  # Should not crash
        assert collector.is_running
        collector.stop()

    def test_flush_returns_list(self, collector):
        result = collector.flush()
        assert isinstance(result, list)

    def test_flush_empty_when_no_data(self, collector):
        result = collector.flush()
        assert result == []

    def test_flush_clears_accumulator(self, collector):
        # Manually inject a record
        collector._apps["TestApp"] = AppRecord(
            app_name="TestApp",
            process_id=999,
            active_duration_sec=60,
            idle_duration_sec=10,
            switch_count=3,
            first_seen=time.time(),
            last_seen=time.time(),
        )
        assert collector.current_app_count == 1

        result = collector.flush()
        assert len(result) == 1
        assert result[0]["app_name"] == "TestApp"

        # Second flush should be empty
        result2 = collector.flush()
        assert result2 == []
        assert collector.current_app_count == 0

    def test_flush_filters_short_focus(self, collector):
        # Record with less than MIN_FOCUS_DURATION total time
        collector._apps["FlashApp"] = AppRecord(
            app_name="FlashApp",
            process_id=111,
            active_duration_sec=0.5,
            idle_duration_sec=0.0,
            switch_count=1,
        )
        result = collector.flush()
        assert len(result) == 0  # Should be filtered out

    def test_collects_real_data(self, collector):
        """Integration test: run collector briefly, expect some data."""
        collector.start()
        time.sleep(3.5)  # Collect for ~3 seconds
        collector.stop()

        result = collector.flush()
        # Should have at least one app (the terminal/IDE running this test)
        # Could be empty if all foreground apps are in ignored list
        assert isinstance(result, list)
        if len(result) > 0:
            record = result[0]
            assert "app_name" in record
            assert "process_id" in record
            assert "active_duration_sec" in record
            assert record["active_duration_sec"] >= 0


class TestAppCollectorIgnored:
    """Test the ignored apps filtering."""

    def test_ignored_system_app(self):
        collector = AppCollector()
        fg = ForegroundAppInfo(
            app_name="Explorer",
            process_id=100,
            raw_process_name="explorer.exe",
        )
        assert collector._is_ignored(fg) is True

    def test_not_ignored_regular_app(self):
        collector = AppCollector()
        fg = ForegroundAppInfo(
            app_name="Chrome",
            process_id=200,
            raw_process_name="chrome.exe",
        )
        assert collector._is_ignored(fg) is False

    