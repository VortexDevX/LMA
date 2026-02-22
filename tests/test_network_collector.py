"""
Tests for the Network / Domain Collector.
Run with: python -m pytest tests/test_network_collector.py -v
"""

import time
import socket
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from src.collectors.network_collector import (
    NetworkCollector,
    DomainRecord,
    ConnectionSnapshot,
    MONITORED_PORTS,
)


class TestDomainRecord:
    """Test the DomainRecord data class."""

    def test_default_values(self):
        record = DomainRecord(domain="github.com", app_name="Chrome")
        assert record.domain == "github.com"
        assert record.app_name == "Chrome"
        assert record.connection_count == 0
        assert record.bytes_uploaded == 0
        assert record.bytes_downloaded == 0

    def test_duration_calculation(self):
        record = DomainRecord(
            domain="github.com",
            app_name="Chrome",
            first_seen=1000.0,
            last_seen=1060.0,
        )
        assert record.duration_sec == 60

    def test_duration_minimum_one(self):
        record = DomainRecord(
            domain="github.com",
            app_name="Chrome",
            first_seen=1000.0,
            last_seen=1000.5,
        )
        assert record.duration_sec == 1

    def test_duration_zero_when_not_seen(self):
        record = DomainRecord(domain="github.com", app_name="Chrome")
        assert record.duration_sec == 0

    def test_to_dict(self):
        record = DomainRecord(
            domain="github.com",
            app_name="Chrome",
            first_seen=1000.0,
            last_seen=1120.0,
            bytes_uploaded=5000,
            bytes_downloaded=50000,
        )
        d = record.to_dict()
        assert d["domain"] == "github.com"
        assert d["app_name"] == "Chrome"
        assert d["bytes_uploaded"] == 5000
        assert d["bytes_downloaded"] == 50000
        assert d["duration_sec"] == 120

    def test_to_dict_has_required_fields(self):
        record = DomainRecord(domain="test.com", app_name="Firefox")
        d = record.to_dict()
        required = {"domain", "app_name", "bytes_uploaded", "bytes_downloaded", "duration_sec"}
        assert set(d.keys()) == required


class TestConnectionSnapshot:
    """Test the ConnectionSnapshot data class."""

    def test_creation(self):
        snap = ConnectionSnapshot(
            pid=1234,
            process_name="chrome.exe",
            remote_ip="140.82.121.4",
            remote_port=443,
            protocol="tcp",
            timestamp=time.time(),
        )
        assert snap.pid == 1234
        assert snap.remote_port == 443
        assert snap.protocol == "tcp"


class TestNetworkCollectorInit:
    """Test collector initialization."""

    def test_creates_successfully(self):
        collector = NetworkCollector()
        assert collector is not None
        assert not collector.is_running
        assert collector.current_domain_count == 0

    def test_loads_ignored_domains(self):
        collector = NetworkCollector()
        assert len(collector._ignored_domains) > 0

    def test_dns_cache_populated(self):
        collector = NetworkCollector()
        # On Windows, should have some entries from system DNS cache
        # On other platforms, may be empty
        assert isinstance(collector.dns_cache_size, int)


class TestNetworkCollectorLifecycle:
    """Test start/stop lifecycle."""

    def test_start_stop(self):
        collector = NetworkCollector()
        collector.start()
        assert collector.is_running
        time.sleep(1)
        collector.stop()
        assert not collector.is_running

    def test_double_start_safe(self):
        collector = NetworkCollector()
        collector.start()
        collector.start()
        assert collector.is_running
        collector.stop()

    def test_flush_returns_list(self):
        collector = NetworkCollector()
        result = collector.flush()
        assert isinstance(result, list)

    def test_flush_empty_when_no_data(self):
        collector = NetworkCollector()
        result = collector.flush()
        assert result == []


class TestDomainNormalization:
    """Test domain normalization."""

    def test_strips_www(self):
        collector = NetworkCollector()
        assert collector._normalize_domain("www.github.com") == "github.com"

    def test_lowercase(self):
        collector = NetworkCollector()
        assert collector._normalize_domain("GitHub.COM") == "github.com"

    def test_strips_trailing_dot(self):
        collector = NetworkCollector()
        assert collector._normalize_domain("github.com.") == "github.com"

    def test_empty_returns_empty(self):
        collector = NetworkCollector()
        assert collector._normalize_domain("") == ""


class TestDomainFiltering:
    """Test domain ignore logic."""

    def test_ignores_localhost(self):
        collector = NetworkCollector()
        assert collector._is_ignored("localhost") is True

    def test_ignores_ip_addresses(self):
        collector = NetworkCollector()
        assert collector._is_ignored("192.168.1.1") is True
        assert collector._is_ignored("10.0.0.1") is True

    def test_ignores_wildcard_patterns(self):
        collector = NetworkCollector()
        assert collector._is_ignored("mypc.local") is True
        assert collector._is_ignored("printer.internal") is True

    def test_does_not_ignore_regular_domains(self):
        collector = NetworkCollector()
        assert collector._is_ignored("github.com") is False
        assert collector._is_ignored("google.com") is False

    def test_ignores_empty(self):
        collector = NetworkCollector()
        assert collector._is_ignored("") is True

    def test_ignores_system_domains(self):
        collector = NetworkCollector()
        assert collector._is_ignored("ocsp.digicert.com") is True
        assert collector._is_ignored("connectivitycheck.gstatic.com") is True


class TestIPDetection:
    """Test IP address detection."""

    def test_ipv4_detected(self):
        assert NetworkCollector._is_ip_like("192.168.1.1") is True
        assert NetworkCollector._is_ip_like("10.0.0.1") is True
        assert NetworkCollector._is_ip_like("255.255.255.255") is True

    def test_domain_not_ip(self):
        assert NetworkCollector._is_ip_like("github.com") is False
        assert NetworkCollector._is_ip_like("docs.google.com") is False

    def test_ipv6_detected(self):
        assert NetworkCollector._is_ip_like("::1") is True
        assert NetworkCollector._is_ip_like("fe80::1") is True

    def test_edge_cases(self):
        assert NetworkCollector._is_ip_like("") is False
        assert NetworkCollector._is_ip_like("999.999.999.999") is False


class TestDNSResolution:
    """Test DNS resolution and caching."""

    def test_cache_miss_returns_none_for_invalid(self):
        collector = NetworkCollector()
        # RFC 5737 TEST-NET, should not resolve
        result = collector._resolve_ip("192.0.2.1")
        # May or may not resolve depending on DNS config
        assert result is None or isinstance(result, str)

    def test_cache_stores_results(self):
        collector = NetworkCollector()
        collector._dns_cache["1.2.3.4"] = "example.com"
        collector._dns_cache_ttl["1.2.3.4"] = time.time()

        result = collector._resolve_ip("1.2.3.4")
        assert result == "example.com"

    def test_cache_stores_misses(self):
        collector = NetworkCollector()
        # Resolve something that will fail
        collector._resolve_ip("192.0.2.1")
        # Should be cached as empty string
        assert "192.0.2.1" in collector._dns_cache

    def test_cache_expires(self):
        collector = NetworkCollector()
        collector._dns_cache["5.6.7.8"] = "old.example.com"
        collector._dns_cache_ttl["5.6.7.8"] = time.time() - 9999  # Expired

        # Should try to resolve again (cache expired)
        # Result depends on actual DNS
        result = collector._resolve_ip("5.6.7.8")
        # Just verify it doesn't crash
        assert result is None or isinstance(result, str)


class TestConnectionSnapshots:
    """Test connection snapshot gathering."""

    def test_get_snapshots_returns_list(self):
        collector = NetworkCollector()
        snapshots = collector._get_connection_snapshots()
        assert isinstance(snapshots, list)

    def test_snapshots_have_correct_ports(self):
        collector = NetworkCollector()
        snapshots = collector._get_connection_snapshots()
        for snap in snapshots:
            assert snap.remote_port in MONITORED_PORTS

    def test_snapshots_have_valid_fields(self):
        collector = NetworkCollector()
        snapshots = collector._get_connection_snapshots()
        for snap in snapshots:
            assert isinstance(snap, ConnectionSnapshot)
            assert snap.pid > 0
            assert len(snap.remote_ip) > 0
            assert snap.timestamp > 0


class TestConnectionSnapshotFiltering:
    """Test protocol/status filtering for snapshots."""

    def test_includes_established_tcp_and_udp_quic(self):
        collector = NetworkCollector()

        tcp_conn = SimpleNamespace(
            status="ESTABLISHED",
            type=socket.SOCK_STREAM,
            raddr=SimpleNamespace(ip="1.1.1.1", port=443),
            pid=111,
        )
        udp_conn = SimpleNamespace(
            status="NONE",
            type=socket.SOCK_DGRAM,
            raddr=SimpleNamespace(ip="8.8.8.8", port=443),
            pid=222,
        )
        tcp_not_established = SimpleNamespace(
            status="LISTEN",
            type=socket.SOCK_STREAM,
            raddr=SimpleNamespace(ip="9.9.9.9", port=443),
            pid=333,
        )
        udp_unmonitored = SimpleNamespace(
            status="NONE",
            type=socket.SOCK_DGRAM,
            raddr=SimpleNamespace(ip="4.4.4.4", port=53),
            pid=444,
        )

        with patch("src.collectors.network_collector.psutil.net_connections") as mock_net:
            mock_net.return_value = [
                tcp_conn,
                udp_conn,
                tcp_not_established,
                udp_unmonitored,
            ]
            with patch.object(collector._platform, "get_process_name", return_value="chrome.exe"):
                snapshots = collector._get_connection_snapshots()

        assert len(snapshots) == 2
        ips = {s.remote_ip for s in snapshots}
        protocols = {s.protocol for s in snapshots}
        assert ips == {"1.1.1.1", "8.8.8.8"}
        assert protocols == {"tcp", "udp"}


class TestDNSCacheRefresh:
    """Test periodic DNS cache refresh behavior on Windows."""

    def test_refreshes_dns_cache_when_interval_elapsed(self):
        collector = NetworkCollector()
        collector._last_dns_cache_refresh_time = 0
        now = collector._dns_cache_refresh_interval + 10

        with patch("src.collectors.network_collector.sys.platform", "win32"):
            with patch.object(collector, "_load_windows_dns_cache") as mock_load:
                collector._refresh_dns_cache_if_needed(now=now)

        mock_load.assert_called_once()


class TestBandwidthTracking:
    """Test bandwidth delta calculation."""

    def test_initial_delta_zero(self):
        collector = NetworkCollector()
        collector._last_io_counters = None
        up, down = collector._calculate_bandwidth_delta()
        assert up == 0
        assert down == 0

    def test_delta_calculation(self):
        collector = NetworkCollector()
        collector._last_io_counters = (1000, 5000)
        collector._last_io_time = time.time() - 5

        with patch("src.collectors.network_collector.psutil") as mock_psutil:
            mock_counters = MagicMock()
            mock_counters.bytes_sent = 2000
            mock_counters.bytes_recv = 8000
            mock_psutil.net_io_counters.return_value = mock_counters

            up, down = collector._calculate_bandwidth_delta()
            assert up == 1000
            assert down == 3000

    def test_distribute_bandwidth(self):
        collector = NetworkCollector()
        collector._domains["github.com"] = DomainRecord(
            domain="github.com",
            app_name="Chrome",
            connection_count=3,
        )
        collector._domains["youtube.com"] = DomainRecord(
            domain="youtube.com",
            app_name="Chrome",
            connection_count=1,
        )

        collector._distribute_bandwidth(4000, 8000)

        github = collector._domains["github.com"]
        youtube = collector._domains["youtube.com"]

        # github has 3/4 of connections, youtube has 1/4
        assert github.bytes_uploaded == 3000
        assert github.bytes_downloaded == 6000
        assert youtube.bytes_uploaded == 1000
        assert youtube.bytes_downloaded == 2000

    def test_distribute_bandwidth_no_domains(self):
        collector = NetworkCollector()
        # Should not crash with empty domains
        collector._distribute_bandwidth(1000, 2000)


class TestFlushWithData:
    """Test flushing with manually injected data."""

    def test_flush_returns_records(self):
        collector = NetworkCollector()
        now = time.time()

        collector._domains["github.com"] = DomainRecord(
            domain="github.com",
            app_name="Chrome",
            first_seen=now - 60,
            last_seen=now,
            connection_count=5,
            bytes_uploaded=10000,
            bytes_downloaded=50000,
        )

        records = collector.flush()
        assert len(records) == 1
        assert records[0]["domain"] == "github.com"
        assert records[0]["app_name"] == "Chrome"
        assert records[0]["duration_sec"] == 60
        assert records[0]["bytes_uploaded"] == 10000
        assert records[0]["bytes_downloaded"] == 50000

    def test_flush_clears_accumulator(self):
        collector = NetworkCollector()
        now = time.time()

        collector._domains["test.com"] = DomainRecord(
            domain="test.com",
            app_name="Firefox",
            first_seen=now - 10,
            last_seen=now,
        )

        collector.flush()
        assert collector.current_domain_count == 0

        second = collector.flush()
        assert second == []

    def test_flush_filters_short_duration(self):
        collector = NetworkCollector()
        collector._domains["flash.com"] = DomainRecord(
            domain="flash.com",
            app_name="Chrome",
            first_seen=0,
            last_seen=0,  # duration = 0
        )

        records = collector.flush()
        assert len(records) == 0

    def test_flush_multiple_domains(self):
        collector = NetworkCollector()
        now = time.time()

        for i in range(5):
            domain = f"site{i}.com"
            collector._domains[domain] = DomainRecord(
                domain=domain,
                app_name="Chrome",
                first_seen=now - 30,
                last_seen=now,
                connection_count=1,
            )

        records = collector.flush()
        assert len(records) == 5


class TestLiveCollection:
    """Integration test: run collector briefly with real network."""

    def test_collects_real_connections(self):
        collector = NetworkCollector()
        collector.start()
        time.sleep(6)  # At least one poll cycle (5s interval)
        collector.stop()

        records = collector.flush()
        # May or may not have records depending on active connections
        assert isinstance(records, list)

    def test_active_domains_list(self):
        collector = NetworkCollector()
        domains = collector.get_active_domains()
        assert isinstance(domains, list)


class TestMonitoredPorts:
    """Test port configuration."""

    def test_standard_ports_monitored(self):
        assert 80 in MONITORED_PORTS
        assert 443 in MONITORED_PORTS

    def test_alternate_ports_monitored(self):
        assert 8080 in MONITORED_PORTS
        assert 8443 in MONITORED_PORTS
