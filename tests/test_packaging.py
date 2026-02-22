"""
Tests for packaging verification.
Run with: python -m pytest tests/test_packaging.py -v
"""

import sys
from pathlib import Path
import pytest

from src.config import config


class TestBundledResources:
    """Verify resources that will be bundled exist."""

    def test_categories_json_exists(self):
        assert config.CATEGORIES_PATH.exists(), f"Missing: {config.CATEGORIES_PATH}"

    def test_categories_json_valid(self):
        categories = config.load_categories()
        assert "apps" in categories
        assert "domains" in categories
        assert len(categories["apps"]) > 0
        assert len(categories["domains"]) > 0

    def test_main_entry_point_exists(self):
        main_path = Path(__file__).parent.parent / "src" / "main.py"
        assert main_path.exists()

    def test_main_has_main_function(self):
        from src.main import main
        assert callable(main)


class TestIconAssets:
    """Verify icon assets."""

    def test_assets_dir_exists(self):
        assets_dir = Path(__file__).parent.parent / "assets"
        assert assets_dir.exists()

    def test_png_icon_exists(self):
        icon_path = Path(__file__).parent.parent / "assets" / "icon.png"
        assert icon_path.exists()

    def test_ico_icon_exists(self):
        icon_path = Path(__file__).parent.parent / "assets" / "icon.ico"
        assert icon_path.exists()

    def test_iconset_dir_exists(self):
        iconset_dir = Path(__file__).parent.parent / "assets" / "icon" / "iconset"
        assert iconset_dir.exists()

    def test_iconset_has_multiple_sizes(self):
        iconset_dir = Path(__file__).parent.parent / "assets" / "icon" / "iconset"
        png_files = list(iconset_dir.glob("*.png"))
        assert len(png_files) >= 5  # Multiple sizes


class TestBuildScripts:
    """Verify build scripts exist."""

    def test_windows_build_script_exists(self):
        script = Path(__file__).parent.parent / "scripts" / "build_windows.bat"
        assert script.exists()

    def test_macos_build_script_exists(self):
        script = Path(__file__).parent.parent / "scripts" / "build_macos.sh"
        assert script.exists()

    def test_linux_build_script_exists(self):
        script = Path(__file__).parent.parent / "scripts" / "build_linux.sh"
        assert script.exists()

    def test_pyinstaller_spec_exists(self):
        spec = Path(__file__).parent.parent / "local-monitor-agent.spec"
        assert spec.exists()


class TestPyInstallerImports:
    """Verify PyInstaller can import all modules."""

    def test_import_main(self):
        from src import main
        assert main is not None

    def test_import_agent_core(self):
        from src import agent_core
        assert agent_core is not None

    def test_import_config(self):
        from src import config
        assert config is not None

    def test_import_platform(self):
        from src.platform import get_platform
        assert callable(get_platform)

    def test_import_collectors(self):
        from src.collectors.app_collector import AppCollector
        from src.collectors.network_collector import NetworkCollector
        assert AppCollector is not None
        assert NetworkCollector is not None

    def test_import_categorizer(self):
        from src.categorization.categorizer import Categorizer
        assert Categorizer is not None

    def test_import_session_manager(self):
        from src.session.session_manager import SessionManager
        assert SessionManager is not None

    def test_import_sqlite_buffer(self):
        from src.storage.sqlite_buffer import SQLiteBuffer
        assert SQLiteBuffer is not None

    def test_import_api_sender(self):
        from src.network.api_sender import APISender
        assert APISender is not None

    def test_import_first_launch(self):
       from src.setup.first_launch import run_first_launch
       assert callable(run_first_launch)

    def test_import_tray(self):
        from src.ui.tray import SystemTray
        assert SystemTray is not None

    def test_import_pystray(self):
        import pystray
        assert pystray is not None

    def test_import_pillow(self):
        from PIL import Image
        assert Image is not None

    def test_import_psutil(self):
        import psutil
        assert psutil is not None

    def test_import_requests(self):
        import requests
        assert requests is not None