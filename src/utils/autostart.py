"""
Auto-start management.
Registers/unregisters the agent to start on system boot.

Windows:  Registry key HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
macOS:    LaunchAgent plist in ~/Library/LaunchAgents/
Linux:    .desktop file in ~/.config/autostart/
"""

import sys
import logging
from pathlib import Path

logger = logging.getLogger("agent.utils.autostart")

APP_NAME = "LocalMonitorAgent"


def get_exe_path() -> str | None:
    """Get path to bundled executable. Returns None if running from source."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return None


def register_autostart() -> bool:
    """Register the agent to start on system boot."""
    if sys.platform == "win32":
        return _register_windows()
    elif sys.platform == "darwin":
        return _register_macos()
    else:
        return _register_linux()


def unregister_autostart() -> bool:
    """Remove the agent from system boot startup."""
    if sys.platform == "win32":
        return _unregister_windows()
    elif sys.platform == "darwin":
        return _unregister_macos()
    else:
        return _unregister_linux()


def is_autostart_enabled() -> bool:
    """Check if auto-start is currently registered."""
    if sys.platform == "win32":
        return _check_windows()
    elif sys.platform == "darwin":
        return _check_macos()
    else:
        return _check_linux()


# ── Windows ──────────────────────────────────────────────────


def _register_windows() -> bool:
    exe_path = get_exe_path()
    if not exe_path:
        logger.warning("Cannot register auto-start: not running as bundled exe")
        return False
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
        winreg.CloseKey(key)
        logger.info(f"Auto-start registered: {exe_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to register auto-start: {e}")
        return False


def _unregister_windows() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass  # Already not registered
        winreg.CloseKey(key)
        logger.info("Auto-start unregistered")
        return True
    except Exception as e:
        logger.error(f"Failed to unregister auto-start: {e}")
        return False


def _check_windows() -> bool:
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_QUERY_VALUE,
        )
        try:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return bool(value)
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False
    except Exception:
        return False


# ── macOS ────────────────────────────────────────────────────


def _get_plist_path() -> Path:
    return (
        Path.home()
        / "Library"
        / "LaunchAgents"
        / "com.company.localmonitoragent.plist"
    )


_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" \
"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.company.localmonitoragent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""


def _register_macos() -> bool:
    exe_path = get_exe_path()
    if not exe_path:
        logger.warning("Cannot register auto-start: not running as bundled exe")
        return False
    try:
        plist_path = _get_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_PLIST_TEMPLATE.format(exe_path=exe_path))
        logger.info(f"Auto-start registered: {plist_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to register auto-start: {e}")
        return False


def _unregister_macos() -> bool:
    try:
        plist_path = _get_plist_path()
        if plist_path.exists():
            plist_path.unlink()
        logger.info("Auto-start unregistered")
        return True
    except Exception as e:
        logger.error(f"Failed to unregister auto-start: {e}")
        return False


def _check_macos() -> bool:
    return _get_plist_path().exists()


# ── Linux ────────────────────────────────────────────────────


def _get_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "localmonitoragent.desktop"


_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Name=Local Monitor Agent
Exec={exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Local Monitoring Agent for productivity analytics
"""


def _register_linux() -> bool:
    exe_path = get_exe_path()
    if not exe_path:
        logger.warning("Cannot register auto-start: not running as bundled exe")
        return False
    try:
        desktop_path = _get_desktop_path()
        desktop_path.parent.mkdir(parents=True, exist_ok=True)
        desktop_path.write_text(_DESKTOP_TEMPLATE.format(exe_path=exe_path))
        logger.info(f"Auto-start registered: {desktop_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to register auto-start: {e}")
        return False


def _unregister_linux() -> bool:
    try:
        desktop_path = _get_desktop_path()
        if desktop_path.exists():
            desktop_path.unlink()
        logger.info("Auto-start unregistered")
        return True
    except Exception as e:
        logger.error(f"Failed to unregister auto-start: {e}")
        return False


def _check_linux() -> bool:
    return _get_desktop_path().exists()