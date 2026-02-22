"""
Local SQLite buffer for persisting telemetry data.
Survives crashes, network failures, and agent restarts.
All pending payloads are stored here until successfully sent.
"""

import sys
import json
import time
import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.config import config

logger = logging.getLogger("agent.storage")


@dataclass
class PendingRecord:
    """A single buffered record waiting to be sent."""
    id: int
    table: str
    payload: dict
    created_at: float
    retry_count: int
    last_retry_at: Optional[float]
    status: str  # pending, sending, sent, failed, permanently_failed


# SQL statements
_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at REAL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS pending_app_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at REAL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS pending_domain_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at REAL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS sent_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    sent_at REAL NOT NULL,
    response_code INTEGER
);

CREATE TABLE IF NOT EXISTS event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    device_mac TEXT,
    event_type TEXT NOT NULL,
    event_time REAL NOT NULL,
    details TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON pending_sessions(status);
CREATE INDEX IF NOT EXISTS idx_app_usage_status ON pending_app_usage(status);
CREATE INDEX IF NOT EXISTS idx_domain_visits_status ON pending_domain_visits(status);
CREATE INDEX IF NOT EXISTS idx_sent_log_sent_at ON sent_log(sent_at);
CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log(event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_time ON event_log(event_time);
"""

# Valid table names for pending records
VALID_TABLES = {"pending_sessions", "pending_app_usage", "pending_domain_visits"}


class SQLiteBuffer:
    """
    Thread-safe SQLite buffer for telemetry data.

    All writes and reads go through a single lock to prevent
    concurrent access issues with SQLite.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or config.DB_PATH
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

        self._initialize()

    def _initialize(self):
        """Create database and tables if they don't exist."""
        try:
            # Ensure parent directory exists
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

            self._conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10,
            )

            # Enable WAL mode for crash safety
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")

            # Create tables
            self._conn.executescript(_CREATE_TABLES)
            self._conn.commit()

            # Reset any records stuck in 'sending' from a previous crash
            self._reset_stale_sending()

            # Set restrictive file permissions on non-Windows
            self._set_file_permissions()

            logger.info(f"SQLite buffer initialized at {self._db_path}")

        except sqlite3.DatabaseError as e:
            logger.error(f"Database corruption detected: {e}")
            self._handle_corruption()

    def _handle_corruption(self):
        """Handle a corrupt database by backing it up and starting fresh."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass

        backup_path = self._db_path.with_suffix(".db.corrupt")
        try:
            if self._db_path.exists():
                self._db_path.rename(backup_path)
                logger.warning(f"Corrupt database backed up to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup corrupt database: {e}")
            try:
                self._db_path.unlink(missing_ok=True)
            except Exception:
                pass

        # Reinitialize with fresh database
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            timeout=10,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_CREATE_TABLES)
        self._conn.commit()
        self._set_file_permissions()
        logger.info("Fresh database created after corruption recovery")

    def _reset_stale_sending(self):
        """
        Reset records stuck in 'sending' status back to 'pending'.
        This happens when the agent crashed mid-send in a previous run.
        Called once during initialization.
        """
        try:
            total = 0
            for table in VALID_TABLES:
                cursor = self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET status = 'pending' WHERE status = 'sending'"
                )
                total += cursor.rowcount
            self._conn.commit()  # type: ignore
            if total > 0:
                logger.warning(f"Reset {total} stale 'sending' records to 'pending'")
        except Exception as e:
            logger.error(f"Failed to reset stale sending records: {e}")

    def _set_file_permissions(self):
        """Set restrictive file permissions (owner-only) on Linux/macOS."""
        if sys.platform == "win32":
            return
        try:
            if self._db_path.exists():
                self._db_path.chmod(0o600)
        except Exception as e:
            logger.debug(f"Could not set DB file permissions: {e}")

    # --------------------------------------------------
    # Config key-value store
    # --------------------------------------------------

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Read a config value by key."""
        with self._lock:
            try:
                cursor = self._conn.execute(  # type: ignore
                    "SELECT value FROM config WHERE key = ?", (key,)
                )
                row = cursor.fetchone()
                return row[0] if row else default
            except Exception as e:
                logger.error(f"Failed to read config key '{key}': {e}")
                return default

    def set_config(self, key: str, value: str):
        """Write a config value. Creates or updates."""
        with self._lock:
            try:
                self._conn.execute(  # type: ignore
                    "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, str(value), time.time()),
                )
                self._conn.commit()  # type: ignore
            except Exception as e:
                logger.error(f"Failed to write config key '{key}': {e}")

    def delete_config(self, key: str):
        """Delete a config key."""
        with self._lock:
            try:
                self._conn.execute("DELETE FROM config WHERE key = ?", (key,))  # type: ignore
                self._conn.commit()  # type: ignore
            except Exception as e:
                logger.error(f"Failed to delete config key '{key}': {e}")

    def get_all_config(self) -> dict:
        """Read all config key-value pairs."""
        with self._lock:
            try:
                cursor = self._conn.execute("SELECT key, value FROM config")  # type: ignore
                return {row[0]: row[1] for row in cursor.fetchall()}
            except Exception as e:
                logger.error(f"Failed to read all config: {e}")
                return {}

    # --------------------------------------------------
    # Pending record operations
    # --------------------------------------------------

    def _validate_table(self, table: str):
        """Validate table name to prevent SQL injection."""
        if table not in VALID_TABLES:
            raise ValueError(f"Invalid table name: {table}. Must be one of {VALID_TABLES}")

    def insert_pending(self, table: str, payload: dict) -> Optional[int]:
        """
        Insert a new pending record.
        Returns the record ID, or None on failure.
        """
        self._validate_table(table)

        with self._lock:
            try:
                payload_json = json.dumps(payload, default=str)
                cursor = self._conn.execute(  # type: ignore
                    f"INSERT INTO {table} (payload_json, created_at, retry_count, status) "
                    f"VALUES (?, ?, 0, 'pending')",
                    (payload_json, time.time()),
                )
                self._conn.commit()  # type: ignore
                record_id = cursor.lastrowid
                logger.debug(f"Inserted pending record into {table} (id={record_id})")
                return record_id
            except Exception as e:
                logger.error(f"Failed to insert into {table}: {e}")
                return None

    def insert_pending_batch(self, table: str, payloads: list[dict]) -> int:
        """
        Insert multiple pending records in a single transaction.
        Returns the number of records inserted.
        """
        self._validate_table(table)

        if not payloads:
            return 0

        with self._lock:
            try:
                now = time.time()
                rows = [
                    (json.dumps(p, default=str), now, 0, "pending")
                    for p in payloads
                ]
                self._conn.executemany(  # type: ignore
                    f"INSERT INTO {table} (payload_json, created_at, retry_count, status) "
                    f"VALUES (?, ?, ?, ?)",
                    rows,
                )
                self._conn.commit()  # type: ignore
                count = len(rows)
                logger.debug(f"Batch inserted {count} records into {table}")
                return count
            except Exception as e:
                logger.error(f"Failed to batch insert into {table}: {e}")
                return 0

    def log_event(self, event_type: str, employee_id: Optional[int] = None, device_mac: Optional[str] = None, details: Optional[str] = None):
        """
        Log an event (pause/resume/etc) to the event_log table.
        
        Args:
            event_type: Type of event (e.g., 'pause', 'resume')
            employee_id: Optional employee ID
            device_mac: Optional device MAC address
            details: Optional JSON string with additional details
        """
        with self._lock:
            try:
                event_time = time.time()
                self._conn.execute(  # type: ignore
                    "INSERT INTO event_log (employee_id, device_mac, event_type, event_time, details) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (employee_id, device_mac, event_type, event_time, details)
                )
                self._conn.commit()  # type: ignore
                logger.debug(f"Event logged: {event_type} (employee_id={employee_id})")
            except Exception as e:
                logger.error(f"Failed to log event '{event_type}': {e}")

    def get_pending(self, table: str, limit: int = 50) -> list[PendingRecord]:
        """
        Fetch oldest pending records (status = 'pending').
        Returns list of PendingRecord objects.
        """
        self._validate_table(table)

        with self._lock:
            try:
                cursor = self._conn.execute(  # type: ignore
                    f"SELECT id, payload_json, created_at, retry_count, last_retry_at, status "
                    f"FROM {table} "
                    f"WHERE status = 'pending' "
                    f"ORDER BY created_at ASC "
                    f"LIMIT ?",
                    (limit,),
                )
                records = []
                for row in cursor.fetchall():
                    try:
                        payload = json.loads(row[1])
                    except json.JSONDecodeError:
                        payload = {}

                    records.append(PendingRecord(
                        id=row[0],
                        table=table,
                        payload=payload,
                        created_at=row[2],
                        retry_count=row[3],
                        last_retry_at=row[4],
                        status=row[5],
                    ))
                return records
            except Exception as e:
                logger.error(f"Failed to fetch pending from {table}: {e}")
                return []

    def get_retryable(self, table: str, limit: int = 20) -> list[PendingRecord]:
        """
        Fetch failed records that are eligible for retry.
        Only returns records where enough time has passed based on retry count.
        """
        self._validate_table(table)

        with self._lock:
            try:
                cursor = self._conn.execute(  # type: ignore
                    f"SELECT id, payload_json, created_at, retry_count, last_retry_at, status "
                    f"FROM {table} "
                    f"WHERE status = 'failed' AND retry_count < ? "
                    f"ORDER BY last_retry_at ASC "
                    f"LIMIT ?",
                    (config.MAX_RETRIES, limit),
                )
                now = time.time()
                records = []
                for row in cursor.fetchall():
                    retry_count = row[3]
                    last_retry = row[4] or 0

                    # Calculate backoff delay
                    delay = min(
                        config.INITIAL_RETRY_DELAY * (2 ** retry_count),
                        config.MAX_RETRY_DELAY,
                    )

                    # Check if enough time has passed
                    if now - last_retry < delay:
                        continue

                    try:
                        payload = json.loads(row[1])
                    except json.JSONDecodeError:
                        payload = {}

                    records.append(PendingRecord(
                        id=row[0],
                        table=table,
                        payload=payload,
                        created_at=row[2],
                        retry_count=retry_count,
                        last_retry_at=row[4],
                        status=row[5],
                    ))
                return records
            except Exception as e:
                logger.error(f"Failed to fetch retryable from {table}: {e}")
                return []

    # --------------------------------------------------
    # Single record marking (kept for backward compatibility)
    # --------------------------------------------------

    def mark_sent(self, table: str, record_id: int, response_code: int = 200):
        """Mark a record as successfully sent."""
        self._validate_table(table)

        with self._lock:
            try:
                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET status = 'sent' WHERE id = ?",
                    (record_id,),
                )
                self._conn.execute(  # type: ignore
                    "INSERT INTO sent_log (table_name, record_id, sent_at, response_code) "
                    "VALUES (?, ?, ?, ?)",
                    (table, record_id, time.time(), response_code),
                )
                self._conn.commit()  # type: ignore
                logger.debug(f"Marked {table}:{record_id} as sent")
            except Exception as e:
                logger.error(f"Failed to mark sent {table}:{record_id}: {e}")

    def mark_failed(self, table: str, record_id: int):
        """Mark a record as failed and increment retry count."""
        self._validate_table(table)

        with self._lock:
            try:
                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET "
                    f"status = 'failed', "
                    f"retry_count = retry_count + 1, "
                    f"last_retry_at = ? "
                    f"WHERE id = ?",
                    (time.time(), record_id),
                )
                self._conn.commit()  # type: ignore
                logger.debug(f"Marked {table}:{record_id} as failed")
            except Exception as e:
                logger.error(f"Failed to mark failed {table}:{record_id}: {e}")

    def mark_permanently_failed(self, table: str, record_id: int):
        """Mark a record as permanently failed (no more retries)."""
        self._validate_table(table)

        with self._lock:
            try:
                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET status = 'permanently_failed' WHERE id = ?",
                    (record_id,),
                )
                self._conn.commit()  # type: ignore
                logger.warning(f"Permanently failed: {table}:{record_id}")
            except Exception as e:
                logger.error(f"Failed to mark permanently failed {table}:{record_id}: {e}")

    # --------------------------------------------------
    # Batch record marking (used by APISender for efficiency)
    # --------------------------------------------------

    def mark_sent_batch(self, table: str, record_ids: list[int], response_code: int = 200):
        """Mark multiple records as sent in a single transaction."""
        if not record_ids:
            return
        self._validate_table(table)

        with self._lock:
            try:
                now = time.time()
                placeholders = ",".join("?" for _ in record_ids)

                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET status = 'sent' WHERE id IN ({placeholders})",
                    record_ids,
                )

                log_rows = [(table, rid, now, response_code) for rid in record_ids]
                self._conn.executemany(  # type: ignore
                    "INSERT INTO sent_log (table_name, record_id, sent_at, response_code) "
                    "VALUES (?, ?, ?, ?)",
                    log_rows,
                )

                self._conn.commit()  # type: ignore
                logger.debug(f"Batch marked {len(record_ids)} records as sent in {table}")
            except Exception as e:
                logger.error(f"Failed to batch mark sent in {table}: {e}")

    def mark_failed_batch(self, table: str, record_ids: list[int]):
        """Mark multiple records as failed and increment retry counts in a single transaction."""
        if not record_ids:
            return
        self._validate_table(table)

        with self._lock:
            try:
                now = time.time()
                placeholders = ",".join("?" for _ in record_ids)

                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET "
                    f"status = 'failed', "
                    f"retry_count = retry_count + 1, "
                    f"last_retry_at = ? "
                    f"WHERE id IN ({placeholders})",
                    [now] + record_ids,
                )

                self._conn.commit()  # type: ignore
                logger.debug(f"Batch marked {len(record_ids)} records as failed in {table}")
            except Exception as e:
                logger.error(f"Failed to batch mark failed in {table}: {e}")

    def mark_permanently_failed_batch(self, table: str, record_ids: list[int]):
        """Mark multiple records as permanently failed in a single transaction."""
        if not record_ids:
            return
        self._validate_table(table)

        with self._lock:
            try:
                placeholders = ",".join("?" for _ in record_ids)

                self._conn.execute(  # type: ignore
                    f"UPDATE {table} SET status = 'permanently_failed' "
                    f"WHERE id IN ({placeholders})",
                    record_ids,
                )

                self._conn.commit()  # type: ignore
                logger.warning(
                    f"Batch permanently failed: {len(record_ids)} records in {table}"
                )
            except Exception as e:
                logger.error(f"Failed to batch mark permanently failed in {table}: {e}")

    # --------------------------------------------------
    # Cleanup and stats
    # --------------------------------------------------

    def cleanup_sent(self, older_than_hours: int = 24):
        """Delete sent records and their log entries older than the given threshold."""
        cutoff = time.time() - (older_than_hours * 3600)

        with self._lock:
            try:
                total_deleted = 0
                for table in VALID_TABLES:
                    cursor = self._conn.execute(  # type: ignore
                        f"DELETE FROM {table} WHERE status = 'sent' AND created_at < ?",
                        (cutoff,),
                    )
                    total_deleted += cursor.rowcount

                # Clean old sent_log entries too
                self._conn.execute(  # type: ignore
                    "DELETE FROM sent_log WHERE sent_at < ?",
                    (cutoff,),
                )

                # Clean permanently failed records older than 7 days
                perm_cutoff = time.time() - (7 * 24 * 3600)
                for table in VALID_TABLES:
                    self._conn.execute(  # type: ignore
                        f"DELETE FROM {table} WHERE status = 'permanently_failed' AND created_at < ?",
                        (perm_cutoff,),
                    )

                self._conn.commit()  # type: ignore

                if total_deleted > 0:
                    logger.info(f"Cleaned up {total_deleted} sent records older than {older_than_hours}h")

            except Exception as e:
                logger.error(f"Cleanup failed: {e}")

    def get_stats(self) -> dict:
        """Get counts of records by status for each table."""
        stats = {}
        with self._lock:
            try:
                for table in VALID_TABLES:
                    cursor = self._conn.execute(  # type: ignore
                        f"SELECT status, COUNT(*) FROM {table} GROUP BY status"
                    )
                    table_stats = {}
                    for row in cursor.fetchall():
                        table_stats[row[0]] = row[1]
                    stats[table] = table_stats
            except Exception as e:
                logger.error(f"Failed to get stats: {e}")
        return stats

    def get_pending_count(self) -> int:
        """Get total number of unsent records across all tables."""
        total = 0
        with self._lock:
            try:
                for table in VALID_TABLES:
                    cursor = self._conn.execute(  # type: ignore
                        f"SELECT COUNT(*) FROM {table} WHERE status IN ('pending', 'failed')"
                    )
                    row = cursor.fetchone()
                    if row:
                        total += row[0]
            except Exception as e:
                logger.error(f"Failed to get pending count: {e}")
        return total

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def close(self):
        """Close the database connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                    logger.info("SQLite buffer closed")
                except Exception as e:
                    logger.error(f"Error closing database: {e}")
                finally:
                    self._conn = None

    def vacuum(self):
        """Reclaim disk space from deleted records."""
        with self._lock:
            try:
                self._conn.execute("VACUUM")  # type: ignore
                logger.info("Database vacuumed")
            except Exception as e:
                logger.error(f"Vacuum failed: {e}")

    @property
    def db_size_bytes(self) -> int:
        """Get the current database file size in bytes."""
        try:
            return self._db_path.stat().st_size
        except Exception:
            return 0

    @property
    def db_size_mb(self) -> float:
        """Get the current database file size in MB."""
        return self.db_size_bytes / (1024 * 1024)