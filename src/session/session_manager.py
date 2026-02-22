"""
Session Manager (Aggregator).
Cleans, deduplicates, and merges raw data from collectors.
Manages the overall monitoring session lifecycle.
Coordinates flush cycles and packages data for the API sender.
"""

import time
import threading
import logging
from datetime import datetime, timezone
from typing import Optional

from src.config import config
from src.platform import get_platform
from src.collectors.app_collector import AppCollector
from src.collectors.network_collector import NetworkCollector
from src.categorization.categorizer import Categorizer
from src.storage.sqlite_buffer import SQLiteBuffer

logger = logging.getLogger("agent.session")


class SessionManager:
    """
    Coordinates data collection, aggregation, and buffering.

    Responsibilities:
    - Owns the AppCollector and NetworkCollector
    - Periodically flushes collector data
    - Packages data into API-ready payloads
    - Writes payloads to SQLite buffer
    - Tracks overall session state (start/end, active/idle totals)
    """

    def __init__(self, buffer: SQLiteBuffer):
        self._buffer = buffer
        self._platform = get_platform()
        self._categorizer = Categorizer()
        self._app_collector = AppCollector()
        self._network_collector = NetworkCollector()

        # Session state
        self._session_start: Optional[str] = None
        self._total_active_sec: float = 0.0
        self._total_idle_sec: float = 0.0
        self._total_bytes_up: int = 0
        self._total_bytes_down: int = 0
        self._last_flush_time: float = 0.0

        # Identity (loaded from buffer config)
        self._employee_id: Optional[int] = None
        self._device_mac: Optional[str] = None

        # Thread control
        self._running = False
        self._flush_thread: Optional[threading.Thread] = None
        self._session_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._load_identity()

    def _load_identity(self):
        """Load employee_id and device_mac from local config."""
        emp_id = self._buffer.get_config("employee_id")
        if emp_id is not None:
            try:
                self._employee_id = int(emp_id)
            except ValueError:
                self._employee_id = None

        self._device_mac = self._buffer.get_config("device_mac")

        if self._device_mac is None:
            self._device_mac = self._platform.get_mac_address()

        logger.info(
            f"Identity loaded: employee_id={self._employee_id}, "
            f"device_mac={self._device_mac}"
        )

    def set_identity(self, employee_id: int, device_mac: str):
        """Set identity after first-launch authentication."""
        self._employee_id = employee_id
        self._device_mac = device_mac
        self._buffer.set_config("employee_id", str(employee_id))
        self._buffer.set_config("device_mac", device_mac)
        logger.info(f"Identity set: employee_id={employee_id}, device_mac={device_mac}")

    @property
    def is_configured(self) -> bool:
        """Check if identity is set (first launch completed)."""
        return self._employee_id is not None and self._device_mac is not None

    @property
    def employee_id(self) -> Optional[int]:
        return self._employee_id

    @property
    def device_mac(self) -> Optional[str]:
        return self._device_mac

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def start(self):
        """Start the session: collectors + periodic flush."""
        if self._running:
            logger.warning("SessionManager already running")
            return

        if not self.is_configured:
            logger.error("Cannot start session: identity not configured")
            return

        self._running = True
        self._session_start = datetime.now(timezone.utc).isoformat()
        self._total_active_sec = 0.0
        self._total_idle_sec = 0.0
        self._total_bytes_up = 0
        self._total_bytes_down = 0
        self._last_flush_time = time.time()

        # Start collectors
        self._app_collector.start()
        self._network_collector.start()

        # Buffer initial session record
        self._buffer_session_start()

        # Start periodic flush thread
        self._flush_thread = threading.Thread(
            target=self._flush_loop,
            name="FlushThread",
            daemon=True,
        )
        self._flush_thread.start()

        # Start periodic session update thread
        self._session_thread = threading.Thread(
            target=self._session_update_loop,
            name="SessionUpdateThread",
            daemon=True,
        )
        self._session_thread.start()

        logger.info(f"Session started at {self._session_start}")

    def stop(self):
        """Stop the session: flush remaining data, send session end."""
        if not self._running:
            return

        logger.info("Stopping session...")
        self._running = False

        # Stop collectors
        self._app_collector.stop()
        self._network_collector.stop()

        # Final flush
        self._flush_collectors()

        # Buffer session end
        self._buffer_session_end()

        # Wait for threads
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=5)
        if self._session_thread and self._session_thread.is_alive():
            self._session_thread.join(timeout=5)

        logger.info("Session stopped")

    # --------------------------------------------------
    # Health check (called by watchdog)
    # --------------------------------------------------

    def check_health(self) -> bool:
        """
        Check if collector threads are alive, restart if dead.
        Called by the agent core watchdog.
        Returns True if all healthy.
        """
        if not self._running:
            return True

        healthy = True

        # Check app collector thread
        if self._app_collector._running and not self._app_collector.is_thread_alive:
            logger.warning("AppCollector thread died, restarting...")
            self._app_collector._running = False
            self._app_collector.start()
            healthy = False

        # Check network collector thread
        if self._network_collector._running and not self._network_collector.is_thread_alive:
            logger.warning("NetworkCollector thread died, restarting...")
            self._network_collector._running = False
            self._network_collector.start()
            healthy = False

        return healthy

    # --------------------------------------------------
    # Periodic loops
    # --------------------------------------------------

    def _flush_loop(self):
        """Flush collector data every BATCH_SEND_INTERVAL seconds."""
        logger.debug(f"Flush loop started (interval={config.BATCH_SEND_INTERVAL}s)")

        while self._running:
            time.sleep(1)

            elapsed = time.time() - self._last_flush_time
            if elapsed >= config.BATCH_SEND_INTERVAL:
                try:
                    self._flush_collectors()
                except Exception as e:
                    logger.error(f"Flush error: {e}", exc_info=True)
                self._last_flush_time = time.time()

        logger.debug("Flush loop ended")

    def _session_update_loop(self):
        """Send session update every SESSION_UPDATE_INTERVAL seconds."""
        logger.debug(
            f"Session update loop started "
            f"(interval={config.SESSION_UPDATE_INTERVAL}s)"
        )

        last_update = time.time()

        while self._running:
            time.sleep(1)

            elapsed = time.time() - last_update
            if elapsed >= config.SESSION_UPDATE_INTERVAL:
                try:
                    self._buffer_session_update()
                except Exception as e:
                    logger.error(f"Session update error: {e}", exc_info=True)
                last_update = time.time()

        logger.debug("Session update loop ended")

    # --------------------------------------------------
    # Flush logic
    # --------------------------------------------------

    def _flush_collectors(self):
        """Collect data from all collectors and write to buffer."""
        logger.debug("Flushing collectors...")

        # Flush app usage
        app_records = self._app_collector.flush()
        if app_records:
            self._buffer_app_usage(app_records)
            self._update_session_totals_from_apps(app_records)

        # Flush network/domain data
        domain_records = self._network_collector.flush()
        if domain_records:
            self._buffer_domain_visits(domain_records)
            self._update_session_totals_from_domains(domain_records)

        logger.debug(
            f"Flush complete: {len(app_records)} app records, "
            f"{len(domain_records)} domain records"
        )

    def _update_session_totals_from_apps(self, app_records: list[dict]):
        """Update running session totals from flushed app data."""
        with self._lock:
            for record in app_records:
                self._total_active_sec += record.get("active_duration_sec", 0)
                self._total_idle_sec += record.get("idle_duration_sec", 0)

    def _update_session_totals_from_domains(self, domain_records: list[dict]):
        """Update running session totals from flushed domain data."""
        with self._lock:
            for record in domain_records:
                self._total_bytes_up += record.get("bytes_uploaded", 0)
                self._total_bytes_down += record.get("bytes_downloaded", 0)

    # --------------------------------------------------
    # Buffer payloads
    # --------------------------------------------------

    def _buffer_session_start(self):
        """Write initial session record to buffer."""
        payload = {
            "employee_id": self._employee_id,
            "device_mac": self._device_mac,
            "session_start": self._session_start,
            "session_end": None,
            "active_duration_sec": 0,
            "idle_duration_sec": 0,
            "bytes_uploaded": 0,
            "bytes_downloaded": 0,
            "avg_bandwidth_kbps": 0.0,
            "source": config.SOURCE,
        }
        self._buffer.insert_pending("pending_sessions", payload)
        logger.debug("Session start buffered")

    def _buffer_session_update(self):
        """Write session update record to buffer."""
        with self._lock:
            active = round(self._total_active_sec)
            idle = round(self._total_idle_sec)
            bytes_up = self._total_bytes_up
            bytes_down = self._total_bytes_down

        total_sec = active + idle
        avg_bw = 0.0
        if total_sec > 0:
            avg_bw = round((bytes_up + bytes_down) * 8 / total_sec / 1000, 2)

        payload = {
            "employee_id": self._employee_id,
            "device_mac": self._device_mac,
            "session_start": self._session_start,
            "session_end": None,
            "active_duration_sec": active,
            "idle_duration_sec": idle,
            "bytes_uploaded": bytes_up,
            "bytes_downloaded": bytes_down,
            "avg_bandwidth_kbps": avg_bw,
            "source": config.SOURCE,
        }
        self._buffer.insert_pending("pending_sessions", payload)
        logger.debug(f"Session update buffered (active={active}s, idle={idle}s)")

    def _buffer_session_end(self):
        """Write final session record to buffer."""
        session_end = datetime.now(timezone.utc).isoformat()

        with self._lock:
            active = round(self._total_active_sec)
            idle = round(self._total_idle_sec)
            bytes_up = self._total_bytes_up
            bytes_down = self._total_bytes_down

        total_sec = active + idle
        avg_bw = 0.0
        if total_sec > 0:
            avg_bw = round((bytes_up + bytes_down) * 8 / total_sec / 1000, 2)

        payload = {
            "employee_id": self._employee_id,
            "device_mac": self._device_mac,
            "session_start": self._session_start,
            "session_end": session_end,
            "active_duration_sec": active,
            "idle_duration_sec": idle,
            "bytes_uploaded": bytes_up,
            "bytes_downloaded": bytes_down,
            "avg_bandwidth_kbps": avg_bw,
            "source": config.SOURCE,
        }
        self._buffer.insert_pending("pending_sessions", payload)
        logger.info(f"Session end buffered (duration={active + idle}s)")

    def _buffer_app_usage(self, app_records: list[dict]):
        """Write app usage batch to buffer."""
        recorded_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "employee_id": self._employee_id,
            "device_mac": self._device_mac,
            "recorded_at": recorded_at,
            "apps": app_records,
        }
        self._buffer.insert_pending("pending_app_usage", payload)
        logger.debug(f"App usage buffered: {len(app_records)} apps")

    def _buffer_domain_visits(self, domain_records: list[dict]):
        """Write domain visit records to buffer using batch insert."""
        visited_at = datetime.now(timezone.utc).isoformat()

        payloads = []
        for record in domain_records:
            domain = record["domain"]
            category = self._categorizer.categorize_domain(domain)

            payload = {
                "employee_id": self._employee_id,
                "device_mac": self._device_mac,
                "app_name": record.get("app_name", "unknown"),
                "domain": domain,
                "category": category,
                "bytes_uploaded": record.get("bytes_uploaded", 0),
                "bytes_downloaded": record.get("bytes_downloaded", 0),
                "duration_sec": record.get("duration_sec", 0),
                "visited_at": visited_at,
            }
            payloads.append(payload)

        if payloads:
            self._buffer.insert_pending_batch("pending_domain_visits", payloads)

        logger.debug(f"Domain visits buffered: {len(payloads)} domains")

    def buffer_domain_visit(
        self,
        domain: str,
        app_name: str,
        bytes_uploaded: int = 0,
        bytes_downloaded: int = 0,
        duration_sec: int = 0,
    ):
        """
        Buffer a single domain visit record.
        Can be called externally for manual domain tracking.
        """
        clean_domain = self._categorizer.normalize_domain(domain)

        if not clean_domain:
            return

        if self._categorizer.is_ignored_domain(clean_domain):
            return

        category = self._categorizer.categorize_domain(clean_domain)
        visited_at = datetime.now(timezone.utc).isoformat()

        payload = {
            "employee_id": self._employee_id,
            "device_mac": self._device_mac,
            "app_name": app_name,
            "domain": clean_domain,
            "category": category,
            "bytes_uploaded": bytes_uploaded,
            "bytes_downloaded": bytes_downloaded,
            "duration_sec": duration_sec,
            "visited_at": visited_at,
        }
        self._buffer.insert_pending("pending_domain_visits", payload)

        # Update session totals
        with self._lock:
            self._total_bytes_up += bytes_uploaded
            self._total_bytes_down += bytes_downloaded

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def session_start(self) -> Optional[str]:
        return self._session_start

    def get_status(self) -> dict:
        """Get current session status for display."""
        with self._lock:
            return {
                "running": self._running,
                "employee_id": self._employee_id,
                "device_mac": self._device_mac,
                "session_start": self._session_start,
                "active_duration_sec": round(self._total_active_sec),
                "idle_duration_sec": round(self._total_idle_sec),
                "bytes_uploaded": self._total_bytes_up,
                "bytes_downloaded": self._total_bytes_down,
                "apps_tracked": self._app_collector.current_app_count,
                "domains_tracked": self._network_collector.current_domain_count,
                "dns_cache_size": self._network_collector.dns_cache_size,
                "pending_records": self._buffer.get_pending_count(),
            }

    @property
    def categorizer(self) -> Categorizer:
        """Expose categorizer for external use."""
        return self._categorizer