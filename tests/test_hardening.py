"""
Tests for Phase 14: Hardening & Optimization.
Covers crypto, batch operations, DNS cache management,
auth cooldown, watchdog, memory checks, and stale record recovery.
"""

import time
import sqlite3
import threading
import sys
import pytest # type: ignore
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock


# ============================================================
# Crypto tests
# ============================================================

class TestCrypto:
    """Tests for API key obfuscation utilities."""

    def test_roundtrip(self):
        from src.utils.crypto import obfuscate, deobfuscate, get_machine_salt

        salt = get_machine_salt()
        plaintext = "my_secret_api_key_123"
        encrypted = obfuscate(plaintext, salt)
        decrypted = deobfuscate(encrypted, salt)
        assert decrypted == plaintext

    def test_different_salts_produce_different_output(self):
        from src.utils.crypto import obfuscate

        salt_a = b"salt_a_value_here_32bytes_long!!"
        salt_b = b"salt_b_value_here_32bytes_long!!"
        plaintext = "same_key"
        enc_a = obfuscate(plaintext, salt_a)
        enc_b = obfuscate(plaintext, salt_b)
        assert enc_a != enc_b

    def test_special_characters(self):
        from src.utils.crypto import obfuscate, deobfuscate, get_machine_salt

        salt = get_machine_salt()
        plaintext = "key-with-$pecial!chars@2024#&*()"
        encrypted = obfuscate(plaintext, salt)
        assert deobfuscate(encrypted, salt) == plaintext

    def test_unicode_key(self):
        from src.utils.crypto import obfuscate, deobfuscate, get_machine_salt

        salt = get_machine_salt()
        plaintext = "キー_with_日本語"
        encrypted = obfuscate(plaintext, salt)
        assert deobfuscate(encrypted, salt) == plaintext

    def test_empty_string(self):
        from src.utils.crypto import obfuscate, deobfuscate, get_machine_salt

        salt = get_machine_salt()
        assert obfuscate("", salt) == ""
        assert deobfuscate("", salt) == ""

    def test_long_key(self):
        from src.utils.crypto import obfuscate, deobfuscate, get_machine_salt

        salt = get_machine_salt()
        plaintext = "A" * 500
        encrypted = obfuscate(plaintext, salt)
        assert deobfuscate(encrypted, salt) == plaintext

    def test_obfuscated_is_not_plaintext(self):
        from src.utils.crypto import obfuscate, get_machine_salt

        salt = get_machine_salt()
        plaintext = "visible_api_key"
        encrypted = obfuscate(plaintext, salt)
        assert encrypted != plaintext
        assert plaintext not in encrypted

    def test_machine_salt_is_stable(self):
        from src.utils.crypto import get_machine_salt

        salt1 = get_machine_salt()
        salt2 = get_machine_salt()
        assert salt1 == salt2
        assert len(salt1) == 32  # SHA-256 output


# ============================================================
# SQLite batch marking tests
# ============================================================

class TestBatchMarking:
    """Tests for batch mark_sent/mark_failed/mark_permanently_failed."""

    def _make_buffer(self, tmp_path):
        from src.storage.sqlite_buffer import SQLiteBuffer
        return SQLiteBuffer(db_path=tmp_path / "test.db")

    def test_mark_sent_batch(self, tmp_path):
        buf = self._make_buffer(tmp_path)
        ids = []
        for i in range(5):
            rid = buf.insert_pending("pending_sessions", {"i": i})
            ids.append(rid)

        buf.mark_sent_batch("pending_sessions", ids)

        pending = buf.get_pending("pending_sessions")
        assert len(pending) == 0

        stats = buf.get_stats()
        assert stats["pending_sessions"].get("sent", 0) == 5
        buf.close()

    def test_mark_failed_batch(self, tmp_path):
        buf = self._make_buffer(tmp_path)
        ids = []
        for i in range(3):
            rid = buf.insert_pending("pending_app_usage", {"i": i})
            ids.append(rid)

        buf.mark_failed_batch("pending_app_usage", ids)

        pending = buf.get_pending("pending_app_usage")
        assert len(pending) == 0  # status is now 'failed', not 'pending'

        from src.config import config
        retryable = buf.get_retryable("pending_app_usage", limit=50)
        # May or may not be retryable depending on backoff timing
        # But status should be 'failed'
        stats = buf.get_stats()
        assert stats["pending_app_usage"].get("failed", 0) == 3
        buf.close()

    def test_mark_permanently_failed_batch(self, tmp_path):
        buf = self._make_buffer(tmp_path)
        ids = []
        for i in range(4):
            rid = buf.insert_pending("pending_domain_visits", {"i": i})
            ids.append(rid)

        buf.mark_permanently_failed_batch("pending_domain_visits", ids)

        pending = buf.get_pending("pending_domain_visits")
        assert len(pending) == 0

        stats = buf.get_stats()
        assert stats["pending_domain_visits"].get("permanently_failed", 0) == 4
        buf.close()

    def test_batch_mark_empty_list(self, tmp_path):
        buf = self._make_buffer(tmp_path)
        # Should not raise
        buf.mark_sent_batch("pending_sessions", [])
        buf.mark_failed_batch("pending_sessions", [])
        buf.mark_permanently_failed_batch("pending_sessions", [])
        buf.close()

    def test_batch_partial_ids(self, tmp_path):
        """Mark only some records, others stay pending."""
        buf = self._make_buffer(tmp_path)
        id1 = buf.insert_pending("pending_sessions", {"a": 1})
        id2 = buf.insert_pending("pending_sessions", {"b": 2})
        id3 = buf.insert_pending("pending_sessions", {"c": 3})

        buf.mark_sent_batch("pending_sessions", [id1, id3]) # type: ignore

        pending = buf.get_pending("pending_sessions")
        assert len(pending) == 1
        assert pending[0].id == id2
        buf.close()


# ============================================================
# Stale 'sending' record reset tests
# ============================================================

class TestStaleSendingReset:
    """Tests for resetting records stuck in 'sending' status on init."""

    def test_stale_sending_reset_on_init(self, tmp_path):
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "test.db"

        # Create buffer, insert record, manually set status to 'sending'
        buf = SQLiteBuffer(db_path=db_path)
        rid = buf.insert_pending("pending_sessions", {"test": "data"})
        with buf._lock:
            buf._conn.execute( # type: ignore
                "UPDATE pending_sessions SET status = 'sending' WHERE id = ?",
                (rid,),
            )
            buf._conn.commit() # type: ignore
        buf.close()

        # Create new buffer pointing to same DB — should reset stale records
        buf2 = SQLiteBuffer(db_path=db_path)
        pending = buf2.get_pending("pending_sessions")
        assert len(pending) == 1
        assert pending[0].status == "pending"
        buf2.close()

    def test_stale_reset_multiple_tables(self, tmp_path):
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "test.db"
        buf = SQLiteBuffer(db_path=db_path)

        # Insert into multiple tables and set to 'sending'
        for table in ["pending_sessions", "pending_app_usage", "pending_domain_visits"]:
            rid = buf.insert_pending(table, {"table": table})
            with buf._lock:
                buf._conn.execute( # type: ignore
                    f"UPDATE {table} SET status = 'sending' WHERE id = ?",
                    (rid,),
                )
                buf._conn.commit() # type: ignore
        buf.close()

        # Reopen
        buf2 = SQLiteBuffer(db_path=db_path)
        for table in ["pending_sessions", "pending_app_usage", "pending_domain_visits"]:
            pending = buf2.get_pending(table)
            assert len(pending) == 1
            assert pending[0].status == "pending"
        buf2.close()


# ============================================================
# File permissions tests
# ============================================================

class TestFilePermissions:
    """Tests for restrictive file permissions on Linux/macOS."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Permissions not set on Windows")
    def test_db_file_permissions(self, tmp_path):
        from src.storage.sqlite_buffer import SQLiteBuffer
        import stat

        db_path = tmp_path / "test.db"
        buf = SQLiteBuffer(db_path=db_path)

        mode = db_path.stat().st_mode
        # Owner read+write only (0o600)
        assert mode & 0o777 == 0o600
        buf.close()


# ============================================================
# DNS cache management tests
# ============================================================

class TestDNSCacheManagement:
    """Tests for DNS cache eviction and size cap."""

    def _make_collector(self):
        """Create a NetworkCollector with mocked dependencies."""
        with patch("src.collectors.network_collector.get_platform") as mock_plat, \
             patch("src.collectors.network_collector.Categorizer"), \
             patch("src.collectors.network_collector.config") as mock_config:

            mock_plat_instance = MagicMock()
            mock_plat.return_value = mock_plat_instance

            mock_config.load_categories.return_value = {"ignored_domains": []}
            mock_config.NETWORK_POLL_INTERVAL = 5
            mock_config.MIN_DOMAIN_DURATION = 1

            # Patch _load_system_dns_cache to avoid subprocess calls
            from src.collectors.network_collector import NetworkCollector
            with patch.object(NetworkCollector, "_load_system_dns_cache"):
                collector = NetworkCollector()

        return collector

    def test_evict_expired_entries(self):
        collector = self._make_collector()

        # Add expired entries (older than 600s TTL)
        old_time = time.time() - 700
        collector._dns_cache["1.1.1.1"] = "old-domain.com"
        collector._dns_cache_ttl["1.1.1.1"] = old_time
        collector._dns_cache["2.2.2.2"] = "another-old.com"
        collector._dns_cache_ttl["2.2.2.2"] = old_time

        # Add fresh entry
        collector._dns_cache["3.3.3.3"] = "fresh.com"
        collector._dns_cache_ttl["3.3.3.3"] = time.time()

        collector._evict_expired_dns_entries()

        assert "1.1.1.1" not in collector._dns_cache
        assert "2.2.2.2" not in collector._dns_cache
        assert "3.3.3.3" in collector._dns_cache
        assert collector._dns_cache["3.3.3.3"] == "fresh.com"

    def test_enforce_cache_limit(self):
        from src.collectors.network_collector import DNS_CACHE_MAX_SIZE

        collector = self._make_collector()

        # Fill cache beyond limit
        count = DNS_CACHE_MAX_SIZE + 200
        now = time.time()
        for i in range(count):
            ip = f"10.0.{i // 256}.{i % 256}"
            collector._dns_cache[ip] = f"domain-{i}.com"
            collector._dns_cache_ttl[ip] = now - (count - i)  # oldest first

        assert len(collector._dns_cache) == count

        collector._enforce_cache_limit()

        assert len(collector._dns_cache) <= DNS_CACHE_MAX_SIZE
        # Oldest entries should be evicted
        assert "10.0.0.0" not in collector._dns_cache  # oldest

    def test_cache_under_limit_no_eviction(self):
        collector = self._make_collector()

        # Add a few entries (well under limit)
        collector._dns_cache["1.1.1.1"] = "example.com"
        collector._dns_cache_ttl["1.1.1.1"] = time.time()

        collector._enforce_cache_limit()

        assert "1.1.1.1" in collector._dns_cache

    def test_maybe_evict_respects_interval(self):
        collector = self._make_collector()
        collector._last_eviction_time = time.time()  # just ran

        # Add expired entry
        collector._dns_cache["1.1.1.1"] = "old.com"
        collector._dns_cache_ttl["1.1.1.1"] = time.time() - 700

        # Should not evict (too soon)
        collector._maybe_evict_dns_cache(time.time())
        assert "1.1.1.1" in collector._dns_cache

        # Should evict (enough time passed)
        collector._maybe_evict_dns_cache(time.time() + 400)
        assert "1.1.1.1" not in collector._dns_cache


# ============================================================
# Auth cooldown tests
# ============================================================

class TestAuthCooldown:
    """Tests for auth cooldown on 401/403 responses."""

    def _make_sender(self, tmp_path):
        from src.storage.sqlite_buffer import SQLiteBuffer
        from src.network.api_sender import APISender
        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        sender = APISender(buf)
        return sender, buf

    def test_auth_cooldown_activates_on_401(self, tmp_path):
        import responses as resp # type: ignore

        sender, buf = self._make_sender(tmp_path)
        buf.insert_pending("pending_sessions", {"test": "data"})

        with resp.RequestsMock() as rsps:
            rsps.add(
                resp.POST,
                f"{sender._base_url}/api/v1/telemetry/sessions",
                json={"detail": "Unauthorized"},
                status=401,
            )

            with patch.object(sender, "_is_network_available", return_value=True):
                sender._send_all_pending()

        assert sender._auth_cooldown_until > time.time()
        buf.close()

    def test_auth_cooldown_skips_send_cycle(self, tmp_path):
        sender, buf = self._make_sender(tmp_path)
        buf.insert_pending("pending_sessions", {"test": "data"})

        # Set cooldown in the future
        sender._auth_cooldown_until = time.time() + 600

        with patch.object(sender, "_is_network_available", return_value=True):
            sender._send_all_pending()

        # Record should still be pending (cycle was skipped)
        pending = buf.get_pending("pending_sessions")
        assert len(pending) == 1
        buf.close()

    def test_force_send_bypasses_cooldown(self, tmp_path):
        import responses as resp # type: ignore

        sender, buf = self._make_sender(tmp_path)
        buf.insert_pending("pending_sessions", {"test": "data"})

        # Set cooldown
        sender._auth_cooldown_until = time.time() + 600

        with resp.RequestsMock() as rsps:
            rsps.add(
                resp.POST,
                f"{sender._base_url}/api/v1/telemetry/sessions",
                json={"id": 1},
                status=201,
            )
            with patch.object(sender, "_is_network_available", return_value=True):
                sender.force_send()

        pending = buf.get_pending("pending_sessions")
        assert len(pending) == 0
        buf.close()

    def test_auth_cooldown_stops_remaining_tables(self, tmp_path):
        """After 401 on any table, remaining tables should be skipped."""
        import responses as resp # type: ignore
        from src.network.api_sender import ENDPOINTS

        sender, buf = self._make_sender(tmp_path)
        buf.insert_pending("pending_sessions", {"s": 1})
        buf.insert_pending("pending_app_usage", {"a": 1})
        buf.insert_pending("pending_domain_visits", {"d": 1})

        with resp.RequestsMock(assert_all_requests_are_fired=False) as rsps:
            # Return 401 for ALL endpoints — whichever is tried first will trigger cooldown
            for endpoint in ENDPOINTS.values():
                rsps.add(
                    resp.POST,
                    f"{sender._base_url}{endpoint}",
                    json={"detail": "Unauthorized"},
                    status=401,
                )

            with patch.object(sender, "_is_network_available", return_value=True):
                sender._send_all_pending()

        # At most 1 table should have been attempted (the first in iteration order).
        # The other tables should still have pending records.
        pending_s = len(buf.get_pending("pending_sessions"))
        pending_a = len(buf.get_pending("pending_app_usage"))
        pending_d = len(buf.get_pending("pending_domain_visits"))

        # Exactly 2 out of 3 should still be pending (untouched)
        still_pending = pending_s + pending_a + pending_d
        assert still_pending >= 2, (
            f"Expected at least 2 tables untouched, got {still_pending} "
            f"(s={pending_s}, a={pending_a}, d={pending_d})"
        )

        # Cooldown should be active
        assert sender._auth_cooldown_until > time.time()
        buf.close()


# ============================================================
# Last sync tracking tests
# ============================================================

class TestLastSyncTracking:
    """Tests for last_successful_sync config writing."""

    def test_last_sync_written_on_success(self, tmp_path):
        import responses as resp # type: ignore

        from src.storage.sqlite_buffer import SQLiteBuffer
        from src.network.api_sender import APISender

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        sender = APISender(buf)
        buf.insert_pending("pending_sessions", {"data": "ok"})

        with resp.RequestsMock() as rsps:
            rsps.add(
                resp.POST,
                f"{sender._base_url}/api/v1/telemetry/sessions",
                json={"id": 1},
                status=201,
            )
            with patch.object(sender, "_is_network_available", return_value=True):
                sender._send_all_pending()

        sync_time = buf.get_config("last_successful_sync")
        assert sync_time is not None
        assert "T" in sync_time  # ISO format
        buf.close()

    def test_last_sync_not_written_on_failure(self, tmp_path):
        import responses as resp # type: ignore

        from src.storage.sqlite_buffer import SQLiteBuffer
        from src.network.api_sender import APISender

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        sender = APISender(buf)
        buf.insert_pending("pending_sessions", {"data": "bad"})

        with resp.RequestsMock() as rsps:
            rsps.add(
                resp.POST,
                f"{sender._base_url}/api/v1/telemetry/sessions",
                json={"error": "bad"},
                status=500,
            )
            with patch.object(sender, "_is_network_available", return_value=True):
                sender._send_all_pending()

        sync_time = buf.get_config("last_successful_sync")
        assert sync_time is None
        buf.close()


# ============================================================
# Watchdog tests
# ============================================================

class TestWatchdog:
    """Tests for SessionManager.check_health() watchdog."""

    def test_check_health_all_alive(self):
        """check_health returns True when everything is running."""
        with patch("src.session.session_manager.get_platform"), \
             patch("src.session.session_manager.Categorizer"), \
             patch("src.session.session_manager.AppCollector") as MockApp, \
             patch("src.session.session_manager.NetworkCollector") as MockNet:

            mock_app = MockApp.return_value
            mock_app._running = True
            mock_app.is_thread_alive = True

            mock_net = MockNet.return_value
            mock_net._running = True
            mock_net.is_thread_alive = True

            from src.session.session_manager import SessionManager
            buf = MagicMock()
            buf.get_config.return_value = None
            sm = SessionManager(buf)
            sm._running = True

            assert sm.check_health() is True
            mock_app.start.assert_not_called()
            mock_net.start.assert_not_called()

    def test_check_health_restarts_dead_app_collector(self):
        """check_health restarts dead app collector."""
        with patch("src.session.session_manager.get_platform"), \
             patch("src.session.session_manager.Categorizer"), \
             patch("src.session.session_manager.AppCollector") as MockApp, \
             patch("src.session.session_manager.NetworkCollector") as MockNet:

            mock_app = MockApp.return_value
            mock_app._running = True
            mock_app.is_thread_alive = False  # thread died

            mock_net = MockNet.return_value
            mock_net._running = True
            mock_net.is_thread_alive = True

            from src.session.session_manager import SessionManager
            buf = MagicMock()
            buf.get_config.return_value = None
            sm = SessionManager(buf)
            sm._running = True

            result = sm.check_health()

            assert result is False
            mock_app.start.assert_called_once()

    def test_check_health_restarts_dead_network_collector(self):
        """check_health restarts dead network collector."""
        with patch("src.session.session_manager.get_platform"), \
             patch("src.session.session_manager.Categorizer"), \
             patch("src.session.session_manager.AppCollector") as MockApp, \
             patch("src.session.session_manager.NetworkCollector") as MockNet:

            mock_app = MockApp.return_value
            mock_app._running = True
            mock_app.is_thread_alive = True

            mock_net = MockNet.return_value
            mock_net._running = True
            mock_net.is_thread_alive = False  # thread died

            from src.session.session_manager import SessionManager
            buf = MagicMock()
            buf.get_config.return_value = None
            sm = SessionManager(buf)
            sm._running = True

            result = sm.check_health()

            assert result is False
            mock_net.start.assert_called_once()

    def test_check_health_noop_when_stopped(self):
        """check_health does nothing when session is stopped."""
        with patch("src.session.session_manager.get_platform"), \
             patch("src.session.session_manager.Categorizer"), \
             patch("src.session.session_manager.AppCollector") as MockApp, \
             patch("src.session.session_manager.NetworkCollector") as MockNet:

            from src.session.session_manager import SessionManager
            buf = MagicMock()
            buf.get_config.return_value = None
            sm = SessionManager(buf)
            sm._running = False

            assert sm.check_health() is True


# ============================================================
# Memory check tests
# ============================================================

class TestMemoryCheck:
    """Tests for memory monitoring in AgentCore."""

    def test_check_memory_runs_without_error(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        # Should not raise
        agent._check_memory()

    def test_check_memory_warns_on_high_usage(self):
        from src.agent_core import AgentCore, MEMORY_WARNING_MB

        agent = AgentCore()

        mock_process = MagicMock()
        mock_mem = MagicMock()
        mock_mem.rss = (MEMORY_WARNING_MB + 50) * 1024 * 1024  # Over threshold

        mock_process.memory_info.return_value = mock_mem

        with patch("psutil.Process", return_value=mock_process):
            with patch("src.agent_core.logger") as mock_logger:
                agent._check_memory()
                mock_logger.warning.assert_called_once()
                assert "High memory" in mock_logger.warning.call_args[0][0]


# ============================================================
# API key migration tests
# ============================================================

class TestAPIKeyMigration:
    """Tests for API key obfuscation migration in AgentCore."""

    def test_migrate_stores_key_in_db(self, tmp_path):
        from src.agent_core import AgentCore
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        agent = AgentCore()
        agent._buffer = buf

        with patch("src.config.config") as mock_config:
            mock_config.API_KEY = "test_api_key_12345"
            agent._migrate_api_key()

        stored = buf.get_config("api_key_enc")
        assert stored is not None
        assert stored != "test_api_key_12345"  # should be obfuscated
        buf.close()

    def test_migrate_loads_key_from_db(self, tmp_path):
        from src.agent_core import AgentCore
        from src.storage.sqlite_buffer import SQLiteBuffer
        from src.utils.crypto import get_machine_salt, obfuscate

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")

        # Pre-store an encrypted key
        salt = get_machine_salt()
        encrypted = obfuscate("stored_secret_key", salt)
        buf.set_config("api_key_enc", encrypted)

        agent = AgentCore()
        agent._buffer = buf

        with patch("src.agent_core.config") as mock_config:
            mock_config.API_KEY = "old_env_key"
            agent._migrate_api_key()
            # config.API_KEY should now be updated to the stored key
            assert mock_config.API_KEY == "stored_secret_key"

        buf.close()

    def test_migrate_skips_short_key(self, tmp_path):
        from src.agent_core import AgentCore
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        agent = AgentCore()
        agent._buffer = buf

        with patch("src.agent_core.config") as mock_config:
            mock_config.API_KEY = ""  # empty
            agent._migrate_api_key()

        stored = buf.get_config("api_key_enc")
        assert stored is None  # nothing stored
        buf.close()


# ============================================================
# Thread alive property tests
# ============================================================

class TestThreadAliveProperty:
    """Tests for is_thread_alive on collectors."""

    def test_app_collector_thread_alive_before_start(self):
        with patch("src.collectors.app_collector.get_platform"), \
             patch("src.collectors.app_collector.config") as mock_config:
            mock_config.load_categories.return_value = {"ignored_apps": []}
            mock_config.APP_POLL_INTERVAL = 1
            mock_config.IDLE_THRESHOLD = 60

            from src.collectors.app_collector import AppCollector
            collector = AppCollector()
            assert collector.is_thread_alive is False

    def test_network_collector_thread_alive_before_start(self):
        with patch("src.collectors.network_collector.get_platform"), \
             patch("src.collectors.network_collector.Categorizer"), \
             patch("src.collectors.network_collector.config") as mock_config:
            mock_config.load_categories.return_value = {"ignored_domains": []}
            mock_config.NETWORK_POLL_INTERVAL = 5
            mock_config.MIN_DOMAIN_DURATION = 1

            from src.collectors.network_collector import NetworkCollector
            with patch.object(NetworkCollector, "_load_system_dns_cache"):
                collector = NetworkCollector()
            assert collector.is_thread_alive is False