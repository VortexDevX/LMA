"""
Tests for the System Tray.
Run with: python -m pytest tests/test_tray.py -v
"""

import pytest # type: ignore
from unittest.mock import MagicMock, patch

from src.config import config
from src.ui.tray import SystemTray, is_tray_available, _create_icon_image, _TRAY_AVAILABLE


class TestTrayAvailability:
    """Test tray availability detection."""

    def test_is_tray_available_returns_bool(self):
        result = is_tray_available()
        assert isinstance(result, bool)

    def test_tray_available_when_deps_installed(self):
        # pystray and Pillow are in our requirements
        assert is_tray_available() is True


class TestIconCreation:
    """Test icon image generation."""

    @pytest.mark.skipif(not _TRAY_AVAILABLE, reason="pystray/Pillow not available")
    def test_create_green_icon(self):
        img = _create_icon_image("green")
        assert img is not None
        assert img.size == (64, 64)
        assert img.mode == "RGBA"

    @pytest.mark.skipif(not _TRAY_AVAILABLE, reason="pystray/Pillow not available")
    def test_create_yellow_icon(self):
        img = _create_icon_image("yellow")
        assert img is not None
        assert img.size == (64, 64)

    @pytest.mark.skipif(not _TRAY_AVAILABLE, reason="pystray/Pillow not available")
    def test_create_red_icon(self):
        img = _create_icon_image("red")
        assert img is not None
        assert img.size == (64, 64)

    @pytest.mark.skipif(not _TRAY_AVAILABLE, reason="pystray/Pillow not available")
    def test_create_gray_icon(self):
        img = _create_icon_image("gray")
        assert img is not None
        assert img.size == (64, 64)

    @pytest.mark.skipif(not _TRAY_AVAILABLE, reason="pystray/Pillow not available")
    def test_create_unknown_color_defaults_gray(self):
        img = _create_icon_image("purple")
        assert img is not None
        assert img.size == (64, 64)


class TestSystemTrayInit:
    """Test tray initialization."""

    def test_creates_successfully(self):
        status_fn = MagicMock(return_value={"running": True})
        stop_fn = MagicMock()

        tray = SystemTray(get_status_fn=status_fn, stop_fn=stop_fn)
        assert tray is not None
        assert not tray.is_running
        assert not tray.is_paused

    def test_callbacks_assignable(self):
        tray = SystemTray(
            get_status_fn=MagicMock(),
            stop_fn=MagicMock(),
        )
        pause_fn = MagicMock()
        resume_fn = MagicMock()

        tray.on_pause = pause_fn
        tray.on_resume = resume_fn

        assert tray.on_pause is pause_fn
        assert tray.on_resume is resume_fn


class TestTrayMenuText:
    """Test dynamic menu text generation."""

    def test_status_text_running(self):
        status_fn = MagicMock(return_value={
            "session": {"running": True, "pending_records": 0},
        })
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._status_text(None)
        assert "Running" in text

    def test_status_text_running_with_pending(self):
        status_fn = MagicMock(return_value={
            "session": {"running": True, "pending_records": 5},
        })
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._status_text(None)
        assert "5 pending" in text

    def test_status_text_stopped(self):
        status_fn = MagicMock(return_value={
            "session": {"running": False},
        })
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._status_text(None)
        assert "Stopped" in text

    def test_status_text_paused(self):
        status_fn = MagicMock(return_value={
            "session": {"running": True, "pending_records": 0},
        })
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())
        tray._paused = True

        text = tray._status_text(None)
        assert "Paused" in text

    def test_status_text_handles_error(self):
        status_fn = MagicMock(side_effect=Exception("fail"))
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._status_text(None)
        assert "Unknown" in text

    def test_employee_text(self):
        status_fn = MagicMock(return_value={
            "session": {"employee_id": 42},
        })
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._employee_text(None)
        assert "42" in text

    def test_employee_text_handles_error(self):
        status_fn = MagicMock(side_effect=Exception("fail"))
        tray = SystemTray(get_status_fn=status_fn, stop_fn=MagicMock())

        text = tray._employee_text(None)
        assert "Unknown" in text

    def test_pause_text_when_running(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        tray._paused = False
        text = tray._pause_text(None)
        assert text == "Call it a day"

    def test_pause_text_when_paused(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        tray._paused = True
        text = tray._pause_text(None)
        assert text == "Resume Work"

    def test_about_text(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        text = tray._about_text(None)
        assert config.AGENT_VERSION in text # type: ignore


class TestTrayPauseToggle:
    """Test pause/resume functionality."""

    def test_pause_toggle_changes_state(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        mock_icon = MagicMock()

        assert tray.is_paused is False

        tray._on_pause_toggle(mock_icon, None)
        assert tray.is_paused is True

        tray._on_pause_toggle(mock_icon, None)
        assert tray.is_paused is False

    def test_pause_calls_callback(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        pause_fn = MagicMock()
        tray.on_pause = pause_fn
        mock_icon = MagicMock()

        tray._on_pause_toggle(mock_icon, None)
        pause_fn.assert_called_once()

    def test_resume_calls_callback(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        resume_fn = MagicMock()
        tray.on_resume = resume_fn
        mock_icon = MagicMock()

        # First toggle: pause
        tray._on_pause_toggle(mock_icon, None)
        # Second toggle: resume
        tray._on_pause_toggle(mock_icon, None)
        resume_fn.assert_called_once()

    def test_pause_callback_error_handled(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        tray.on_pause = MagicMock(side_effect=Exception("fail"))
        mock_icon = MagicMock()

        # Should not raise
        tray._on_pause_toggle(mock_icon, None)
        assert tray.is_paused is True


class TestTrayQuit:
    """Test quit functionality."""

    def test_quit_calls_stop_fn(self):
        stop_fn = MagicMock()
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=stop_fn)
        mock_icon = MagicMock()

        tray._on_quit(mock_icon, None)
        stop_fn.assert_called_once()

    def test_quit_stops_tray(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        tray._running = True
        mock_icon = MagicMock()

        tray._on_quit(mock_icon, None)
        # _running set to False by stop()
        assert tray.is_running is False


class TestTrayViewStats:
    """Test view stats browser launch."""

    @patch("src.ui.tray.webbrowser")
    def test_view_stats_opens_browser(self, mock_wb):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        mock_icon = MagicMock()

        tray._on_view_stats(mock_icon, None)
        mock_wb.open.assert_called_once()

        url = mock_wb.open.call_args[0][0]
        assert config.API_BASE_URL in url # type: ignore

    @patch("src.ui.tray.webbrowser")
    def test_view_stats_handles_error(self, mock_wb):
        mock_wb.open.side_effect = Exception("no browser")
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        mock_icon = MagicMock()

        # Should not raise
        tray._on_view_stats(mock_icon, None)


class TestAgentCoreWithTray:
    """Test that agent core integrates tray properly."""

    def test_agent_status_includes_tray(self):
        from src.agent_core import AgentCore

        agent = AgentCore()
        # Before init, no tray in status
        status = agent.get_status()
        assert "tray" not in status

    def test_tray_stop_without_start(self):
        tray = SystemTray(get_status_fn=MagicMock(), stop_fn=MagicMock())
        # Should not crash
        tray.stop()