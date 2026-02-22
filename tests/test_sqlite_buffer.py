"""
Tests for the SQLite buffer.
Run with: python -m pytest tests/test_sqlite_buffer.py -v
"""

import time
import json
import pytest
from pathlib import Path

from src.storage.sqlite_buffer import SQLiteBuffer, PendingRecord, VALID_TABLES


@pytest.fixture
def db(tmp_path):
    """Create a fresh SQLite buffer using a temp directory."""
    db_path = tmp_path / "test_agent.db"
    buffer = SQLiteBuffer(db_path=db_path)
    yield buffer
    buffer.close()


@pytest.fixture
def sample_session_payload():
    return {
        "employee_id": 1,
        "device_mac": "58:1c:f8:f4:c3:d8",
        "session_start": "2026-02-18T09:00:00Z",
        "session_end": None,
        "active_duration_sec": 3200,
        "idle_duration_sec": 400,
        "bytes_uploaded": 1524000,
        "bytes_downloaded": 5890000,
        "avg_bandwidth_kbps": 1250.5,
        "source": "local_agent",
    }


@pytest.fixture
def sample_app_payload():
    return {
        "employee_id": 1,
        "device_mac": "58:1c:f8:f4:c3:d8",
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


@pytest.fixture
def sample_domain_payload():
    return {
        "employee_id": 1,
        "device_mac": "58:1c:f8:f4:c3:d8",
        "app_name": "Chrome",
        "domain": "github.com",
        "category": "productivity",
        "bytes_uploaded": 50000,
        "bytes_downloaded": 200000,
        "duration_sec": 600,
        "visited_at": "2026-02-18T09:10:00Z",
    }


class TestDatabaseInit:
    """Test database initialization and setup."""

    def test_creates_database_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        assert not db_path.exists()
        buffer = SQLiteBuffer(db_path=db_path)
        assert db_path.exists()
        buffer.close()

    def test_creates_parent_directories(self, tmp_path):
        db_path = tmp_path / "sub" / "dir" / "test.db"
        buffer = SQLiteBuffer(db_path=db_path)
        assert db_path.exists()
        buffer.close()

    def test_db_size_bytes(self, db):
        assert db.db_size_bytes > 0

    def test_db_size_mb(self, db):
        assert db.db_size_mb >= 0.0


class TestConfigStore:
    """Test the key-value config store."""

    def test_set_and_get(self, db):
        db.set_config("employee_id", "42")
        assert db.get_config("employee_id") == "42"

    def test_get_missing_returns_default(self, db):
        assert db.get_config("nonexistent") is None
        assert db.get_config("nonexistent", "fallback") == "fallback"

    def test_update_existing(self, db):
        db.set_config("key1", "value1")
        db.set_config("key1", "value2")
        assert db.get_config("key1") == "value2"

    def test_delete_config(self, db):
        db.set_config("to_delete", "temp")
        assert db.get_config("to_delete") == "temp"
        db.delete_config("to_delete")
        assert db.get_config("to_delete") is None

    def test_get_all_config(self, db):
        db.set_config("a", "1")
        db.set_config("b", "2")
        db.set_config("c", "3")
        all_config = db.get_all_config()
        assert all_config == {"a": "1", "b": "2", "c": "3"}

    def test_get_all_config_empty(self, db):
        assert db.get_all_config() == {}


class TestPendingRecords:
    """Test inserting and retrieving pending records."""

    def test_insert_session(self, db, sample_session_payload):
        record_id = db.insert_pending("pending_sessions", sample_session_payload)
        assert record_id is not None
        assert record_id > 0

    def test_insert_app_usage(self, db, sample_app_payload):
        record_id = db.insert_pending("pending_app_usage", sample_app_payload)
        assert record_id is not None

    def test_insert_domain_visit(self, db, sample_domain_payload):
        record_id = db.insert_pending("pending_domain_visits", sample_domain_payload)
        assert record_id is not None

    def test_invalid_table_raises(self, db):
        with pytest.raises(ValueError, match="Invalid table name"):
            db.insert_pending("invalid_table", {"data": "test"})

    def test_get_pending_returns_records(self, db, sample_session_payload):
        db.insert_pending("pending_sessions", sample_session_payload)
        records = db.get_pending("pending_sessions")
        assert len(records) == 1
        assert isinstance(records[0], PendingRecord)
        assert records[0].status == "pending"
        assert records[0].payload["employee_id"] == 1

    def test_get_pending_ordered_by_created_at(self, db):
        db.insert_pending("pending_sessions", {"order": 1})
        time.sleep(0.01)
        db.insert_pending("pending_sessions", {"order": 2})
        time.sleep(0.01)
        db.insert_pending("pending_sessions", {"order": 3})

        records = db.get_pending("pending_sessions")
        assert len(records) == 3
        assert records[0].payload["order"] == 1
        assert records[1].payload["order"] == 2
        assert records[2].payload["order"] == 3

    def test_get_pending_respects_limit(self, db):
        for i in range(10):
            db.insert_pending("pending_sessions", {"i": i})

        records = db.get_pending("pending_sessions", limit=3)
        assert len(records) == 3

    def test_get_pending_empty(self, db):
        records = db.get_pending("pending_sessions")
        assert records == []


class TestBatchInsert:
    """Test batch insertion."""

    def test_batch_insert(self, db):
        payloads = [{"domain": f"site{i}.com"} for i in range(5)]
        count = db.insert_pending_batch("pending_domain_visits", payloads)
        assert count == 5

        records = db.get_pending("pending_domain_visits")
        assert len(records) == 5

    def test_batch_insert_empty(self, db):
        count = db.insert_pending_batch("pending_sessions", [])
        assert count == 0

    def test_batch_insert_large(self, db):
        payloads = [{"i": i} for i in range(100)]
        count = db.insert_pending_batch("pending_app_usage", payloads)
        assert count == 100


class TestMarkSent:
    """Test marking records as sent."""

    def test_mark_sent(self, db, sample_session_payload):
        record_id = db.insert_pending("pending_sessions", sample_session_payload)
        db.mark_sent("pending_sessions", record_id)

        # Should not appear in pending anymore
        records = db.get_pending("pending_sessions")
        assert len(records) == 0

    def test_mark_sent_creates_log(self, db, sample_session_payload):
        record_id = db.insert_pending("pending_sessions", sample_session_payload)
        db.mark_sent("pending_sessions", record_id, response_code=201)

        # Check sent_log directly
        cursor = db._conn.execute("SELECT * FROM sent_log WHERE record_id = ?", (record_id,))
        row = cursor.fetchone()
        assert row is not None


class TestMarkFailed:
    """Test marking records as failed with retry logic."""

    def test_mark_failed(self, db):
        record_id = db.insert_pending("pending_sessions", {"test": True})
        db.mark_failed("pending_sessions", record_id)

        # Should not appear in pending (status changed to 'failed')
        pending = db.get_pending("pending_sessions")
        assert len(pending) == 0

    def test_mark_failed_increments_retry(self, db):
        record_id = db.insert_pending("pending_sessions", {"test": True})

        db.mark_failed("pending_sessions", record_id)
        db.mark_failed("pending_sessions", record_id)
        db.mark_failed("pending_sessions", record_id)

        cursor = db._conn.execute(
            "SELECT retry_count FROM pending_sessions WHERE id = ?", (record_id,)
        )
        row = cursor.fetchone()
        assert row[0] == 3

    def test_mark_permanently_failed(self, db):
        record_id = db.insert_pending("pending_sessions", {"test": True})
        db.mark_permanently_failed("pending_sessions", record_id)

        cursor = db._conn.execute(
            "SELECT status FROM pending_sessions WHERE id = ?", (record_id,)
        )
        row = cursor.fetchone()
        assert row[0] == "permanently_failed"


class TestRetryable:
    """Test fetching retryable records."""

    def test_get_retryable_empty(self, db):
        records = db.get_retryable("pending_sessions")
        assert records == []

    def test_failed_record_becomes_retryable(self, db):
        record_id = db.insert_pending("pending_sessions", {"test": True})
        db.mark_failed("pending_sessions", record_id)

        # Manually set last_retry_at to long ago so backoff passes
        db._conn.execute(
            "UPDATE pending_sessions SET last_retry_at = ? WHERE id = ?",
            (time.time() - 9999, record_id),
        )
        db._conn.commit()

        records = db.get_retryable("pending_sessions")
        assert len(records) == 1
        assert records[0].retry_count == 1


class TestCleanup:
    """Test cleanup of old records."""

    def test_cleanup_sent(self, db):
        record_id = db.insert_pending("pending_sessions", {"test": True})
        db.mark_sent("pending_sessions", record_id)

        # Manually set created_at to 48 hours ago
        old_time = time.time() - (48 * 3600)
        db._conn.execute(
            "UPDATE pending_sessions SET created_at = ? WHERE id = ?",
            (old_time, record_id),
        )
        db._conn.commit()

        db.cleanup_sent(older_than_hours=24)

        cursor = db._conn.execute(
            "SELECT COUNT(*) FROM pending_sessions WHERE id = ?", (record_id,)
        )
        assert cursor.fetchone()[0] == 0

    def test_cleanup_does_not_delete_pending(self, db):
        db.insert_pending("pending_sessions", {"test": True})

        # Set old created_at
        old_time = time.time() - (48 * 3600)
        db._conn.execute(
            "UPDATE pending_sessions SET created_at = ?", (old_time,)
        )
        db._conn.commit()

        db.cleanup_sent(older_than_hours=24)

        # Should still be there because status is 'pending', not 'sent'
        records = db.get_pending("pending_sessions")
        assert len(records) == 1


class TestStats:
    """Test statistics retrieval."""

    def test_get_stats_empty(self, db):
        stats = db.get_stats()
        assert isinstance(stats, dict)
        for table in VALID_TABLES:
            assert table in stats

    def test_get_stats_with_data(self, db):
        db.insert_pending("pending_sessions", {"a": 1})
        db.insert_pending("pending_sessions", {"b": 2})
        rid = db.insert_pending("pending_sessions", {"c": 3})
        db.mark_sent("pending_sessions", rid)

        stats = db.get_stats()
        assert stats["pending_sessions"]["pending"] == 2
        assert stats["pending_sessions"]["sent"] == 1

    def test_get_pending_count(self, db):
        assert db.get_pending_count() == 0

        db.insert_pending("pending_sessions", {"a": 1})
        db.insert_pending("pending_app_usage", {"b": 2})
        db.insert_pending("pending_domain_visits", {"c": 3})

        assert db.get_pending_count() == 3

    def test_pending_count_excludes_sent(self, db):
        rid = db.insert_pending("pending_sessions", {"a": 1})
        db.insert_pending("pending_sessions", {"b": 2})
        db.mark_sent("pending_sessions", rid)

        assert db.get_pending_count() == 1


class TestVacuum:
    """Test vacuum operation."""

    def test_vacuum_runs(self, db):
        # Should not raise
        db.vacuum()


class TestCorruptionRecovery:
    """Test handling of corrupt database."""

    def test_recovers_from_corrupt_file(self, tmp_path):
        db_path = tmp_path / "corrupt.db"

        # Write garbage to simulate corruption
        db_path.write_bytes(b"THIS IS NOT A VALID SQLITE DATABASE FILE " * 100)

        # Should recover gracefully
        buffer = SQLiteBuffer(db_path=db_path)

        # Should work after recovery
        buffer.set_config("test", "works")
        assert buffer.get_config("test") == "works"

        buffer.close()

        # Backup should exist
        backup = db_path.with_suffix(".db.corrupt")
        assert backup.exists()


class TestThreadSafety:
    """Basic thread safety tests."""

    def test_concurrent_inserts(self, db):
        import threading

        errors = []

        def insert_records(start):
            try:
                for i in range(20):
                    db.insert_pending("pending_sessions", {"thread_start": start, "i": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=insert_records, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert db.get_pending_count() == 100  # 5 threads x 20 records

    def test_concurrent_read_write(self, db):
        import threading

        errors = []

        def writer():
            try:
                for i in range(20):
                    db.insert_pending("pending_sessions", {"w": i})
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(20):
                    db.get_pending("pending_sessions")
                    db.get_pending_count()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0