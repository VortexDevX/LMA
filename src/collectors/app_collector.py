"""
Application Activity Collector.
Polls the foreground app every second, tracks focus duration,
idle time, and app switch frequency.
"""

import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Optional

from src.config import config
from src.platform import get_platform
from src.platform.base import ForegroundAppInfo

logger = logging.getLogger("agent.collector.app")


@dataclass
class AppRecord:
    """Accumulated usage data for a single app in one collection window."""
    app_name: str
    process_id: int
    active_duration_sec: float = 0.0
    idle_duration_sec: float = 0.0
    switch_count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0

    def to_dict(self) -> dict:
        return {
            "app_name": self.app_name,
            "process_id": self.process_id,
            "active_duration_sec": round(self.active_duration_sec),
            "idle_duration_sec": round(self.idle_duration_sec),
            "switch_count": self.switch_count,
        }


class AppCollector:
    """
    Tracks foreground application usage.

    Polls every APP_POLL_INTERVAL seconds (default 1s).
    Accumulates per-app stats in memory.
    Flush returns all records and resets for the next window.
    """

    def __init__(self):
        self._platform = get_platform()
        self._lock = threading.Lock()

        # Accumulator: keyed by app_name
        self._apps: dict[str, AppRecord] = {}

        # Previous poll state (for detecting switches)
        self._prev_app_name: Optional[str] = None
        self._prev_poll_time: float = 0.0

        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Load ignored apps list
        categories = config.load_categories()
        self._ignored_apps = set()
        for name in categories.get("ignored_apps", []):
            self._ignored_apps.add(name.lower().strip())

        logger.info(
            f"AppCollector initialized "
            f"(poll_interval={config.APP_POLL_INTERVAL}s, "
            f"idle_threshold={config.IDLE_THRESHOLD}s, "
            f"ignored_apps={len(self._ignored_apps)})"
        )

    def start(self):
        """Start the collector polling thread."""
        if self._running:
            logger.warning("AppCollector already running")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AppCollectorThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("AppCollector started")

    def stop(self):
        """Stop the collector polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("AppCollector stopped")

    def flush(self) -> list[dict]:
        """
        Return all accumulated app records and reset.
        Called by the session manager every BATCH_SEND_INTERVAL.

        Returns list of app dicts ready for API payload.
        Filters out apps with less than MIN_FOCUS_DURATION total time.
        """
        with self._lock:
            records = []
            for app_record in self._apps.values():
                total_time = app_record.active_duration_sec + app_record.idle_duration_sec
                if total_time < config.MIN_FOCUS_DURATION:
                    continue
                records.append(app_record.to_dict())

            # Reset accumulator
            self._apps.clear()
            self._prev_app_name = None

        if records:
            logger.debug(f"Flushed {len(records)} app records")

        return records

    def _poll_loop(self):
        """Main polling loop. Runs in a background thread."""
        logger.debug("Poll loop started")

        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"Poll error: {e}", exc_info=True)

            time.sleep(config.APP_POLL_INTERVAL)

        logger.debug("Poll loop ended")

    def _poll_once(self):
        """Single poll iteration: check foreground app and update stats."""
        now = time.time()
        elapsed = now - self._prev_poll_time if self._prev_poll_time > 0 else 0.0
        self._prev_poll_time = now

        # Skip if elapsed is unreasonably large (system sleep, etc.)
        if elapsed > 30:
            logger.debug(f"Large gap detected ({elapsed:.1f}s), skipping accumulation")
            elapsed = 0.0

        # Check if screen is locked
        try:
            if self._platform.is_screen_locked():
                self._prev_app_name = None
                return
        except Exception:
            pass

        # Get foreground app
        fg_app = self._platform.get_foreground_app()
        if fg_app is None:
            self._prev_app_name = None
            return

        # Check if ignored
        if self._is_ignored(fg_app):
            self._prev_app_name = None
            return

        # Check idle state
        idle_sec = self._platform.get_idle_duration_sec()
        is_idle = idle_sec >= config.IDLE_THRESHOLD

        # Session split: if idle too long, don't accumulate
        if idle_sec >= config.SESSION_SPLIT_IDLE:
            self._prev_app_name = None
            return

        # Update accumulator
        with self._lock:
            self._update_app_record(fg_app, elapsed, is_idle, now)

    def _update_app_record(
        self,
        fg_app: ForegroundAppInfo,
        elapsed: float,
        is_idle: bool,
        now: float,
    ):
        """Update or create the app record in the accumulator."""
        app_name = fg_app.app_name

        if app_name not in self._apps:
            self._apps[app_name] = AppRecord(
                app_name=app_name,
                process_id=fg_app.process_id,
                first_seen=now,
                last_seen=now,
            )

        record = self._apps[app_name]
        record.last_seen = now
        record.process_id = fg_app.process_id  # Update to latest PID

        # Accumulate time
        if elapsed > 0:
            if is_idle:
                record.idle_duration_sec += elapsed
            else:
                record.active_duration_sec += elapsed

        # Detect app switch
        if self._prev_app_name is not None and self._prev_app_name != app_name:
            record.switch_count += 1

        self._prev_app_name = app_name

    def _is_ignored(self, fg_app: ForegroundAppInfo) -> bool:
        """Check if this app should be ignored."""
        raw_lower = fg_app.raw_process_name.lower().strip()
        name_lower = fg_app.app_name.lower().strip()

        if raw_lower in self._ignored_apps:
            return True
        if name_lower in self._ignored_apps:
            return True

        # Also check without .exe
        if raw_lower.endswith(".exe"):
            stripped = raw_lower[:-4]
            if stripped in self._ignored_apps:
                return True

        return False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_thread_alive(self) -> bool:
        """Check if the collector thread is actually alive (not just flagged running)."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_app_count(self) -> int:
        """Number of unique apps currently tracked in this window."""
        with self._lock:
            return len(self._apps)