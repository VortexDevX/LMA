"""
Platform factory — returns the correct implementation for the current OS.
"""

import sys
import logging

from src.platform.base import (
    PlatformBase,
    ForegroundAppInfo,
    NetworkConnection,
    SystemInfo,
)

logger = logging.getLogger("agent.platform")

# Singleton instance
_platform_instance: PlatformBase = None # type: ignore


def get_platform() -> PlatformBase:
    """
    Get the platform-specific implementation for the current OS.
    Returns a singleton instance.
    """
    global _platform_instance

    if _platform_instance is not None:
        return _platform_instance

    current_os = sys.platform

    if current_os == "win32":
        from src.platform.windows import WindowsPlatform
        _platform_instance = WindowsPlatform()
        logger.info("Loaded Windows platform")

    elif current_os == "darwin":
        from src.platform.macos import MacOSPlatform
        _platform_instance = MacOSPlatform()
        logger.info("Loaded macOS platform")

    elif current_os.startswith("linux"):
        from src.platform.linux import LinuxPlatform
        _platform_instance = LinuxPlatform()
        logger.info("Loaded Linux platform")

    else:
        raise RuntimeError(
            f"Unsupported platform: {current_os}. "
            f"Supported: win32, darwin, linux"
        )

    return _platform_instance


# Re-export data classes for convenience
__all__ = [
    "get_platform",
    "PlatformBase",
    "ForegroundAppInfo",
    "NetworkConnection",
    "SystemInfo",
]