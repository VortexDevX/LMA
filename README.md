# 🖥️ Local Monitoring Agent

<div align="center">

![Local Monitor Agent Icon](assets/icon/iconset/icon_256x256.png)

Cross-platform productivity telemetry agent for employee monitoring and analytics.

**[GitHub](https://github.com/VortexDevX/LMA.git)** • **[Documentation](docs/)** • **[Issues](https://github.com/VortexDevX/LMA.git/issues)**

</div>

---

## Overview

The **Local Monitoring Agent** is a lightweight, cross-platform background service that collects productivity telemetry at the metadata level and syncs it to a backend API. It's designed to be privacy-conscious, transparent, and reliable.

### What It Monitors

- **Application Usage**: Foreground application names, active/idle time, app switching patterns
- **Network Activity**: Domain-level traffic (bytewise), no full URLs captured
- **Session Tracking**: Session duration, timestamp, device identification

### What It Does NOT Capture

- 🚫 Keystrokes or keystroke logging
- 🚫 Screenshots or screen content
- 🚫 Page content, request/response bodies, or full URLs
- 🚫 Clipboard, webcam, or microphone access

---

## ✨ Key Features

- **Cross-Platform Support**: Windows, macOS, and Linux via platform abstraction layer
- **Offline-First Design**: Local SQLite database buffers data during network outages
- **Automatic Sync**: Batched API uploads with intelligent retry logic
- **User Control**: System tray UI allows employees to pause/resume monitoring
- **Auto-Update**: Background update mechanism with rollback support
- **Event Logging**: Detailed event logs for pause/resume actions
- **Security**: API key obfuscation, auth cooldown, request signing
- **Hardening**: Memory monitoring, crash detection, stale record cleanup
- **CLI & GUI**: Command-line interface with fallback setup wizard
- **Extensive Testing**: 435+ test cases covering all major components

---

## 🚀 Quick Start

### System Requirements

- **Python 3.11+**
- **Windows 10+, macOS 10.14+, or Linux (Ubuntu 20.04+)**
- **Internet connection** for API syncing

### Installation

#### From Source

```bash
# Clone the repository
git clone https://github.com/VortexDevX/LMA.git
cd local-monitor-agent

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the agent (or use installer scripts)
python -m src.main
```

#### Using Installer Scripts

- **Windows**: `scripts/install_windows.ps1` or `install_windows.bat`
- **macOS**: `scripts/build_macos.sh`
- **Linux**: `scripts/build_linux.sh`

---

## 📖 Usage

### Starting the Agent

**Normal Mode** (runs in background):

```bash
python -m src.main
```

**CLI Commands**:

```bash
# Check version
python -m src.main --version

# Check agent status
python -m src.main --status

# Force setup (re-authentication)
python -m src.main --setup

# Reset identity config
python -m src.main --reset

# Uninstall and clean
python -m src.main --uninstall
```

### System Tray Interface

Right-click the tray icon to access menu:

- **Status**: Current monitoring state
- **Call it a day**: Pause monitoring and flush collected data to backend
- **Resume Work**: Resume monitoring
- **View Dashboard**: Open browser to employee dashboard
- **Auto-start**: Toggle auto-launch on system startup
- **Quit Agent**: Stop the agent

### Configuration

Configuration is stored in platform-specific data directories:

- **Windows**: `%APPDATA%\LocalMonitorAgent`
- **macOS**: `~/Library/Application Support/LocalMonitorAgent`
- **Linux**: `~/.local/share/LocalMonitorAgent`

Create `.env` file in the data directory to override settings:

```ini
API_BASE_URL=https://api.yourserver.com
LOG_LEVEL=INFO
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────┐
│   System (App Focus, Network)       │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  AppCollector + NetworkCollector    │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│    SessionManager (Aggregator)      │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  SQLiteBuffer (Local Persistence)   │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│  APISender (Batch Upload)           │
└─────────────────────────────────────┘
         ↓
┌─────────────────────────────────────┐
│    Backend API                      │
└─────────────────────────────────────┘
```

### Core Components

| Component         | Purpose                                 |
| ----------------- | --------------------------------------- |
| `agent_core.py`   | Main orchestrator, lifecycle management |
| `collectors/`     | App and network data collectors         |
| `session/`        | Session aggregation and state tracking  |
| `storage/`        | SQLite buffer for offline persistence   |
| `network/`        | API client and request handling         |
| `categorization/` | Domain categorization (work/personal)   |
| `platform/`       | OS-specific implementations             |
| `ui/`             | System tray and setup wizard            |

---

## 📁 Project Structure

```
local-monitor-agent/
├── src/                          # Main source code
│   ├── agent_core.py             # Core orchestrator
│   ├── config.py                 # Configuration management
│   ├── main.py                   # CLI entry point
│   ├── collectors/               # Data collectors
│   ├── network/                  # API communication
│   ├── session/                  # Session management
│   ├── storage/                  # SQLite buffer
│   ├── categorization/           # Category logic
│   ├── platform/                 # Platform abstraction
│   └── ui/                       # Tray & setup wizard
├── tests/                        # Comprehensive test suite (435+ tests)
├── docs/                         # Documentation
├── scripts/                      # Build & install scripts
├── data/                         # Category definitions
├── assets/                       # Icons and media
├── build/                        # Build artifacts
├── requirements.txt              # Dependencies
└── pyproject.toml               # Project metadata
```

---

## 🔧 Development

### Setup Development Environment

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Install dependencies with test tools
pip install -r requirements.txt
```

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_agent_core.py

# Run with verbose output
pytest -v tests/
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Check type hints (using pyright/pylance)
python -m pylance check src/
```

---

## 🔨 Building

### Build Standalone Executable

**Windows**:

```bash
scripts/build_windows.bat
```

**macOS**:

```bash
bash scripts/build_macos.sh
```

**Linux**:

```bash
bash scripts/build_linux.sh
```

Compiled binaries will be in the `build/` directory.

---

## 🚢 Deployment

### Installation Guides

Detailed deployment instructions are available in the docs:

- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [User Guide](docs/USER_GUIDE.md)
- [Pilot Checklist](docs/PILOT_CHECKLIST.md)

### System Requirements for Deployment

- **Windows**: 10/11, .NET 4.5+, or standalone executable
- **macOS**: 10.14+, Intel or Apple Silicon compatible
- **Linux**: Ubuntu 20.04+, Fedora 32+, or other modern distributions

---

## 🔄 API Integration

The agent communicates with a backend API for:

**Endpoints**:

- `POST /api/v1/telemetry/sessions` - Session lifecycle
- `POST /api/v1/telemetry/app-usage` - Application usage
- `POST /api/v1/telemetry/domain-visits` - Network activity

**Authentication**: API key via `X-API-Key` header (stored securely)

**Data Format**: JSON payloads with employee ID, device MAC, timestamps, and metrics

---

## 📊 Event Logging

All user interactions are logged:

- **Pause Event**: When employee clicks "Call it a day"
- **Resume Event**: When employee clicks "Resume Work"
- **Timestamps**: UTC ISO 8601 format
- **Storage**: Local SQLite database

These events are sent to the backend for audit and productivity pattern analysis.

---

## 🛡️ Security & Privacy

- **Metadata Only**: No content capture, no keyloggers
- **Local Encryption**: Sensitive data (API keys) obfuscated at rest
- **Auth Cooldown**: Protection against rapid credential attacks
- **Data Validation**: Strict payload validation before sync
- **Secure Communication**: HTTPS for all API calls
- **Event Audit**: Complete logging of pause/resume actions

---

## 🐛 Troubleshooting

### Agent Not Starting

- Check logs: `~/.local/share/LocalMonitorAgent/logs/agent.log` (Linux/macOS) or `%APPDATA%\LocalMonitorAgent\logs\agent.log` (Windows)
- Verify network connectivity
- Run `python -m src.main --status` to check state

### Data Not Syncing

- Check internet connection
- Verify API endpoint in configuration
- Review logs for network errors
- Check API key validity

### High Memory Usage

- Agent includes automatic memory monitoring
- Check for large pending data buffers
- Review application usage stats

### Auto-start Not Working

- Verify installation completed successfully
- Check permissions on auto-start directory
- Run `python -m src.main --setup` to re-register

---

## 📚 Documentation

Additional documentation available in `docs/`:

- [Local Agent Overview](docs/LOCAL_AGENT_OVERVIEW.md) - Technical details
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Installation & deployment
- [User Guide](docs/USER_GUIDE.md) - End-user documentation
- [Pilot Checklist](docs/PILOT_CHECKLIST.md) - Testing checklist
- [Development Plans](docs/PLAN/PLAN.md) - Roadmap

---

## 🤝 Contributing

We welcome contributions! Areas of interest:

- Platform-specific enhancements
- Performance optimizations
- Additional categorization rules
- Test coverage improvements
- Documentation improvements

For detailed implementation information, see [LOCAL_AGENT_OVERVIEW.md](docs/LOCAL_AGENT_OVERVIEW.md).

---

## 📝 Environment Variables

Common configuration variables:

| Variable              | Default                 | Description                                     |
| --------------------- | ----------------------- | ----------------------------------------------- |
| `API_BASE_URL`        | `http://localhost:8000` | Backend API endpoint                            |
| `LOG_LEVEL`           | `INFO`                  | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `BATCH_SEND_INTERVAL` | `120`                   | Seconds between data syncs                      |
| `APP_POLL_INTERVAL`   | `1`                     | Seconds between app polling                     |
| `IDLE_THRESHOLD`      | `120`                   | Seconds of inactivity before idle               |

---

## 📞 Support

For issues, feature requests, or questions:

- **GitHub Issues**: [VortexDevX/LMA](https://github.com/VortexDevX/LMA.git/issues)
- **Documentation**: Check [docs/](docs/) for comprehensive guides
- **Logs**: Review agent logs for debugging information

---

## 🎯 Version

**Current Version**: 1.0.1

**Last Updated**: February 2026

---

<div align="center">

Built with ❤️ for transparent workplace productivity monitoring

[GitHub](https://github.com/VortexDevX/LMA.git) • [Docs](docs/) • [Support](https://github.com/VortexDevX/LMA.git/issues)

</div>
