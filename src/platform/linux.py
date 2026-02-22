"""
Linux-specific platform implementation.
Uses /proc filesystem, xdotool/xprintidle, and psutil.
"""

import subprocess
import socket
import logging
import uuid
import platform
import re
import os
from pathlib import Path
from typing import Optional

import psutil

from src.platform.base import (
    PlatformBase,
    ForegroundAppInfo,
    NetworkConnection,
    SystemInfo,
)

logger = logging.getLogger("agent.platform.linux")


_APP_NAME_MAP = {
    "code": "VSCode",
    "google-chrome": "Chrome",
    "chromium-browser": "Chromium",
    "firefox": "Firefox",
    "firefox-esr": "Firefox",
    "brave-browser": "Brave",
    "microsoft-edge": "Edge",
    "slack": "Slack",
    "discord": "Discord",
    "spotify": "Spotify",
    "gnome-terminal": "Terminal",
    "konsole": "Terminal",
    "xterm": "Terminal",
    "alacritty": "Alacritty",
    "kitty": "Kitty",
    "tilix": "Tilix",
    "nautilus": "Files",
    "thunar": "Files",
    "nemo": "Files",
    "dolphin": "Files",
    "thunderbird": "Thunderbird",
    "libreoffice": "LibreOffice",
    "soffice.bin": "LibreOffice",
    "telegram-desktop": "Telegram",
    "obs": "OBS Studio",
    "vlc": "VLC",
    "gimp": "GIMP",
    "inkscape": "Inkscape",
    "blender": "Blender",
    "postman": "Postman",
    "notion-app": "Notion",
    "obsidian": "Obsidian",
}


class LinuxPlatform(PlatformBase):
    """Linux implementation using X11 tools + /proc + psutil."""

    def __init__(self):
        self._process_cache = {}
        self._display_server = self._detect_display_server()
        self._has_xdotool = self._check_command("xdotool")
        self._has_xprintidle = self._check_command("xprintidle")
        logger.info(
            f"Linux platform initialized "
            f"(display: {self._display_server}, "
            f"xdotool: {self._has_xdotool}, "
            f"xprintidle: {self._has_xprintidle})"
        )

    def _detect_display_server(self) -> str:
        """Detect if running X11 or Wayland."""
        session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session_type == "wayland":
            return "wayland"
        if session_type == "x11":
            return "x11"
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        if os.environ.get("DISPLAY"):
            return "x11"
        return "unknown"

    def _check_command(self, cmd: str) -> bool:
        """Check if a command-line tool is available."""
        try:
            result = subprocess.run(
                ["which", cmd],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.returncode == 0
        except Exception:
            return False

    # --- Foreground App ---

    def get_foreground_app(self) -> Optional[ForegroundAppInfo]:
        if self._display_server == "x11" and self._has_xdotool:
            return self._get_foreground_x11()
        elif self._display_server == "wayland":
            return self._get_foreground_wayland()
        return self._get_foreground_proc()

    def _get_foreground_x11(self) -> Optional[ForegroundAppInfo]:
        try:
            # Get active window ID
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return None

            window_id = result.stdout.strip()

            # Get PID of window
            result = subprocess.run(
                ["xdotool", "getwindowpid", window_id],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                return None

            pid = int(result.stdout.strip())
            raw_name = self.get_process_name(pid)
            if raw_name is None:
                return None

            return ForegroundAppInfo(
                app_name=self.normalize_app_name(raw_name),
                process_id=pid,
                raw_process_name=raw_name,
            )

        except Exception as e:
            logger.debug(f"X11 foreground detection failed: {e}")
            return None

    def _get_foreground_wayland(self) -> Optional[ForegroundAppInfo]:
        """
        Wayland foreground detection is compositor-dependent.
        Try common methods: swaymsg (Sway), gdbus (GNOME).
        """
        # Try swaymsg for Sway/i3-like compositors
        try:
            result = subprocess.run(
                ["swaymsg", "-t", "get_tree"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                import json
                tree = json.loads(result.stdout)
                focused = self._find_focused_sway(tree)
                if focused:
                    pid = focused.get("pid", 0)
                    app_id = focused.get("app_id", "") or focused.get("name", "unknown")
                    raw_name = self.get_process_name(pid) if pid else app_id
                    return ForegroundAppInfo(
                        app_name=self.normalize_app_name(raw_name or app_id),
                        process_id=pid,
                        raw_process_name=raw_name or app_id,
                    )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        except Exception as e:
            logger.debug(f"Sway detection failed: {e}")

        # Fallback: read /proc for largest CPU consumer (rough heuristic)
        return self._get_foreground_proc()

    def _find_focused_sway(self, node: dict) -> Optional[dict]:
        """Recursively find the focused node in sway tree."""
        if node.get("focused"):
            return node
        for child in node.get("nodes", []) + node.get("floating_nodes", []):
            result = self._find_focused_sway(child)
            if result:
                return result
        return None

    def _get_foreground_proc(self) -> Optional[ForegroundAppInfo]:
        """
        Last resort: find the process using most CPU that looks like a GUI app.
        This is imprecise but better than nothing.
        """
        try:
            gui_procs = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent"]):
                info = proc.info
                name = (info.get("name") or "").lower()
                # Skip system processes
                if name in ("systemd", "kworker", "init", "bash", "sh", "zsh"):
                    continue
                gui_procs.append(info)

            if not gui_procs:
                return None

            # Sort by CPU usage, take top one
            gui_procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
            top = gui_procs[0]

            return ForegroundAppInfo(
                app_name=self.normalize_app_name(top["name"]),
                process_id=top["pid"],
                raw_process_name=top["name"],
            )

        except Exception as e:
            logger.debug(f"Proc-based foreground detection failed: {e}")
            return None

    # --- Idle Detection ---

    def get_idle_duration_sec(self) -> float:
        if self._has_xprintidle:
            return self._get_idle_xprintidle()
        return self._get_idle_proc()

    def _get_idle_xprintidle(self) -> float:
        try:
            result = subprocess.run(
                ["xprintidle"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                idle_ms = int(result.stdout.strip())
                return idle_ms / 1000.0
            return 0.0
        except Exception:
            return 0.0

    def _get_idle_proc(self) -> float:
        """Fallback: check /proc/stat for recent input events."""
        try:
            # Check all input device event files for recent activity
            input_dir = Path("/dev/input")
            if not input_dir.exists():
                return 0.0

            import time
            now = time.time()
            newest = 0.0

            for event_file in input_dir.glob("event*"):
                try:
                    stat = event_file.stat()
                    if stat.st_atime > newest:
                        newest = stat.st_atime
                except (PermissionError, OSError):
                    continue

            if newest > 0:
                return max(0.0, now - newest)
            return 0.0

        except Exception:
            return 0.0

    # --- Screen Lock ---

    def is_screen_locked(self) -> bool:
        try:
            # Try GNOME screensaver
            result = subprocess.run(
                [
                    "dbus-send",
                    "--session",
                    "--dest=org.gnome.ScreenSaver",
                    "--type=method_call",
                    "--print-reply",
                    "/org/gnome/ScreenSaver",
                    "org.gnome.ScreenSaver.GetActive",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and "true" in result.stdout.lower():
                return True

            # Try loginctl
            result = subprocess.run(
                ["loginctl", "show-session", "self", "-p", "LockedHint"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                return "yes" in result.stdout.lower()

            return False

        except Exception:
            return False

    # --- System Info ---

    def get_system_info(self) -> SystemInfo:
        return SystemInfo(
            mac_address=self.get_mac_address(),
            hostname=self.get_hostname(),
            local_ip=self.get_local_ip(),
            os_name="linux",
            os_version=platform.release(),
        )

    def get_mac_address(self) -> str:
        try:
            # Read from /sys/class/net for the first non-lo interface
            net_dir = Path("/sys/class/net")
            for iface in sorted(net_dir.iterdir()):
                if iface.name == "lo":
                    continue
                addr_file = iface / "address"
                if addr_file.exists():
                    mac = addr_file.read_text().strip()
                    if mac and mac != "00:00:00:00:00:00":
                        return mac

            # Fallback
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
            # Try reading /proc directly first (faster than psutil)
            comm_file = Path(f"/proc/{pid}/comm")
            if comm_file.exists():
                name = comm_file.read_text().strip()
            else:
                proc = psutil.Process(pid)
                name = proc.name()

            self._process_cache[pid] = name

            if len(self._process_cache) > 500:
                keys = list(self._process_cache.keys())[:100]
                for k in keys:
                    del self._process_cache[k]

            return name

        except (psutil.NoSuchProcess, psutil.AccessDenied, FileNotFoundError):
            return None

    def normalize_app_name(self, raw_name: str) -> str:
        if not raw_name:
            return "unknown"

        lower = raw_name.lower().strip()

        if lower in _APP_NAME_MAP:
            return _APP_NAME_MAP[lower]

        # Strip common suffixes
        for suffix in ("-bin", ".bin", "-wrapper"):
            if lower.endswith(suffix):
                lower = lower[: -len(suffix)]

        if lower:
            return lower[0].upper() + lower[1:]

        return "unknown"

    def clear_process_cache(self):
        self._process_cache.clear()