"""
Auto-Update Mechanism.
Checks backend for newer agent versions, downloads, verifies, and applies updates.
Keeps a backup of previous version for rollback.
"""

import os
import sys
import time
import shutil
import hashlib
import tempfile
import subprocess
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.config import config

logger = logging.getLogger("agent.updater")

# How often to check for updates (seconds)
UPDATE_CHECK_INTERVAL = 86400  # 24 hours

# Max consecutive crashes before rollback
MAX_CRASH_COUNT = 3


@dataclass
class UpdateInfo:
    """Information about an available update."""
    version: str
    download_url: str
    checksum: str  # SHA-256 hex digest
    release_notes: str = ""
    mandatory: bool = False


class Updater:
    """
    Checks for and applies agent updates.

    Flow:
    1. GET /api/v1/agent/latest-version → compare with current
    2. If newer: download binary to temp dir
    3. Verify SHA-256 checksum
    4. Backup current exe
    5. Replace with new exe
    6. Restart agent (via helper script on Windows)
    """

    def __init__(self, sender):
        """
        Args:
            sender: APISender instance for making HTTP requests.
        """
        self._sender = sender
        self._last_check_time: float = 0.0
        self._available_update: Optional[UpdateInfo] = None
        self._is_frozen = getattr(sys, "frozen", False)

    # --------------------------------------------------
    # Update check
    # --------------------------------------------------

    def should_check(self) -> bool:
        """Whether enough time has passed since last check."""
        return time.time() - self._last_check_time >= UPDATE_CHECK_INTERVAL

    def check_for_update(self) -> Optional[UpdateInfo]:
        """
        Query backend for latest agent version.
        Returns UpdateInfo if a newer version is available, None otherwise.
        """
        self._last_check_time = time.time()

        try:
            result = self._sender.get_immediate("/api/v1/agent/latest-version")

            if result is None:
                logger.debug("Update check: no response from server")
                return None

            remote_version = result.get("version", "")
            if not remote_version:
                logger.debug("Update check: no version in response")
                return None

            if not self._is_newer(remote_version, config.AGENT_VERSION):
                logger.debug(
                    f"Update check: current={config.AGENT_VERSION}, "
                    f"latest={remote_version} (up to date)"
                )
                return None

            info = UpdateInfo(
                version=remote_version,
                download_url=result.get("download_url", ""),
                checksum=result.get("checksum", ""),
                release_notes=result.get("release_notes", ""),
                mandatory=result.get("mandatory", False),
            )

            if not info.download_url:
                logger.warning(
                    f"Update v{remote_version} available but no download URL"
                )
                return None

            self._available_update = info
            logger.info(
                f"Update available: v{config.AGENT_VERSION} → v{remote_version}"
            )
            return info

        except Exception as e:
            logger.debug(f"Update check failed: {e}")
            return None

    @property
    def available_update(self) -> Optional[UpdateInfo]:
        return self._available_update

    # --------------------------------------------------
    # Download and verify
    # --------------------------------------------------

    def download_update(self, info: UpdateInfo) -> Optional[Path]:
        """
        Download the update binary to a temp directory.
        Returns path to downloaded file, or None on failure.
        """
        if not info.download_url:
            return None

        try:
            import requests

            logger.info(f"Downloading update v{info.version}...")

            temp_dir = Path(tempfile.mkdtemp(prefix="lma_update_"))
            filename = f"LocalMonitorAgent_v{info.version}"
            if sys.platform == "win32":
                filename += ".exe"
            dest = temp_dir / filename

            response = requests.get(
                info.download_url,
                timeout=120,
                stream=True,
            )
            response.raise_for_status()

            total = 0
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    total += len(chunk)

            logger.info(
                f"Downloaded update: {dest} ({total / 1024 / 1024:.1f} MB)"
            )
            return dest

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def verify_checksum(self, file_path: Path, expected: str) -> bool:
        """Verify SHA-256 checksum of downloaded file."""
        if not expected:
            logger.warning("No checksum provided, skipping verification")
            return True

        try:
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256.update(chunk)

            actual = sha256.hexdigest()
            match = actual.lower() == expected.lower()

            if match:
                logger.info("Checksum verified OK")
            else:
                logger.error(
                    f"Checksum mismatch: expected={expected}, actual={actual}"
                )

            return match

        except Exception as e:
            logger.error(f"Checksum verification failed: {e}")
            return False

    # --------------------------------------------------
    # Apply update
    # --------------------------------------------------

    def apply_update(self, new_binary: Path) -> bool:
        """
        Replace the current executable with the new one.
        Backs up the current exe first.
        Only works when running as a frozen (PyInstaller) executable.

        Returns True if update was applied and restart is needed.
        """
        if not self._is_frozen:
            logger.warning("Cannot apply update: not running as bundled exe")
            return False

        current_exe = Path(sys.executable)

        if not current_exe.exists():
            logger.error(f"Current executable not found: {current_exe}")
            return False

        if not new_binary.exists():
            logger.error(f"New binary not found: {new_binary}")
            return False

        try:
            # Step 1: Backup current exe
            backup_path = current_exe.with_suffix(".exe.backup")
            if backup_path.exists():
                # Remove old backup
                backup_path.unlink()

            shutil.copy2(str(current_exe), str(backup_path))
            logger.info(f"Current exe backed up to: {backup_path}")

            # Step 2: On Windows, we can't replace a running exe directly.
            # Create a helper script that waits, replaces, and restarts.
            if sys.platform == "win32":
                return self._apply_windows_update(
                    current_exe, new_binary, backup_path
                )
            else:
                return self._apply_unix_update(
                    current_exe, new_binary, backup_path
                )

        except Exception as e:
            logger.error(f"Failed to apply update: {e}")
            return False

    def _apply_windows_update(
        self, current_exe: Path, new_binary: Path, backup_path: Path
    ) -> bool:
        """Apply update on Windows using a helper batch script."""
        try:
            script_path = current_exe.parent / "_update.bat"

            script = f"""@echo off
echo Waiting for agent to exit...
timeout /t 3 /nobreak >nul
echo Replacing executable...
copy /y "{new_binary}" "{current_exe}"
if errorlevel 1 (
    echo Update failed, restoring backup...
    copy /y "{backup_path}" "{current_exe}"
    echo Restored from backup.
) else (
    echo Update applied successfully.
    del "{new_binary}"
)
echo Starting updated agent...
start "" "{current_exe}"
del "%~f0"
"""
            script_path.write_text(script, encoding="utf-8")

            # Launch the script detached
            subprocess.Popen(
                ["cmd.exe", "/c", str(script_path)],
                creationflags=subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )

            logger.info("Update script launched. Agent will restart.")
            return True

        except Exception as e:
            logger.error(f"Windows update script failed: {e}")
            return False

    def _apply_unix_update(
        self, current_exe: Path, new_binary: Path, backup_path: Path
    ) -> bool:
        """Apply update on Linux/macOS."""
        try:
            script_path = current_exe.parent / "_update.sh"

            script = f"""#!/bin/bash
sleep 3
cp -f "{new_binary}" "{current_exe}"
if [ $? -ne 0 ]; then
    cp -f "{backup_path}" "{current_exe}"
    echo "Update failed, restored backup."
else
    chmod +x "{current_exe}"
    rm -f "{new_binary}"
    echo "Update applied."
fi
"{current_exe}" &
rm -f "$0"
"""
            script_path.write_text(script, encoding="utf-8")
            script_path.chmod(0o755)

            subprocess.Popen(
                ["/bin/bash", str(script_path)],
                close_fds=True,
                start_new_session=True,
            )

            logger.info("Update script launched. Agent will restart.")
            return True

        except Exception as e:
            logger.error(f"Unix update script failed: {e}")
            return False

    # --------------------------------------------------
    # Rollback
    # --------------------------------------------------

    def rollback(self) -> bool:
        """
        Restore the previous version from backup.
        Only works when running as a frozen executable.
        """
        if not self._is_frozen:
            logger.warning("Cannot rollback: not running as bundled exe")
            return False

        current_exe = Path(sys.executable)
        backup_path = current_exe.with_suffix(".exe.backup")

        if not backup_path.exists():
            logger.warning("No backup found for rollback")
            return False

        try:
            shutil.copy2(str(backup_path), str(current_exe))
            logger.info("Rollback complete: restored previous version")
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    # --------------------------------------------------
    # Crash tracking
    # --------------------------------------------------

    @staticmethod
    def record_clean_start(buffer):
        """Record that agent started successfully (no crash)."""
        buffer.set_config("last_clean_start", str(time.time()))
        buffer.set_config("crash_count", "0")

    @staticmethod
    def record_crash(buffer):
        """Increment crash counter."""
        try:
            count = int(buffer.get_config("crash_count", "0"))
        except (ValueError, TypeError):
            count = 0
        buffer.set_config("crash_count", str(count + 1))

    @staticmethod
    def should_rollback(buffer) -> bool:
        """Check if crash count exceeds threshold."""
        try:
            count = int(buffer.get_config("crash_count", "0"))
        except (ValueError, TypeError):
            count = 0
        return count >= MAX_CRASH_COUNT

    # --------------------------------------------------
    # Version comparison
    # --------------------------------------------------

    @staticmethod
    def _is_newer(remote: str, current: str) -> bool:
        """
        Compare semantic versions. Returns True if remote > current.
        Handles: "1.0.0", "1.2.3", "2.0.0-beta", etc.
        """
        try:
            r_parts = [int(x) for x in remote.split("-")[0].split(".")]
            c_parts = [int(x) for x in current.split("-")[0].split(".")]

            # Pad to same length
            while len(r_parts) < 3:
                r_parts.append(0)
            while len(c_parts) < 3:
                c_parts.append(0)

            return r_parts > c_parts

        except (ValueError, AttributeError):
            return False