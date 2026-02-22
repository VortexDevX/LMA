"""
Tests for CLI arguments in main.py.
"""

import sys
import os
import pytest # type: ignore
from unittest.mock import patch, MagicMock


class TestCmdVersion:
    def test_prints_version(self, capsys):
        from src.main import _cmd_version

        code = _cmd_version()

        assert code == 0
        out = capsys.readouterr().out
        assert "Local Monitor Agent v" in out
        assert sys.platform in out


class TestCmdStatus:
    def test_status_no_database(self, capsys, tmp_path):
        from src.config import AgentConfig

        mock_config = AgentConfig(
            DB_PATH=tmp_path / "nonexistent.db",
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        with patch("src.config.config", mock_config):
            from src.main import _cmd_status
            code = _cmd_status()

        assert code == 0
        out = capsys.readouterr().out
        assert "NOT RUNNING" in out
        assert "Not created yet" in out

    def test_status_with_database(self, capsys, tmp_path):
        from src.config import AgentConfig
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "agent.db"

        mock_config = AgentConfig(
            DB_PATH=db_path,
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        # Create a real DB with some config
        buf = SQLiteBuffer(db_path=db_path)
        buf.set_config("employee_id", "42")
        buf.set_config("employee_name", "Test User")
        buf.set_config("device_mac", "aa:bb:cc:dd:ee:ff")
        buf.close()

        with patch("src.config.config", mock_config):
            from src.main import _cmd_status
            code = _cmd_status()

        assert code == 0
        out = capsys.readouterr().out
        assert "Test User" in out
        assert "42" in out
        assert "aa:bb:cc:dd:ee:ff" in out

    def test_status_running(self, capsys, tmp_path):
        from src.config import AgentConfig

        lock_file = tmp_path / "agent.lock"
        lock_file.write_text(str(os.getpid()))

        mock_config = AgentConfig(
            DB_PATH=tmp_path / "nonexistent.db",
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=lock_file,
        )

        with patch("src.config.config", mock_config):
            from src.main import _cmd_status
            code = _cmd_status()

        assert code == 0
        out = capsys.readouterr().out
        assert "RUNNING" in out


class TestCmdReset:
    def test_reset_no_database(self, capsys, tmp_path):
        from src.config import AgentConfig

        mock_config = AgentConfig(
            DB_PATH=tmp_path / "nonexistent.db",
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        with patch("src.config.config", mock_config):
            from src.main import _cmd_reset
            code = _cmd_reset()

        assert code == 0
        out = capsys.readouterr().out
        assert "Nothing to reset" in out

    def test_reset_confirmed(self, capsys, tmp_path, monkeypatch):
        from src.config import AgentConfig
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "agent.db"

        mock_config = AgentConfig(
            DB_PATH=db_path,
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        buf = SQLiteBuffer(db_path=db_path)
        buf.set_config("employee_id", "42")
        buf.set_config("employee_name", "Test User")
        buf.close()

        monkeypatch.setattr("builtins.input", lambda _: "y")

        with patch("src.config.config", mock_config):
            from src.main import _cmd_reset
            code = _cmd_reset()

        assert code == 0

        # Verify identity cleared
        buf = SQLiteBuffer(db_path=db_path)
        assert buf.get_config("employee_id") is None
        assert buf.get_config("employee_name") is None
        buf.close()

    def test_reset_cancelled(self, capsys, tmp_path, monkeypatch):
        from src.config import AgentConfig
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "agent.db"

        mock_config = AgentConfig(
            DB_PATH=db_path,
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        buf = SQLiteBuffer(db_path=db_path)
        buf.set_config("employee_id", "42")
        buf.close()

        monkeypatch.setattr("builtins.input", lambda _: "n")

        with patch("src.config.config", mock_config):
            from src.main import _cmd_reset
            code = _cmd_reset()

        assert code == 0

        # Verify identity NOT cleared
        buf = SQLiteBuffer(db_path=db_path)
        assert buf.get_config("employee_id") == "42"
        buf.close()

    def test_reset_blocked_if_running(self, capsys, tmp_path):
        from src.config import AgentConfig
        from src.storage.sqlite_buffer import SQLiteBuffer

        db_path = tmp_path / "agent.db"
        lock_file = tmp_path / "agent.lock"
        lock_file.write_text(str(os.getpid()))

        mock_config = AgentConfig(
            DB_PATH=db_path,
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=lock_file,
        )

        buf = SQLiteBuffer(db_path=db_path)
        buf.close()

        with patch("src.config.config", mock_config):
            from src.main import _cmd_reset
            code = _cmd_reset()

        assert code == 1
        out = capsys.readouterr().out
        assert "running" in out.lower()


class TestCmdUninstall:
    def test_uninstall_removes_autostart(self, capsys, tmp_path, monkeypatch):
        from src.config import AgentConfig

        mock_config = AgentConfig(
            DB_PATH=tmp_path / "agent.db",
            DATA_DIR=tmp_path / "data",
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        monkeypatch.setattr("builtins.input", lambda _: "n")

        with patch("src.config.config", mock_config), \
             patch("src.utils.autostart.is_autostart_enabled", return_value=True), \
             patch("src.utils.autostart.unregister_autostart", return_value=True):
            from src.main import _cmd_uninstall
            code = _cmd_uninstall()

        assert code == 0
        out = capsys.readouterr().out
        assert "Auto-start removed" in out

    def test_uninstall_blocked_if_running(self, capsys, tmp_path):
        from src.config import AgentConfig

        lock_file = tmp_path / "agent.lock"
        lock_file.write_text(str(os.getpid()))

        mock_config = AgentConfig(
            DB_PATH=tmp_path / "agent.db",
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=lock_file,
        )

        with patch("src.config.config", mock_config):
            from src.main import _cmd_uninstall
            code = _cmd_uninstall()

        assert code == 1
        out = capsys.readouterr().out
        assert "running" in out.lower()


class TestCmdSetup:
    def test_setup_calls_first_launch(self, tmp_path):
        from src.config import AgentConfig

        db_path = tmp_path / "agent.db"

        mock_config = AgentConfig(
            DB_PATH=db_path,
            DATA_DIR=tmp_path,
            LOG_DIR=tmp_path / "logs",
            LOCK_FILE=tmp_path / "agent.lock",
        )

        with patch("src.config.config", mock_config), \
             patch("src.setup.first_launch.run_first_launch", return_value=True) as mock_fl, \
             patch("src.utils.autostart.register_autostart", return_value=False):
            from src.main import _cmd_setup
            code = _cmd_setup()

        assert code == 0
        mock_fl.assert_called_once()


class TestParseArgs:
    def test_version_flag(self):
        with patch("sys.argv", ["agent", "--version"]):
            from src.main import _parse_args
            args = _parse_args()
            assert args.version is True

    def test_status_flag(self):
        with patch("sys.argv", ["agent", "--status"]):
            from src.main import _parse_args
            args = _parse_args()
            assert args.status is True

    def test_reset_flag(self):
        with patch("sys.argv", ["agent", "--reset"]):
            from src.main import _parse_args
            args = _parse_args()
            assert args.reset is True

    def test_uninstall_flag(self):
        with patch("sys.argv", ["agent", "--uninstall"]):
            from src.main import _parse_args
            args = _parse_args()
            assert args.uninstall is True

    def test_setup_flag(self):
        with patch("sys.argv", ["agent", "--setup"]):
            from src.main import _parse_args
            args = _parse_args()
            assert args.setup is True

    def test_no_flags(self):
        with patch("sys.argv", ["agent"]):
            from src.main import _parse_args
            args = _parse_args()
            assert not any([args.version, args.status, args.reset,
                           args.uninstall, args.setup])