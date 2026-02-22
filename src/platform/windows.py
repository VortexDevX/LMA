"""
Windows-specific platform implementation.
Uses ctypes for Win32 API, psutil for process/network info.
"""

import ctypes
import ctypes.wintypes
import socket
import logging
import uuid
import platform
from typing import Optional

import psutil

from src.platform.base import (
    PlatformBase,
    ForegroundAppInfo,
    NetworkConnection,
    SystemInfo,
)

logger = logging.getLogger("agent.platform.windows")


# Win32 API structures and constants
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


# Known process name mappings for cleaner display
_APP_NAME_MAP = {
    "code.exe": "VSCode",
    "code": "VSCode",
    "msedge.exe": "Edge",
    "chrome.exe": "Chrome",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "slack.exe": "Slack",
    "teams.exe": "Teams",
    "discord.exe": "Discord",
    "spotify.exe": "Spotify",
    "notepad++.exe": "Notepad++",
    "notepad.exe": "Notepad",
    "explorer.exe": "Explorer",
    "windowsterminal.exe": "Windows Terminal",
    "wt.exe": "Windows Terminal",
    "powershell.exe": "PowerShell",
    "cmd.exe": "CMD",
    "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA",
    "pycharm64.exe": "PyCharm",
    "webstorm64.exe": "WebStorm",
    "postman.exe": "Postman",
    "figma.exe": "Figma",
    "notion.exe": "Notion",
    "obsidian.exe": "Obsidian",
    "excel.exe": "Excel",
    "winword.exe": "Word",
    "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook",
    "zoom.exe": "Zoom",
    "vlc.exe": "VLC",
}


class WindowsPlatform(PlatformBase):
    """Windows implementation using Win32 API + psutil."""

    def __init__(self):
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._process_cache = {}  # pid -> process_name cache
        logger.info("Windows platform initialized")

    # --- Foreground App ---

    def get_foreground_app(self) -> Optional[ForegroundAppInfo]:
        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return None

            # Get process ID from window handle
            pid = ctypes.wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid_val = pid.value

            if pid_val == 0:
                return None

            # Get process name
            raw_name = self.get_process_name(pid_val)
            if raw_name is None:
                return None

            display_name = self.normalize_app_name(raw_name)

            return ForegroundAppInfo(
                app_name=display_name,
                process_id=pid_val,
                raw_process_name=raw_name,
            )

        except Exception as e:
            logger.debug(f"Failed to get foreground app: {e}")
            return None

    # --- Idle Detection ---

    def get_idle_duration_sec(self) -> float:
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)

            if not self._user32.GetLastInputInfo(ctypes.byref(lii)):
                return 0.0

            tick_count = self._kernel32.GetTickCount()
            elapsed_ms = tick_count - lii.dwTime

            # Handle tick count overflow (happens after ~49.7 days)
            if elapsed_ms < 0:
                elapsed_ms += 0xFFFFFFFF

            return elapsed_ms / 1000.0

        except Exception as e:
            logger.debug(f"Failed to get idle duration: {e}")
            return 0.0

    # --- Screen Lock ---

    def is_screen_locked(self) -> bool:
        try:
            # Check if a "lock screen" process is running
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if name in ("logonui.exe", "lockapp.exe"):
                    return True
            return False
        except Exception:
            return False

    # --- System Info ---

    def get_system_info(self) -> SystemInfo:
        return SystemInfo(
            mac_address=self.get_mac_address(),
            hostname=self.get_hostname(),
            local_ip=self.get_local_ip(),
            os_name="windows",
            os_version=platform.version(),
        )

    def get_mac_address(self) -> str:
        try:
            mac_int = uuid.getnode()
            mac_str = ":".join(
                ["{:02x}".format((mac_int >> i) & 0xFF) for i in range(0, 48, 8)][::-1]
            )
            return mac_str
        except Exception:
            return "00:00:00:00:00:00"

    def get_hostname(self) -> str:
        try:
            return socket.gethostname()
        except Exception:
            return "UNKNOWN"

    def get_local_ip(self) -> str:
        try:
            # Connect to external address to determine local IP
            # Does not actually send data
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
                # Only ESTABLISHED TCP connections
                if conn.status != "ESTABLISHED":
                    continue

                # Only HTTP/HTTPS
                if not conn.raddr:
                    continue
                remote_port = conn.raddr.port
                if remote_port not in (80, 443, 8080, 8443):
                    continue

                # Get process name
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
        # Check cache first
        if pid in self._process_cache:
            return self._process_cache[pid]

        try:
            proc = psutil.Process(pid)
            name = proc.name()
            self._process_cache[pid] = name

            # Limit cache size
            if len(self._process_cache) > 500:
                # Remove oldest entries (first 100)
                keys = list(self._process_cache.keys())[:100]
                for k in keys:
                    del self._process_cache[k]

            return name

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
        except Exception:
            return None

    def normalize_app_name(self, raw_name: str) -> str:
        if not raw_name:
            return "unknown"

        lower = raw_name.lower().strip()

        # Check known mappings first
        if lower in _APP_NAME_MAP:
            return _APP_NAME_MAP[lower]

        # Strip .exe extension
        if lower.endswith(".exe"):
            lower = lower[:-4]

        # Capitalize first letter
        if lower:
            return lower[0].upper() + lower[1:]

        return "unknown"

    def clear_process_cache(self):
        """Clear the process name cache."""
        self._process_cache.clear()