"""
Abstract base class for platform-specific operations.
Each OS (Windows, macOS, Linux) implements this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ForegroundAppInfo:
    """Information about the currently focused application."""
    app_name: str          # Process name (e.g. "chrome", "Code")
    process_id: int        # OS process ID
    raw_process_name: str  # Original process name from OS (e.g. "chrome.exe")


@dataclass
class NetworkConnection:
    """A single active network connection."""
    pid: int
    process_name: str
    remote_ip: str
    remote_port: int
    status: str            # ESTABLISHED, CLOSE_WAIT, etc.
    family: str            # "ipv4" or "ipv6"


@dataclass
class SystemInfo:
    """Basic system identification info."""
    mac_address: str
    hostname: str
    local_ip: str
    os_name: str           # "windows", "macos", "linux"
    os_version: str


class PlatformBase(ABC):
    """
    Abstract interface for all platform-specific operations.
    Implementations: WindowsPlatform, MacOSPlatform, LinuxPlatform
    """

    # --- Foreground App Detection ---

    @abstractmethod
    def get_foreground_app(self) -> Optional[ForegroundAppInfo]:
        """
        Get the currently focused foreground application.
        Returns None if no window is focused or detection fails.
        """
        pass

    # --- Idle Detection ---

    @abstractmethod
    def get_idle_duration_sec(self) -> float:
        """
        Get seconds since last user input (keyboard or mouse).
        Returns 0.0 if user is actively interacting.
        """
        pass

    def is_user_idle(self, threshold_sec: int = 60) -> bool:
        """Check if user has been idle longer than threshold."""
        return self.get_idle_duration_sec() >= threshold_sec

    # --- Screen Lock Detection ---

    @abstractmethod
    def is_screen_locked(self) -> bool:
        """
        Check if the screen is locked or screensaver is active.
        Returns False if detection is not possible on this platform.
        """
        pass

    # --- System Info ---

    @abstractmethod
    def get_system_info(self) -> SystemInfo:
        """Get device identification info (MAC, hostname, IP, OS)."""
        pass

    @abstractmethod
    def get_mac_address(self) -> str:
        """Get the primary MAC address of this device."""
        pass

    @abstractmethod
    def get_hostname(self) -> str:
        """Get the hostname of this device."""
        pass

    @abstractmethod
    def get_local_ip(self) -> str:
        """Get the local/private IP address of this device."""
        pass

    # --- Network Connections ---

    @abstractmethod
    def get_active_connections(self) -> list[NetworkConnection]:
        """
        Get all active TCP connections (ESTABLISHED only).
        Filtered to HTTP/HTTPS ports (80, 443) by default.
        """
        pass

    # --- Process Utilities ---

    @abstractmethod
    def get_process_name(self, pid: int) -> Optional[str]:
        """Get the process name for a given PID. Returns None if not found."""
        pass

    @abstractmethod
    def normalize_app_name(self, raw_name: str) -> str:
        """
        Normalize a process name for display.
        Strip extensions (.exe), lowercase, clean up.
        """
        pass