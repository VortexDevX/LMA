"""
Agent Core - Main orchestrator.
Ties together all modules: collectors, session manager, API sender, tray.
Manages the complete agent lifecycle.
"""

import sys
import os
import time
import signal
import logging
import logging.handlers
import atexit
from typing import Optional

from src.config import config
from src.storage.sqlite_buffer import SQLiteBuffer
from src.session.session_manager import SessionManager
from src.network.api_sender import APISender
from src.setup.first_launch import run_first_launch
from src.ui.tray import SystemTray, is_tray_available
from src.utils.autostart import is_autostart_enabled, register_autostart
from src.utils.updater import Updater

logger = logging.getLogger("agent.core")

# Watchdog interval (seconds)
WATCHDOG_INTERVAL = 30

# Memory check interval (seconds)
MEMORY_CHECK_INTERVAL = 900  # 15 minutes

# Memory warning threshold (MB)
MEMORY_WARNING_MB = 100


class AgentCore:
    """
    Main agent orchestrator.

    Startup sequence:
    1. Initialize logging
    2. Check single instance (lock file)
    3. Initialize SQLite buffer
    4. Migrate API key to secure storage
    5. Initialize API sender
    6. Check crash count / rollback
    7. Check if first launch -> run setup (CLI or GUI)
    8. Initialize session manager
    9. Start all components
    10. Start system tray
    11. Enter main loop (watchdog + memory + update checks)
    12. On shutdown: stop everything gracefully
    """

    def __init__(self):
        self._buffer: Optional[SQLiteBuffer] = None
        self._sender: Optional[APISender] = None
        self._session_manager: Optional[SessionManager] = None
        self._tray: Optional[SystemTray] = None
        self._updater: Optional[Updater] = None
        self._running = False
        self._exit_code = 0

    def run(self):
        """Main entry point. Blocks until shutdown."""
        try:
            self._setup_logging()
            self._log_startup_banner()
            self._check_single_instance()
            self._initialize_components()

            # Check crash count before proceeding
            self._check_crash_rollback()

            if not self._ensure_configured():
                logger.error("Setup not completed. Exiting.")
                self._exit_code = 1
                return self._exit_code

            self._register_shutdown_hooks()
            self._start_all()

            # Record clean start after successful startup
            Updater.record_clean_start(self._buffer)  # type: ignore

            self._main_loop()

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            self._exit_code = 1
            # Record crash
            if self._buffer:
                try:
                    Updater.record_crash(self._buffer)
                except Exception:
                    pass
        finally:
            self._shutdown()

        return self._exit_code

    # --------------------------------------------------
    # Setup
    # --------------------------------------------------

    def _setup_logging(self):
        """Configure logging with file and console handlers."""
        log_file = config.LOG_DIR / "agent.log"

        handlers = [
            logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            ),
        ]

        # Only add console handler if stdout is available (not windowed mode)
        if sys.stdout is not None:
            handlers.insert(0, logging.StreamHandler(sys.stdout))  # type: ignore

        logging.basicConfig(
            level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
            format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=handlers,
        )

    def _log_startup_banner(self):
        """Log startup information."""
        logger.info("=" * 60)
        logger.info(f"Local Monitoring Agent v{config.AGENT_VERSION}")
        logger.info(f"Platform: {sys.platform}")
        logger.info(f"Python: {sys.version.split()[0]}")
        logger.info(f"Data dir: {config.DATA_DIR}")
        logger.info(f"Database: {config.DB_PATH}")
        logger.info(f"API: {config.API_BASE_URL}")
        logger.info(f"Tray available: {is_tray_available()}")
        logger.info(f"Auto-start: {is_autostart_enabled()}")
        logger.info("=" * 60)

    def _check_single_instance(self):
        """Prevent multiple agent instances."""
        lock_file = config.LOCK_FILE

        if lock_file.exists():
            try:
                import psutil  # type: ignore

                old_pid = int(lock_file.read_text().strip())
                if psutil.pid_exists(old_pid):
                    logger.error(
                        f"Agent already running (PID {old_pid}). Exiting."
                    )
                    sys.exit(1)
                else:
                    logger.warning(
                        f"Stale lock file (PID {old_pid}). Removing."
                    )
                    lock_file.unlink()
            except (ValueError, Exception):
                lock_file.unlink(missing_ok=True)

        lock_file.write_text(str(os.getpid()))
        logger.debug(f"Lock file created: {lock_file}")

    def _initialize_components(self):
        """Create all core components."""
        logger.info("Initializing components...")

        self._buffer = SQLiteBuffer()
        logger.info(f"SQLite buffer ready ({self._buffer.db_size_mb:.2f} MB)")

        # Migrate API key before creating sender
        self._migrate_api_key()

        self._sender = APISender(self._buffer)
        logger.info("API sender ready")

        self._session_manager = SessionManager(self._buffer)
        logger.info("Session manager ready")

        # Updater
        self._updater = Updater(self._sender)
        logger.info("Updater ready")

        # System tray
        self._tray = SystemTray(
            get_status_fn=self.get_status,
            stop_fn=self._request_stop,
        )
        self._tray.on_pause = self._on_pause
        self._tray.on_resume = self._on_resume
        logger.info("System tray ready")

    def _migrate_api_key(self):
        """
        Migrate API key from plaintext .env to obfuscated storage in SQLite.
        On subsequent runs, load from DB instead of .env.
        """
        if not config.API_KEY or len(config.API_KEY) < 5:
            return

        try:
            from src.utils.crypto import get_machine_salt, obfuscate, deobfuscate

            salt = get_machine_salt()
            stored = self._buffer.get_config("api_key_enc")  # type: ignore

            if stored:
                try:
                    decrypted = deobfuscate(stored, salt)
                    if decrypted:
                        config.API_KEY = decrypted
                        logger.info("API key loaded from secure storage")
                        return
                except Exception as e:
                    logger.warning(
                        f"Failed to decrypt stored API key ({e}), "
                        f"re-encrypting from .env"
                    )

            encrypted = obfuscate(config.API_KEY, salt)
            self._buffer.set_config("api_key_enc", encrypted)  # type: ignore
            logger.info("API key migrated to secure storage")

        except Exception as e:
            logger.warning(f"API key migration skipped: {e}")

    def _check_crash_rollback(self):
        """Check if repeated crashes warrant a rollback to previous version."""
        if not self._buffer:
            return

        if Updater.should_rollback(self._buffer):
            logger.warning(
                f"Crash count exceeds threshold. Attempting rollback..."
            )
            if self._updater and self._updater.rollback():
                logger.info("Rollback successful. Restart required.")
                Updater.record_clean_start(self._buffer)
                # Don't exit here — let the current run continue with old code
                # The rollback replaces the exe on disk for next launch
            else:
                logger.warning("Rollback not possible. Resetting crash count.")
                Updater.record_clean_start(self._buffer)

    def _ensure_configured(self) -> bool:
        """
        Check if first launch setup is needed. Run it if so.
        Uses CLI when terminal is available, GUI wizard otherwise.
        """
        if self._session_manager.is_configured:  # type: ignore
            emp_id = self._session_manager.employee_id  # type: ignore
            mac = self._session_manager.device_mac  # type: ignore
            name = self._buffer.get_config("employee_name", "Unknown")  # type: ignore
            logger.info(
                f"Identity loaded: employee={emp_id} ({name}), "
                f"device={mac}"
            )
            return True

        logger.info("First launch detected. Running setup...")

        has_terminal = sys.stdin is not None and sys.stdin.isatty()

        if has_terminal:
            success = run_first_launch(self._buffer, self._sender)  # type: ignore

            if success:
                if register_autostart():
                    logger.info("Auto-start registered for boot")
                else:
                    logger.warning(
                        "Could not register auto-start "
                        "(may not be running as bundled exe)"
                    )
        else:
            from src.ui.setup_wizard import is_tk_available, run_setup_wizard

            if is_tk_available():
                logger.info("Launching GUI setup wizard...")
                success = run_setup_wizard(self._buffer, self._sender)  # type: ignore
            else:
                logger.error(
                    "No terminal and no GUI available. "
                    "Run the agent from command line first to complete setup."
                )
                return False

        if not success:
            return False

        # Reload identity into session manager
        self._session_manager = SessionManager(self._buffer)  # type: ignore
        return self._session_manager.is_configured

    # --------------------------------------------------
    # Lifecycle
    # --------------------------------------------------

    def _register_shutdown_hooks(self):
        """Register signal handlers and atexit for graceful shutdown."""
        atexit.register(self._cleanup_lock)

        def signal_handler(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"Received {sig_name}. Shutting down...")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _start_all(self):
        """Start all components."""
        logger.info("Starting all components...")

        self._sender.start()  # type: ignore
        self._session_manager.start()  # type: ignore

        if is_tray_available():
            self._tray.start()  # type: ignore

        self._running = True
        logger.info("All components started. Agent is running.")

    def _main_loop(self):
        """Keep the agent alive. Runs watchdog, memory, and update checks."""
        logger.info("Entering main loop (Ctrl+C to stop)")

        last_watchdog = time.time()
        last_memory_check = time.time()
        last_update_check = time.time()

        while self._running:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt in main loop")
                self._running = False
                break

            now = time.time()

            # Watchdog: check collector thread health
            if now - last_watchdog >= WATCHDOG_INTERVAL:
                self._watchdog_check()
                last_watchdog = now

            # Memory monitor
            if now - last_memory_check >= MEMORY_CHECK_INTERVAL:
                self._check_memory()
                last_memory_check = now

            # Update check
            if self._updater and self._updater.should_check():
                self._check_for_updates()
                last_update_check = now

    def _request_stop(self):
        """Request agent stop (called from tray quit)."""
        self._running = False

    def _shutdown(self):
        """Stop all components gracefully."""
        logger.info("Shutting down agent...")

        # Stop tray first (UI)
        if self._tray:
            try:
                self._tray.stop()
                logger.info("System tray stopped")
            except Exception as e:
                logger.error(f"Error stopping tray: {e}")

        if self._session_manager:
            try:
                self._session_manager.stop()
                logger.info("Session manager stopped")
            except Exception as e:
                logger.error(f"Error stopping session manager: {e}")

        if self._sender:
            try:
                self._sender.stop()
                logger.info("API sender stopped")
            except Exception as e:
                logger.error(f"Error stopping sender: {e}")

        if self._buffer:
            try:
                pending = self._buffer.get_pending_count()
                if pending > 0:
                    logger.warning(
                        f"{pending} records still pending "
                        f"(will be sent on next launch)"
                    )
                self._buffer.close()
                logger.info("SQLite buffer closed")
            except Exception as e:
                logger.error(f"Error closing buffer: {e}")

        self._cleanup_lock()
        logger.info("Agent stopped.")

    def _cleanup_lock(self):
        """Remove lock file."""
        try:
            config.LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # --------------------------------------------------
    # Watchdog
    # --------------------------------------------------

    def _watchdog_check(self):
        """Check collector threads are alive, restart if dead."""
        if self._session_manager and self._session_manager.is_running:
            healthy = self._session_manager.check_health()
            if not healthy:
                logger.warning("Watchdog: restarted dead collector thread(s)")

    # --------------------------------------------------
    # Memory monitor
    # --------------------------------------------------

    def _check_memory(self):
        """Log memory usage, warn if too high."""
        try:
            import psutil  # type: ignore

            process = psutil.Process()
            mem = process.memory_info()
            rss_mb = mem.rss / (1024 * 1024)

            if rss_mb > MEMORY_WARNING_MB:
                logger.warning(
                    f"High memory usage: {rss_mb:.1f} MB "
                    f"(threshold={MEMORY_WARNING_MB} MB)"
                )
            else:
                logger.debug(f"Memory usage: {rss_mb:.1f} MB")
        except Exception as e:
            logger.debug(f"Memory check failed: {e}")

    # --------------------------------------------------
    # Auto-update
    # --------------------------------------------------

    def _check_for_updates(self):
        """Check backend for a newer agent version."""
        if not self._updater:
            return

        try:
            info = self._updater.check_for_update()

            if info is None:
                return  # Up to date or check failed

            logger.info(
                f"Update v{info.version} available "
                f"(current: v{config.AGENT_VERSION})"
            )

            if not getattr(sys, "frozen", False):
                logger.info(
                    "Running from source — auto-update skipped. "
                    "Update manually."
                )
                return

            # Download
            new_binary = self._updater.download_update(info)
            if new_binary is None:
                logger.error("Update download failed")
                return

            # Verify checksum
            if not self._updater.verify_checksum(new_binary, info.checksum):
                logger.error("Update checksum verification failed")
                try:
                    new_binary.unlink()
                except Exception:
                    pass
                return

            # Apply
            logger.info("Applying update...")
            if self._updater.apply_update(new_binary):
                logger.info("Update applied. Shutting down for restart...")
                self._running = False  # Trigger shutdown → update script restarts
            else:
                logger.error("Update application failed")

        except Exception as e:
            logger.error(f"Update check error: {e}", exc_info=True)

    # --------------------------------------------------
    # Pause / Resume callbacks
    # --------------------------------------------------

    def _on_pause(self):
        """Called when user pauses monitoring from tray."""
        logger.info("Pausing monitoring...")
        
        # Log the pause event
        if self._buffer and self._session_manager:
            self._buffer.log_event(
                event_type="pause",
                employee_id=self._session_manager.employee_id,
                device_mac=self._session_manager.device_mac
            )
        
        # Flush all pending data to backend before pausing
        if self._sender:
            try:
                logger.info("Flushing pending data before pause...")
                self._sender._send_all_pending(bypass_cooldown=True)
            except Exception as e:
                logger.error(f"Failed to flush data on pause: {e}")
        
        # Stop monitoring
        if self._session_manager and self._session_manager.is_running:
            self._session_manager.stop()

    def _on_resume(self):
        """Called when user resumes monitoring from tray."""
        logger.info("Resuming monitoring...")
        
        # Log the resume event
        if self._buffer and self._session_manager:
            self._buffer.log_event(
                event_type="resume",
                employee_id=self._session_manager.employee_id,
                device_mac=self._session_manager.device_mac
            )
        
        # Resume monitoring
        if self._session_manager and not self._session_manager.is_running:
            self._session_manager.start()

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    def get_status(self) -> dict:
        """Get combined status from all components."""
        status = {
            "agent_version": config.AGENT_VERSION,
            "running": self._running,
            "autostart": is_autostart_enabled(),
        }

        # Memory info
        try:
            import psutil  # type: ignore

            process = psutil.Process()
            status["memory_mb"] = round(
                process.memory_info().rss / (1024 * 1024), 1
            )
        except Exception:
            status["memory_mb"] = None

        # Employee name from buffer
        if self._buffer:
            status["employee_name"] = self._buffer.get_config(
                "employee_name", "Unknown"
            )

        # Update info
        if self._updater and self._updater.available_update:
            status["update_available"] = self._updater.available_update.version
        else:
            status["update_available"] = None

        if self._session_manager:
            status["session"] = self._session_manager.get_status()

        if self._sender:
            status["sender"] = self._sender.get_status()

        if self._buffer:
            status["buffer"] = {
                "db_size_mb": self._buffer.db_size_mb,
                "pending_count": self._buffer.get_pending_count(),
                "stats": self._buffer.get_stats(),
            }

        if self._tray:
            status["tray"] = {
                "available": is_tray_available(),
                "running": self._tray.is_running,
                "paused": self._tray.is_paused,
            }

        return status