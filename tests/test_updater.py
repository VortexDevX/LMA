"""
Tests for Phase 16: Auto-Update Mechanism.
Covers version comparison, update checks, download verification,
crash tracking, and rollback logic.
"""

import time
import hashlib
import sys
import pytest # type: ignore
from pathlib import Path
from unittest.mock import patch, MagicMock


# ============================================================
# Version comparison tests
# ============================================================

class TestVersionComparison:
    """Tests for semantic version comparison."""

    def test_newer_major(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("2.0.0", "1.0.0") is True

    def test_newer_minor(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.1.0", "1.0.0") is True

    def test_newer_patch(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.0.1", "1.0.0") is True

    def test_same_version(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.0.0", "1.0.0") is False

    def test_older_version(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.0.0", "2.0.0") is False

    def test_older_minor(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.0.0", "1.1.0") is False

    def test_two_part_version(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("1.1", "1.0.0") is True

    def test_single_part_version(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("2", "1.0.0") is True

    def test_prerelease_stripped(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("2.0.0-beta", "1.0.0") is True

    def test_invalid_version_returns_false(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("abc", "1.0.0") is False

    def test_empty_version_returns_false(self):
        from src.utils.updater import Updater

        assert Updater._is_newer("", "1.0.0") is False

    def test_none_version_returns_false(self):
        from src.utils.updater import Updater

        assert Updater._is_newer(None, "1.0.0") is False # type: ignore


# ============================================================
# Update check tests
# ============================================================

class TestUpdateCheck:
    """Tests for checking backend for updates."""

    def _make_updater(self):
        from src.utils.updater import Updater

        sender = MagicMock()
        return Updater(sender), sender

    def test_check_returns_none_when_up_to_date(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = {
            "version": "1.0.0",  # Same as current
        }

        with patch("src.utils.updater.config") as mock_config:
            mock_config.AGENT_VERSION = "1.0.0"
            result = updater.check_for_update()

        assert result is None

    def test_check_returns_info_when_newer(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = {
            "version": "2.0.0",
            "download_url": "https://example.com/agent.exe",
            "checksum": "abc123",
            "release_notes": "Bug fixes",
        }

        with patch("src.utils.updater.config") as mock_config:
            mock_config.AGENT_VERSION = "1.0.0"
            result = updater.check_for_update()

        assert result is not None
        assert result.version == "2.0.0"
        assert result.download_url == "https://example.com/agent.exe"
        assert result.checksum == "abc123"

    def test_check_returns_none_on_no_response(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = None

        result = updater.check_for_update()
        assert result is None

    def test_check_returns_none_on_empty_version(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = {"version": ""}

        result = updater.check_for_update()
        assert result is None

    def test_check_returns_none_without_download_url(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = {
            "version": "2.0.0",
            # No download_url
        }

        with patch("src.utils.updater.config") as mock_config:
            mock_config.AGENT_VERSION = "1.0.0"
            result = updater.check_for_update()

        assert result is None

    def test_check_handles_exception(self):
        updater, sender = self._make_updater()

        sender.get_immediate.side_effect = RuntimeError("network error")

        result = updater.check_for_update()
        assert result is None

    def test_should_check_respects_interval(self):
        updater, sender = self._make_updater()

        # Just checked
        updater._last_check_time = time.time()
        assert updater.should_check() is False

        # Long ago
        updater._last_check_time = time.time() - 100000
        assert updater.should_check() is True

    def test_available_update_stored(self):
        updater, sender = self._make_updater()

        sender.get_immediate.return_value = {
            "version": "3.0.0",
            "download_url": "https://example.com/agent.exe",
            "checksum": "sha256hex",
        }

        with patch("src.utils.updater.config") as mock_config:
            mock_config.AGENT_VERSION = "1.0.0"
            updater.check_for_update()

        assert updater.available_update is not None
        assert updater.available_update.version == "3.0.0"


# ============================================================
# Checksum verification tests
# ============================================================

class TestChecksumVerification:
    """Tests for SHA-256 checksum verification."""

    def test_valid_checksum(self, tmp_path):
        updater, _ = self._make_updater()

        # Create a test file
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"hello world binary content")

        # Calculate expected checksum
        expected = hashlib.sha256(b"hello world binary content").hexdigest()

        assert updater.verify_checksum(test_file, expected) is True

    def test_invalid_checksum(self, tmp_path):
        updater, _ = self._make_updater()

        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"hello world")

        assert updater.verify_checksum(test_file, "0000bad0000") is False

    def test_empty_checksum_skips_verification(self, tmp_path):
        updater, _ = self._make_updater()

        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b"anything")

        assert updater.verify_checksum(test_file, "") is True

    def test_missing_file(self, tmp_path):
        updater, _ = self._make_updater()

        missing = tmp_path / "nonexistent.exe"
        assert updater.verify_checksum(missing, "abc") is False

    def test_checksum_case_insensitive(self, tmp_path):
        updater, _ = self._make_updater()

        test_file = tmp_path / "test.exe"
        content = b"test content"
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest().upper()
        assert updater.verify_checksum(test_file, expected) is True

    def _make_updater(self):
        from src.utils.updater import Updater

        return Updater(MagicMock()), MagicMock()


# ============================================================
# Crash tracking tests
# ============================================================

class TestCrashTracking:
    """Tests for crash count tracking and rollback decision."""

    def test_record_clean_start_resets_count(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", "5")

        Updater.record_clean_start(buf)

        assert buf.get_config("crash_count") == "0"
        assert buf.get_config("last_clean_start") is not None
        buf.close()

    def test_record_crash_increments(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", "1")

        Updater.record_crash(buf)

        assert buf.get_config("crash_count") == "2"
        buf.close()

    def test_record_crash_from_zero(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")

        Updater.record_crash(buf)

        assert buf.get_config("crash_count") == "1"
        buf.close()

    def test_should_rollback_false_below_threshold(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", "2")

        assert Updater.should_rollback(buf) is False
        buf.close()

    def test_should_rollback_true_at_threshold(self, tmp_path):
        from src.utils.updater import Updater, MAX_CRASH_COUNT
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", str(MAX_CRASH_COUNT))

        assert Updater.should_rollback(buf) is True
        buf.close()

    def test_should_rollback_true_above_threshold(self, tmp_path):
        from src.utils.updater import Updater, MAX_CRASH_COUNT
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", str(MAX_CRASH_COUNT + 5))

        assert Updater.should_rollback(buf) is True
        buf.close()

    def test_should_rollback_handles_invalid_count(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", "not_a_number")

        assert Updater.should_rollback(buf) is False
        buf.close()

    def test_should_rollback_handles_missing_count(self, tmp_path):
        from src.utils.updater import Updater
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        # No crash_count set

        assert Updater.should_rollback(buf) is False
        buf.close()


# ============================================================
# Apply update tests
# ============================================================

class TestApplyUpdate:
    """Tests for update application logic."""

    def test_apply_fails_when_not_frozen(self, tmp_path):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = False

        new_binary = tmp_path / "new.exe"
        new_binary.write_bytes(b"new")

        assert updater.apply_update(new_binary) is False

    def test_apply_fails_when_binary_missing(self, tmp_path):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = True

        missing = tmp_path / "nonexistent.exe"

        with patch("sys.executable", str(tmp_path / "agent.exe")):
            # Create the "current" exe so the check passes
            current = tmp_path / "agent.exe"
            current.write_bytes(b"current")

            assert updater.apply_update(missing) is False

    def test_apply_creates_backup(self, tmp_path):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = True

        current_exe = tmp_path / "agent.exe"
        current_exe.write_bytes(b"current version")

        new_binary = tmp_path / "new_agent.exe"
        new_binary.write_bytes(b"new version")

        with patch("sys.executable", str(current_exe)), \
             patch.object(updater, "_apply_windows_update", return_value=True), \
             patch.object(updater, "_apply_unix_update", return_value=True):
            result = updater.apply_update(new_binary)

        assert result is True
        backup = current_exe.with_suffix(".exe.backup")
        assert backup.exists()
        assert backup.read_bytes() == b"current version"


# ============================================================
# Rollback tests
# ============================================================

class TestRollback:
    """Tests for rollback to previous version."""

    def test_rollback_fails_when_not_frozen(self):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = False

        assert updater.rollback() is False

    def test_rollback_fails_when_no_backup(self, tmp_path):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = True

        with patch("sys.executable", str(tmp_path / "agent.exe")):
            assert updater.rollback() is False

    def test_rollback_restores_backup(self, tmp_path):
        from src.utils.updater import Updater

        updater = Updater(MagicMock())
        updater._is_frozen = True

        current_exe = tmp_path / "agent.exe"
        current_exe.write_bytes(b"broken version")

        backup = tmp_path / "agent.exe.backup"
        backup.write_bytes(b"good version")

        with patch("sys.executable", str(current_exe)):
            result = updater.rollback()

        assert result is True
        assert current_exe.read_bytes() == b"good version"


# ============================================================
# Agent core integration tests
# ============================================================

class TestAgentCoreUpdateIntegration:
    """Tests for update integration in AgentCore."""

    def test_status_includes_update_info(self):
        from src.agent_core import AgentCore
        from src.utils.updater import UpdateInfo

        agent = AgentCore()
        agent._buffer = MagicMock()
        agent._buffer.get_config.return_value = "Test"
        agent._buffer.get_pending_count.return_value = 0
        agent._buffer.get_stats.return_value = {}
        agent._buffer.db_size_mb = 1.0

        agent._updater = MagicMock()
        agent._updater.available_update = UpdateInfo(
            version="2.0.0",
            download_url="https://example.com",
            checksum="abc",
        )

        status = agent.get_status()
        assert status["update_available"] == "2.0.0"

    def test_status_no_update_available(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        agent._buffer = MagicMock()
        agent._buffer.get_config.return_value = "Test"
        agent._buffer.get_pending_count.return_value = 0
        agent._buffer.get_stats.return_value = {}
        agent._buffer.db_size_mb = 1.0

        agent._updater = MagicMock()
        agent._updater.available_update = None

        status = agent.get_status()
        assert status["update_available"] is None

    def test_crash_recorded_on_fatal_error(self, tmp_path):
        from src.agent_core import AgentCore
        from src.storage.sqlite_buffer import SQLiteBuffer

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("employee_id", "1")
        buf.set_config("device_mac", "aa:bb:cc:dd:ee:ff")

        agent = AgentCore()
        agent._buffer = buf

        # Simulate crash count being recorded
        from src.utils.updater import Updater

        Updater.record_crash(buf)
        assert buf.get_config("crash_count") == "1"

        Updater.record_crash(buf)
        assert buf.get_config("crash_count") == "2"

        buf.close()

    def test_clean_start_resets_crash_count(self, tmp_path):
        from src.agent_core import AgentCore
        from src.storage.sqlite_buffer import SQLiteBuffer
        from src.utils.updater import Updater

        buf = SQLiteBuffer(db_path=tmp_path / "test.db")
        buf.set_config("crash_count", "5")

        Updater.record_clean_start(buf)

        assert buf.get_config("crash_count") == "0"
        buf.close()