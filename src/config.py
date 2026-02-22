"""
Agent configuration - loads from .env, environment variables, and defaults.
"""

import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass, field


def _get_data_dir() -> Path:
    """Get platform-specific data directory for the agent."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    data_dir = base / "LocalMonitorAgent"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _get_log_dir() -> Path:
    """Get platform-specific log directory."""
    if sys.platform == "win32":
        log_dir = _get_data_dir() / "logs"
    elif sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "LocalMonitorAgent"
    else:
        log_dir = Path.home() / ".local" / "share" / "LocalMonitorAgent" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _load_env_file(env_path: Path) -> dict:
    """Load .env file into a dictionary."""
    env_vars = {}
    if env_path.exists():
        # Use utf-8-sig to handle files created with BOM (common on Windows).
        with open(env_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    # Remove quotes if present
                    value = value.strip().strip('"').strip("'")
                    env_vars[key.strip().lstrip("\ufeff")] = value
    return env_vars


def _get_project_root() -> Path:
    """Get project root, handling both dev and bundled exe."""
    if getattr(sys, 'frozen', False):
        # Running as bundled exe
        return Path(sys._MEIPASS)  # type: ignore
    else:
        # Running from source
        return Path(__file__).parent.parent


_project_root = _get_project_root()

# Load .env from multiple locations (later ones override earlier)
_env_vars = {}

# 1. Project root (for development)
_env_vars.update(_load_env_file(_project_root / ".env"))

# 2. Data directory (for production/bundled exe)
_env_vars.update(_load_env_file(_get_data_dir() / ".env"))


def _env(key: str, default: str = "") -> str:
    """Get value from environment or .env file."""
    return os.environ.get(key, _env_vars.get(key, default)) # type: ignore


@dataclass
class AgentConfig:
    """Central configuration for the monitoring agent."""

    # --- API ---
    API_BASE_URL: str = _env("API_BASE_URL", "https://manan.digimeck.in")
    API_KEY: str = _env("API_KEY", "")

    # --- Intervals (seconds) ---
    APP_POLL_INTERVAL: int = int(_env("APP_POLL_INTERVAL", "1"))
    NETWORK_POLL_INTERVAL: int = int(_env("NETWORK_POLL_INTERVAL", "5"))
    BATCH_SEND_INTERVAL: int = int(_env("BATCH_SEND_INTERVAL", "300"))
    SESSION_UPDATE_INTERVAL: int = int(_env("SESSION_UPDATE_INTERVAL", "900"))

    # --- Idle Detection ---
    IDLE_THRESHOLD: int = int(_env("IDLE_THRESHOLD", "60"))
    SESSION_SPLIT_IDLE: int = int(_env("SESSION_SPLIT_IDLE", "300"))

    # --- Debounce ---
    MIN_FOCUS_DURATION: int = 2
    MIN_DOMAIN_DURATION: int = 1

    # --- Retry ---
    MAX_RETRIES: int = 10
    INITIAL_RETRY_DELAY: int = 30
    MAX_RETRY_DELAY: int = 14400

    # --- Paths ---
    DATA_DIR: Path = field(default_factory=_get_data_dir)
    LOG_DIR: Path = field(default_factory=_get_log_dir)
    DB_PATH: Path = field(default=None)  # type: ignore
    CATEGORIES_PATH: Path = field(default=None)  # type: ignore
    LOCK_FILE: Path = field(default=None)  # type: ignore

    # --- Debug ---
    DEBUG: bool = _env("DEBUG", "false").lower() in ("true", "1", "yes")
    LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")

    # --- Agent Metadata ---
    AGENT_VERSION: str = "1.0.0"
    SCHEMA_VERSION: int = 1
    SOURCE: str = "local_agent"

    def __post_init__(self):
        if self.DB_PATH is None:
            self.DB_PATH = self.DATA_DIR / "agent.db"
        if self.CATEGORIES_PATH is None:
            # Check bundled location first, then project root
            bundled_path = _project_root / "data" / "categories.json"
            if bundled_path.exists():
                self.CATEGORIES_PATH = bundled_path
            else:
                self.CATEGORIES_PATH = Path(__file__).parent.parent / "data" / "categories.json"
        if self.LOCK_FILE is None:
            self.LOCK_FILE = self.DATA_DIR / "agent.lock"

    @property
    def api_headers(self) -> dict:
        return {
            "X-API-Key": self.API_KEY,
            "Content-Type": "application/json",
            "X-Agent-Version": self.AGENT_VERSION,
        }

    def load_categories(self) -> dict:
        """Load category definitions from JSON file."""
        if self.CATEGORIES_PATH.exists():
            with open(self.CATEGORIES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"apps": {}, "domains": {}, "ignored_domains": [], "ignored_apps": []}


# Singleton instance
config = AgentConfig()
