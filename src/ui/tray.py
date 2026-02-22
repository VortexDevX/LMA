"""
System Tray Icon.
Provides a minimal tray icon with status display and controls.
Uses pystray for cross-platform support.
"""

import sys
import threading
import logging
import webbrowser
from typing import Optional, Callable
from io import BytesIO

from src.config import config

logger = logging.getLogger("agent.ui.tray")

# Try to import pystray and PIL
_TRAY_AVAILABLE = False
try:
    import pystray  # type: ignore
    from PIL import Image, ImageDraw, ImageFont

    _TRAY_AVAILABLE = True
except ImportError:
    logger.warning(
        "pystray or Pillow not available. System tray disabled. "
        "Install with: pip install pystray Pillow"
    )


def is_tray_available() -> bool:
    """Check if system tray functionality is available."""
    return _TRAY_AVAILABLE


def _create_icon_image(color: str = "green") -> "Image.Image":
    """
    Create a simple colored circle icon for the tray.
    Colors: green (connected), yellow (buffering), red (error), gray (stopped)
    """
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))  # type: ignore
    draw = ImageDraw.Draw(image)  # type: ignore

    color_map = {
        "green": (76, 175, 80, 255),
        "yellow": (255, 193, 7, 255),
        "red": (244, 67, 54, 255),
        "gray": (158, 158, 158, 255),
    }

    fill = color_map.get(color, color_map["gray"])

    # Draw filled circle
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=fill,
    )

    # Draw "M" letter in center for "Monitor"
    try:
        font = ImageFont.load_default()  # type: ignore
    except Exception:
        font = None

    if font:
        text = "M"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (size - text_w) // 2
        text_y = (size - text_h) // 2
        draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    return image


class SystemTray:
    """
    System tray icon with status menu.

    Menu items:
    - Status line (read-only)
    - Employee name + ID (read-only)
    - Separator
    - Call it a day
    - View Dashboard (opens browser)
    - Auto-start toggle
    - Separator
    - About
    - Quit
    """

    def __init__(
        self,
        get_status_fn: Callable[[], dict],
        stop_fn: Callable[[], None],
    ):
        self._get_status = get_status_fn
        self._stop_fn = stop_fn

        self._icon: Optional["pystray.Icon"] = None  # type: ignore
        self._thread: Optional[threading.Thread] = None
        self._paused = False
        self._running = False

        # Callbacks that can be set by the agent core
        self.on_pause: Optional[Callable[[], None]] = None
        self.on_resume: Optional[Callable[[], None]] = None

    def start(self):
        """Start the system tray icon in a background thread."""
        if not _TRAY_AVAILABLE:
            logger.warning("System tray not available, skipping")
            return

        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_tray,
            name="SystemTrayThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("System tray started")

    def stop(self):
        """Stop the system tray icon."""
        self._running = False
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
        logger.info("System tray stopped")

    def update_icon(self, color: str):
        """Update the tray icon color (green/yellow/red/gray)."""
        if self._icon and _TRAY_AVAILABLE:
            try:
                self._icon.icon = _create_icon_image(color)
            except Exception as e:
                logger.debug(f"Failed to update tray icon: {e}")

    # --------------------------------------------------
    # Tray setup
    # --------------------------------------------------

    def _run_tray(self):
        """Create and run the tray icon (blocks until stopped)."""
        try:
            menu = pystray.Menu(  # type: ignore
                pystray.MenuItem(  # type: ignore
                    self._status_text,
                    None,
                    enabled=False,
                ),
                pystray.MenuItem(  # type: ignore
                    self._employee_text,
                    None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,  # type: ignore
                pystray.MenuItem(  # type: ignore
                    self._pause_text,
                    self._on_pause_toggle,
                ),
                pystray.MenuItem(  # type: ignore
                    "View Dashboard",
                    self._on_view_stats,
                ),
                pystray.MenuItem(  # type: ignore
                    self._autostart_text,
                    self._on_autostart_toggle,
                ),
                pystray.Menu.SEPARATOR,  # type: ignore
                pystray.MenuItem(  # type: ignore
                    self._about_text,
                    None,
                    enabled=False,
                ),
                pystray.MenuItem(  # type: ignore
                    "Quit Agent",
                    self._on_quit,
                ),
            )

            self._icon = pystray.Icon(  # type: ignore
                name="LocalMonitorAgent",
                icon=_create_icon_image("green"),
                title="Local Monitor Agent",
                menu=menu,
            )

            self._icon.run()  # type: ignore

        except Exception as e:
            logger.error(f"System tray error: {e}", exc_info=True)
        finally:
            self._running = False

    # --------------------------------------------------
    # Dynamic menu text
    # --------------------------------------------------

    def _status_text(self, item) -> str:
        """Generate status text for menu."""
        try:
            status = self._get_status()
            if self._paused:
                return "Status: Paused (data sent)"
            session = status.get("session", {})
            if session.get("running"):
                pending = session.get("pending_records", 0)
                if pending > 0:
                    return f"Status: Running ({pending} pending)"
                return "Status: Running"
            return "Status: Stopped"
        except Exception:
            return "Status: Unknown"

    def _employee_text(self, item) -> str:
        """Generate employee info text with name and ID."""
        try:
            status = self._get_status()
            name = status.get("employee_name", "Unknown")
            session = status.get("session", {})
            emp_id = session.get("employee_id", "?")
            return f"{name} (ID: {emp_id})"
        except Exception:
            return "Employee: Unknown"

    def _pause_text(self, item) -> str:
        """Generate call-it-a-day/resume text."""
        return "Resume Work" if self._paused else "Call it a day"

    def _autostart_text(self, item) -> str:
        """Generate auto-start toggle text."""
        try:
            from src.utils.autostart import is_autostart_enabled

            if is_autostart_enabled():
                return "\u2713 Auto-start Enabled"
            return "  Auto-start Disabled"
        except Exception:
            return "  Auto-start Unknown"

    def _about_text(self, item) -> str:
        """Generate about text."""
        return f"Monitor Agent v{config.AGENT_VERSION}"

    # --------------------------------------------------
    # Menu actions
    # --------------------------------------------------

    def _on_pause_toggle(self, icon, item):
        """Handle call-it-a-day/resume toggle. Pausing flushes data to backend."""
        self._paused = not self._paused

        if self._paused:
            logger.info("Employee called it a day - pausing monitoring and flushing data")
            self.update_icon("yellow")
            if self.on_pause:
                try:
                    self.on_pause()
                except Exception as e:
                    logger.error(f"Pause callback error: {e}")
        else:
            logger.info("Employee resuming work")
            self.update_icon("green")
            if self.on_resume:
                try:
                    self.on_resume()
                except Exception as e:
                    logger.error(f"Resume callback error: {e}")

        # Force menu refresh
        icon.update_menu()

    def _on_autostart_toggle(self, icon, item):
        """Handle auto-start enable/disable toggle."""
        try:
            from src.utils.autostart import (
                is_autostart_enabled,
                register_autostart,
                unregister_autostart,
            )

            if is_autostart_enabled():
                if unregister_autostart():
                    logger.info("Auto-start disabled by user")
                else:
                    logger.error("Failed to disable auto-start")
            else:
                if register_autostart():
                    logger.info("Auto-start enabled by user")
                else:
                    logger.error("Failed to enable auto-start")

            icon.update_menu()
        except Exception as e:
            logger.error(f"Auto-start toggle error: {e}")

    def _on_view_stats(self, icon, item):
        """Open the web dashboard in browser."""
        try:
            url = f"{config.API_BASE_URL}/dashboard"
            webbrowser.open(url)
            logger.info(f"Opened dashboard: {url}")
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")

    def _on_quit(self, icon, item):
        """Handle quit action."""
        logger.info("Quit requested from tray menu")
        self.stop()
        if self._stop_fn:
            self._stop_fn()

    # --------------------------------------------------
    # Properties
    # --------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused