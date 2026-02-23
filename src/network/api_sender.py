"""
API Sender (Telemetry Uploader).
Reads pending records from SQLite buffer and sends them to the backend API.
Handles retries, backoff, network detection, auth cooldown, and error classification.
"""

import time
import threading
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

import requests

from src.config import config
from src.storage.sqlite_buffer import SQLiteBuffer, VALID_TABLES

logger = logging.getLogger("agent.sender")
MAX_DEBUG_TEXT_LEN = 400

# Auth cooldown after 401/403 (seconds)
AUTH_COOLDOWN_SEC = 300

# Endpoint mapping for each table
ENDPOINTS = {
    "pending_sessions": "/api/v1/telemetry/sessions",
    "pending_app_usage": "/api/v1/telemetry/app-usage",
    "pending_domain_visits": "/api/v1/telemetry/domain-visits",
}


class APISender:
    """
    Sends buffered telemetry data to the backend API.

    Runs periodically, reads from SQLite buffer, sends via HTTPS,
    and marks records as sent/failed based on response.
    """

    def __init__(self, buffer: SQLiteBuffer):
        self._buffer = buffer
        self._base_url = config.API_BASE_URL.rstrip("/")
        self._headers = config.api_headers
        self._timeout = 10

        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self._total_sent = 0
        self._total_failed = 0
        self._last_send_time: Optional[float] = None
        self._last_error: Optional[str] = None
        self._consecutive_failures = 0

        # Auth cooldown: skip send cycles until this timestamp
        self._auth_cooldown_until: float = 0.0

        # Session for connection pooling
        self._session = requests.Session()
        self._session.headers.update(self._headers)

        logger.info(
            f"APISender initialized (base_url={self._base_url}, "
            f"interval={config.BATCH_SEND_INTERVAL}s)"
        )

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def start(self):
        """Start the sender loop in a background thread."""
        if self._running:
            logger.warning("APISender already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._send_loop,
            name="APISenderThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("APISender started")

    def stop(self):
        """Stop the sender loop. Runs one final send cycle."""
        if not self._running:
            return

        logger.info("Stopping APISender, running final send cycle...")
        self._running = False

        # Final flush attempt — bypass auth cooldown
        try:
            self._send_all_pending(bypass_cooldown=True)
        except Exception as e:
            logger.error(f"Final send cycle failed: {e}")

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)

        self._session.close()
        logger.info(
            f"APISender stopped (total_sent={self._total_sent}, "
            f"total_failed={self._total_failed})"
        )

    # --------------------------------------------------
    # Send loop
    # --------------------------------------------------

    def _send_loop(self):
        """Main sender loop. Runs every BATCH_SEND_INTERVAL."""
        logger.debug("Send loop started")
        last_send = 0.0
        last_cleanup = time.time()

        while self._running:
            time.sleep(1)

            # Send cycle
            elapsed = time.time() - last_send
            if elapsed >= config.BATCH_SEND_INTERVAL:
                try:
                    self._send_all_pending()
                except Exception as e:
                    logger.error(f"Send cycle error: {e}", exc_info=True)
                last_send = time.time()

            # Cleanup old sent records every hour
            cleanup_elapsed = time.time() - last_cleanup
            if cleanup_elapsed >= 3600:
                try:
                    self._buffer.cleanup_sent(older_than_hours=24)
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
                last_cleanup = time.time()

        logger.debug("Send loop ended")

    def _send_all_pending(self, bypass_cooldown: bool = False):
        """Send all pending and retryable records across all tables."""
        if not self._is_network_available():
            logger.debug("Network unavailable, skipping send cycle")
            return

        # Check auth cooldown
        if not bypass_cooldown and time.time() < self._auth_cooldown_until:
            remaining = int(self._auth_cooldown_until - time.time())
            logger.debug(f"Auth cooldown active, skipping ({remaining}s remaining)")
            return

        total_sent = 0
        total_failed = 0
        auth_failed = False

        for table in VALID_TABLES:
            if auth_failed:
                break

            # Send pending records
            sent, failed, auth_err = self._send_table_records(table, retry=False)
            total_sent += sent
            total_failed += failed
            if auth_err:
                auth_failed = True
                break

            # Send retryable (previously failed) records
            sent, failed, auth_err = self._send_table_records(table, retry=True)
            total_sent += sent
            total_failed += failed
            if auth_err:
                auth_failed = True
                break

        if total_sent > 0 or total_failed > 0:
            logger.info(
                f"Send cycle complete: {total_sent} sent, {total_failed} failed"
            )

        # Track last successful sync
        if total_sent > 0:
            self._buffer.set_config(
                "last_successful_sync",
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )

    def _send_table_records(
        self, table: str, retry: bool = False
    ) -> tuple[int, int, bool]:
        """
        Send records from a single table.
        Returns (sent_count, failed_count, auth_failed).
        Uses batch marking for efficiency.
        """
        if retry:
            records = self._buffer.get_retryable(table, limit=20)
        else:
            records = self._buffer.get_pending(table, limit=50)

        if not records:
            return 0, 0, False

        endpoint = ENDPOINTS.get(table)
        if endpoint is None:
            logger.error(f"No endpoint configured for table: {table}")
            return 0, 0, False

        url = f"{self._base_url}{endpoint}"

        # Collect record IDs by outcome
        sent_ids: list[int] = []
        failed_ids: list[int] = []
        perm_failed_ids: list[int] = []
        auth_failed = False

        for record in records:
            result = self._send_single_record(url, table, record)

            if result == "sent":
                sent_ids.append(record.id)
            elif result == "auth_error":
                failed_ids.append(record.id)
                auth_failed = True
                break  # Stop entire cycle on auth error
            elif result == "perm_failed":
                perm_failed_ids.append(record.id)
            else:  # "failed"
                failed_ids.append(record.id)

            # Small delay between requests
            time.sleep(0.05)

        # Batch update statuses
        if sent_ids:
            self._buffer.mark_sent_batch(table, sent_ids) # type: ignore
            self._total_sent += len(sent_ids)
            self._last_send_time = time.time()

        if perm_failed_ids:
            self._buffer.mark_permanently_failed_batch(table, perm_failed_ids) # type: ignore
            self._total_failed += len(perm_failed_ids)

        if failed_ids:
            self._buffer.mark_failed_batch(table, failed_ids) # type: ignore
            self._total_failed += len(failed_ids)

        # Update consecutive failures / last error
        fail_count = len(failed_ids) + len(perm_failed_ids)
        if fail_count > 0:
            self._consecutive_failures += fail_count
        elif sent_ids:
            self._consecutive_failures = 0
            self._last_error = None

        return len(sent_ids), fail_count, auth_failed

    # --------------------------------------------------
    # Single record sending
    # --------------------------------------------------

    def _send_single_record(self, url: str, table: str, record) -> str:
        """
        Send a single record to the API.
        Returns: "sent", "failed", "perm_failed", or "auth_error".
        """
        try:
            response = self._session.post(
                url,
                json=record.payload,
                timeout=self._timeout,
            )
            return self._classify_response(response, table, record)

        except requests.exceptions.Timeout:
            logger.warning(
                f"Timeout sending {table}:{record.id} to {url} "
                f"(retry_count={record.retry_count})"
            )
            return self._classify_failure(record)

        except requests.exceptions.ConnectionError:
            logger.warning(
                f"Connection error sending {table}:{record.id} to {url} "
                f"(retry_count={record.retry_count})"
            )
            return self._classify_failure(record)

        except requests.exceptions.RequestException as e:
            logger.error(
                f"Request error sending {table}:{record.id}: {e} "
                f"(retry_count={record.retry_count})"
            )
            return self._classify_failure(record)

        except Exception as e:
            logger.error(
                f"Unexpected error sending {table}:{record.id}: {e} "
                f"(retry_count={record.retry_count})"
            )
            return self._classify_failure(record)

    def _classify_response(self, response, table: str, record) -> str:
        """
        Classify the API response into an outcome.
        Returns: "sent", "failed", "perm_failed", or "auth_error".
        """
        status = response.status_code

        # Success
        if 200 <= status < 300:
            logger.debug(f"Sent {table}:{record.id} (HTTP {status})")
            return "sent"

        # Bad request — data is invalid, don't retry
        if status == 400:
            logger.warning(
                f"Bad request for {table}:{record.id} (HTTP 400): "
                f"{self._truncate_text(response.text)}"
            )
            return "perm_failed"

        # Auth error — enter cooldown, stop cycle
        if status in (401, 403):
            logger.error(
                f"Authentication error (HTTP {status}). "
                f"Entering auth cooldown ({AUTH_COOLDOWN_SEC}s)."
            )
            self._auth_cooldown_until = time.time() + AUTH_COOLDOWN_SEC
            self._last_error = f"Auth error: HTTP {status}"
            return "auth_error"

        # Not found — endpoint doesn't exist, don't retry
        if status == 404:
            logger.error(f"Endpoint not found: {response.url} (HTTP 404)")
            return "perm_failed"

        # Rate limited
        if status == 429:
            retry_after = response.headers.get("Retry-After", "60")
            logger.warning(f"Rate limited (HTTP 429). Retry after {retry_after}s")
            self._last_error = f"Rate limited: retry after {retry_after}s"
            return "failed"

        # Server error — retry
        if 500 <= status < 600:
            logger.warning(
                f"Server error for {table}:{record.id} (HTTP {status}) "
                f"response={self._truncate_text(response.text)}"
            )
            return self._classify_failure(record)

        # Unknown status
        logger.warning(
            f"Unexpected status {status} for {table}:{record.id}: "
            f"{self._truncate_text(response.text)}"
        )
        return self._classify_failure(record)

    def _classify_failure(self, record) -> str:
        """
        Decide if a failed record should be retried or permanently failed.
        Based on current retry_count vs MAX_RETRIES.
        """
        if record.retry_count >= config.MAX_RETRIES - 1:
            return "perm_failed"
        return "failed"

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _truncate_text(self, text: str, max_len: int = MAX_DEBUG_TEXT_LEN) -> str:
        """Return a compact single-line debug snippet."""
        if not text:
            return "<empty>"
        compact = " ".join(text.split())
        if len(compact) <= max_len:
            return compact
        return f"{compact[:max_len]}..."

    def _payload_debug(self, payload: dict) -> str:
        """Return safe payload summary for logs."""
        keys = sorted(payload.keys())
        sample = {
            "employee_id": payload.get("employee_id"),
            "device_mac": payload.get("device_mac"),
            "domain": payload.get("domain"),
            "app_name": payload.get("app_name"),
        }
        return f"keys={keys}, sample={sample}"

    # --------------------------------------------------
    # Network detection
    # --------------------------------------------------

    def _is_network_available(self) -> bool:
        """Quick check if network connectivity is available."""
        try:
            parsed = urlparse(self._base_url)
            host = parsed.hostname or "8.8.8.8"
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            return True
        except (socket.timeout, socket.error, OSError):
            return False

    # --------------------------------------------------
    # Manual send (for first launch, device registration, etc.)
    # --------------------------------------------------

    def send_immediate(self, endpoint: str, payload: dict) -> Optional[dict]:
        """
        Send a single request immediately (not buffered).
        Used for auth verification, device registration, etc.

        Returns response JSON on success, None on failure.
        """
        url = f"{self._base_url}{endpoint}"

        try:
            response = self._session.post(
                url,
                json=payload,
                timeout=self._timeout,
            )

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError:
                    return {"status": "ok", "code": response.status_code}

            logger.warning(
                f"Immediate send failed: {url} "
                f"(HTTP {response.status_code}): {response.text[:200]}"
            )
            return None

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on immediate send to {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Connection error on immediate send to {url}")
            return None
        except Exception as e:
            logger.error(f"Immediate send error: {e}")
            return None

    def get_immediate(self, endpoint: str) -> Optional[dict]:
        """
        Send a GET request immediately.
        Used for config fetching, version checks, etc.

        Returns response JSON on success, None on failure.
        """
        url = f"{self._base_url}{endpoint}"

        try:
            response = self._session.get(
                url,
                timeout=self._timeout,
            )

            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError:
                    return {"status": "ok", "code": response.status_code}

            return None

        except Exception as e:
            logger.debug(f"GET request failed: {url}: {e}")
            return None

    def get_immediate_raw(self, endpoint: str) -> tuple[int | None, str]:
        """
        Send a GET request and return (status_code, response_text).
        status_code is None if request failed before response.
        """
        url = f"{self._base_url}{endpoint}"
        try:
            response = self._session.get(url, timeout=self._timeout)
            return response.status_code, response.text
        except Exception as e:
            logger.debug(f"GET request failed: {url}: {e}")
            return None, str(e)

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """Get sender status for display."""
        now = time.time()
        auth_cooldown_active = now < self._auth_cooldown_until
        return {
            "running": self._running,
            "total_sent": self._total_sent,
            "total_failed": self._total_failed,
            "last_send_time": self._last_send_time,
            "last_error": self._last_error,
            "consecutive_failures": self._consecutive_failures,
            "auth_cooldown": auth_cooldown_active,
            "auth_cooldown_remaining": max(0, int(self._auth_cooldown_until - now)) if auth_cooldown_active else 0,
            "network_available": self._is_network_available(),
            "pending_count": self._buffer.get_pending_count(),
        }

    def force_send(self):
        """Trigger an immediate send cycle (outside normal interval)."""
        logger.info("Force send triggered")
        try:
            self._send_all_pending(bypass_cooldown=True)
        except Exception as e:
            logger.error(f"Force send failed: {e}")
