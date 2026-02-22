"""
macOS-specific platform implementation.
Uses subprocess calls to system utilities and psutil.
"""

import subprocess
import socket
import logging
import uuid
import platform
import re
from typing import Optional

import psutil

from src.platform.base import (
    PlatformBase,
    ForegroundAppInfo,
    NetworkConnection,
    SystemInfo,
)

logger = logging.getLogger("agent.platform.macos")


# Known macOS app name mappings
_APP_NAME_MAP = {
    "code": "VSCode",
    "google chrome": "Chrome",
    "firefox": "Firefox",
    "safari": "Safari",
    "brave browser": "Brave",
    "microsoft edge": "Edge",
    "slack": "Slack",
    "microsoft teams": "Teams",
    "discord": "Discord",
    "spotify": "Spotify",
    "iterm2": "iTerm2",
    "terminal": "Terminal",
    "finder": "Finder",
    "mail": "Mail",
    "messages": "Messages",
    "zoom.us": "Zoom",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "figma": "Figma",
    "postman": "Postman",
    "microsoft word": "Word",
    "microsoft excel": "Excel",
    "microsoft powerpoint": "PowerPoint",
    "microsoft outlook": "Outlook",
}


class MacOSPlatform(PlatformBase):
    """macOS implementation using system utilities + psutil."""

    def __init__(self):
        self._process_cache = {}
        self._has_pyobjc = self._check_pyobjc()
        logger.info(f"macOS platform initialized (pyobjc available: {self._has_pyobjc})")

    def _check_pyobjc(self) -> bool:
        """Check if pyobjc is available for native API access."""
        try:
            import AppKit  # type: ignore # noqa: F401
            return True
        except ImportError:
            return False

    # --- Foreground App ---

    def get_foreground_app(self) -> Optional[ForegroundAppInfo]:
        # Try pyobjc first (faster, more reliable)
        if self._has_pyobjc:
            return self._get_foreground_pyobjc()
        return self._get_foreground_osascript()

    def _get_foreground_pyobjc(self) -> Optional[ForegroundAppInfo]:
        try:
            from AppKit import NSWorkspace # type: ignore

            workspace = NSWorkspace.sharedWorkspace()
            active_app = workspace.activeApplication()

            if not active_app:
                return None

            app_name = active_app.get("NSApplicationName", "unknown")
            pid = active_app.get("NSApplicationProcessIdentifier", 0)

            return ForegroundAppInfo(
                app_name=self.normalize_app_name(app_name),
                process_id=pid,
                raw_process_name=app_name,
            )
        except Exception as e:
            logger.debug(f"pyobjc foreground detection failed: {e}")
            return self._get_foreground_osascript()

    def _get_foreground_osascript(self) -> Optional[ForegroundAppInfo]:
        try:
            script = (
                'tell application "System Events" to get '
                "{name, unix id} of first application process whose frontmost is true"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return None

            # Output format: "AppName, 12345"
            parts = result.stdout.strip().split(", ")
            if len(parts) < 2:
                return None

            app_name = parts[0].strip()
            pid = int(parts[1].strip())

            return ForegroundAppInfo(
                app_name=self.normalize_app_name(app_name),
                process_id=pid,
                raw_process_name=app_name,
            )

        except subprocess.TimeoutExpired:
            logger.debug("osascript timed out getting foreground app")
            return None
        except Exception as e:
            logger.debug(f"osascript foreground detection failed: {e}")
            return None

    # --- Idle Detection ---

    def get_idle_duration_sec(self) -> float:
        # Try Quartz framework first
        if self._has_pyobjc:
            return self._get_idle_quartz()
        return self._get_idle_ioreg()

    def _get_idle_quartz(self) -> float:
        try:
            from Quartz.CoreGraphics import CGEventSourceSecondsSinceLastEventType # type: ignore

            # kCGEventSourceStateCombinedSessionState = 0
            # kCGAnyInputEventType = ~0 (all events)
            idle = CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF)
            return max(0.0, idle)
        except Exception:
            return self._get_idle_ioreg()

    def _get_idle_ioreg(self) -> float:
        try:
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
                capture_output=True,
                text=True,
                timeout=3,
            )

            if result.returncode != 0:
                return 0.0

            # Look for HIDIdleTime in output
            match = re.search(r'"HIDIdleTime"\s*=\s*(\d+)', result.stdout)
            if match:
                # Value is in nanoseconds
                idle_ns = int(match.group(1))
                return idle_ns / 1_000_000_000.0

            return 0.0

        except Exception as e:
            logger.debug(f"ioreg idle detection failed: {e}")
            return 0.0

    # --- Screen Lock ---

    def is_screen_locked(self) -> bool:
        try:
            if self._has_pyobjc:
                from Quartz import CGSessionCopyCurrentDictionary # type: ignore

                session = CGSessionCopyCurrentDictionary()
                if session:
                    return session.get("CGSSessionScreenIsLocked", False)

            # Fallback: check if loginwindow is in front
            result = subprocess.run(
                [
                    "python3", "-c",
                    "import Quartz; d=Quartz.CGSessionCopyCurrentDictionary(); "
                    "print(d.get('CGSSessionScreenIsLocked', False) if d else False)"
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.stdout.strip().lower() == "true"

        except Exception:
            return False

    # --- System Info ---

    def get_system_info(self) -> SystemInfo:
        return SystemInfo(
            mac_address=self.get_mac_address(),
            hostname=self.get_hostname(),
            local_ip=self.get_local_ip(),
            os_name="macos",
            os_version=platform.mac_ver()[0],
        )

    def get_mac_address(self) -> str:
        try:
            # Use ifconfig to get en0 MAC (primary interface on macOS)
            result = subprocess.run(
                ["ifconfig", "en0"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            match = re.search(r"ether\s+([0-9a-f:]{17})", result.stdout)
            if match:
                return match.group(1)

            # Fallback to uuid method
            mac_int = uuid.getnode()
            return ":".join(
                ["{:02x}".format((mac_int >> i) & 0xFF) for i in range(0, 48, 8)][::-1]
            )
        except Exception:
            return "00:00:00:00:00:00"

    def get_hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "UNKNOWN"

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            try:
                return socket.gethostbyname(socket.gethostname())
            except Exception:
                return "127.0.0.1"

    # --- Network Connections ---

    def get_active_connections(self) -> list[NetworkConnection]:
        connections = []
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status != "ESTABLISHED":
                    continue
                if not conn.raddr:
                    continue
                remote_port = conn.raddr.port
                if remote_port not in (80, 443, 8080, 8443):
                    continue

                pid = conn.pid
                if pid is None or pid == 0:
                    continue

                proc_name = self.get_process_name(pid)
                if proc_name is None:
                    proc_name = "unknown"

                family = "ipv4" if conn.family.name == "AF_INET" else "ipv6"

                connections.append(
                    NetworkConnection(
                        pid=pid,
                        process_name=self.normalize_app_name(proc_name),
                        remote_ip=conn.raddr.ip,
                        remote_port=remote_port,
                        status=conn.status,
                        family=family,
                    )
                )

        except (psutil.AccessDenied, PermissionError) as e:
            logger.warning(f"Permission denied reading network connections: {e}")
        except Exception as e:
            logger.error(f"Failed to get network connections: {e}")

        return connections

    # --- Process Utilities ---

    def get_process_name(self, pid: int) -> Optional[str]:
        if pid in self._process_cache:
            return self._process_cache[pid]

        try:
            proc = psutil.Process(pid)
            name = proc.name()
            self._process_cache[pid] = name

            if len(self._process_cache) > 500:
                keys = list(self._process_cache.keys())[:100]
                for k in keys:
                    del self._process_cache[k]

            return name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def normalize_app_name(self, raw_name: str) -> str:
        if not raw_name:
            return "unknown"

        lower = raw_name.lower().strip()

        if lower in _APP_NAME_MAP:
            return _APP_NAME_MAP[lower]

        # Strip common macOS suffixes
        for suffix in (".app", " helper", " renderer"):
            if lower.endswith(suffix):
                lower = lower[: -len(suffix)]

        if lower:
            return lower[0].upper() + lower[1:]

        return "unknown"

    def clear_process_cache(self):
        self._process_cache.clear()