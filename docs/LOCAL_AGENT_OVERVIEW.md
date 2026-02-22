# Local Monitoring Agent - Technical Overview

## 1. Purpose

The Local Monitoring Agent is a cross-platform background agent that collects productivity telemetry at metadata level only and syncs it to the backend API.

Primary scope:
- Application activity (foreground app, active/idle time, switches)
- Network activity at domain level (no full URL)

Out of scope:
- Keystrokes, screenshots, page content, request/response bodies, clipboard, webcam/microphone capture

## 2. Current Project Status

Implementation status:
- Phases 0 through 16 implemented
- End-to-end test suite passing in current workspace: 435 passed, 1 skipped

Major delivered areas:
- Platform abstraction (Windows/macOS/Linux)
- Collectors, categorization, session aggregation, SQLite buffering, API sender
- Tray UI, CLI, setup wizard GUI fallback
- Hardening (API key obfuscation, stale record reset, watchdog, memory checks, auth cooldown)
- Auto-update and rollback support

## 3. High-Level Architecture

```
AppCollector + NetworkCollector
            |
      SessionManager
            |
       SQLiteBuffer
            |
         APISender
            |
         Backend API
```

Orchestration:
- `src/agent_core.py` initializes all components and controls lifecycle
- `src/main.py` handles CLI commands and normal background run

## 4. Component Breakdown

### 4.1 Agent Core

File: `src/agent_core.py`

Responsibilities:
- Startup/shutdown orchestration
- First-launch setup path selection (CLI if terminal, GUI wizard if no terminal)
- Watchdog checks for collector thread health
- Memory monitoring
- Update check/apply integration
- Crash tracking and rollback trigger

### 4.2 App Activity Collector

File: `src/collectors/app_collector.py`

Collects:
- `app_name`
- `process_id`
- `active_duration_sec`
- `idle_duration_sec`
- `switch_count`

### 4.3 Network/Domain Collector

File: `src/collectors/network_collector.py`

Collects domain-level telemetry using connection snapshots and DNS mapping.

Current behavior:
- Monitored ports: 80, 443, 8080, 8443
- Protocols:
  - TCP established connections
  - UDP flows (including QUIC/HTTP3 patterns on UDP 443)
- DNS sources:
  - Runtime reverse DNS fallback
  - Windows DNS cache parsing and periodic refresh
- Cache management:
  - TTL expiry
  - Size cap with eviction policy

Produced fields:
- `domain`
- `app_name`
- `bytes_uploaded`
- `bytes_downloaded`
- `duration_sec`

Important limitation:
- Per-domain byte attribution is estimated from total NIC deltas and active connection weighting (not packet-level exact accounting).

### 4.4 Categorization

File: `src/categorization/categorizer.py`

Maps app names and domains to categories using `data/categories.json` rules and normalizers.

### 4.5 Session Manager

File: `src/session/session_manager.py`

Responsibilities:
- Aggregates collector output
- Tracks overall session totals
- Buffers three payload types into SQLite
- Emits session start/update/end records
- Uses batch insert for domain visits

### 4.6 SQLite Buffer

File: `src/storage/sqlite_buffer.py`

Tables:
- `config`
- `pending_sessions`
- `pending_app_usage`
- `pending_domain_visits`
- `sent_log`

Capabilities:
- Thread-safe access
- WAL mode
- Backoff-ready retry metadata
- Batch status updates (`mark_sent_batch`, `mark_failed_batch`, `mark_permanently_failed_batch`)
- Startup reset of stale `sending` records to `pending`

### 4.7 API Sender

File: `src/network/api_sender.py`

Endpoints:
- `POST /api/v1/telemetry/sessions`
- `POST /api/v1/telemetry/app-usage`
- `POST /api/v1/telemetry/domain-visits`

Behavior:
- Periodic send loop
- Retry/backoff for transient failures
- Permanent-fail classification for non-retryable payload errors
- Auth cooldown on 401/403 to avoid request hammering
- Last successful sync timestamp tracking
- Enhanced diagnostics for server/network failures

### 4.8 Setup Flows

CLI setup:
- File: `src/setup/first_launch.py`
- Prompts: employee_id, password, TOTP
- Auth endpoint: `POST /api/v1/auth/login`
- Device registration endpoint: `POST /api/v1/devices/`

GUI setup:
- File: `src/ui/setup_wizard.py`
- Used when no interactive terminal is available and tkinter exists
- Writes identity/device config locally after successful login

### 4.9 Tray UI

File: `src/ui/tray.py`

Provides:
- Dynamic status text
- Employee name/id display
- Pause/resume toggle
- Auto-start toggle
- Dashboard launch
- Quit action

### 4.10 Auto-start

File: `src/utils/autostart.py`

Platform behavior:
- Windows: `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`
- macOS: `~/Library/LaunchAgents/com.company.localmonitoragent.plist`
- Linux: `~/.config/autostart/localmonitoragent.desktop`

### 4.11 Updater

File: `src/utils/updater.py`

Capabilities:
- Update availability check (`GET /api/v1/agent/latest-version`)
- Version comparison
- Binary download + SHA-256 verification
- Apply update via platform helper script
- Backup and rollback support
- Crash-count based rollback trigger

## 5. Data Contracts

### 5.1 Session payload

```json
{
  "employee_id": 6,
  "device_mac": "ef:57:67:ab:08:6a",
  "session_start": "2026-02-20T16:01:53.676972+00:00",
  "session_end": null,
  "active_duration_sec": 0,
  "idle_duration_sec": 0,
  "bytes_uploaded": 0,
  "bytes_downloaded": 0,
  "avg_bandwidth_kbps": 0.0,
  "source": "local_agent"
}
```

### 5.2 App usage payload

```json
{
  "employee_id": 6,
  "device_mac": "ef:57:67:ab:08:6a",
  "recorded_at": "2026-02-20T16:06:53.000000+00:00",
  "apps": [
    {
      "app_name": "Chrome",
      "process_id": 12345,
      "active_duration_sec": 120,
      "idle_duration_sec": 20,
      "switch_count": 4
    }
  ]
}
```

### 5.3 Domain visit payload

```json
{
  "employee_id": 6,
  "device_mac": "ef:57:67:ab:08:6a",
  "app_name": "Chrome",
  "domain": "github.com",
  "category": "productivity",
  "bytes_uploaded": 52340,
  "bytes_downloaded": 482910,
  "duration_sec": 128,
  "visited_at": "2026-02-20T18:12:07.441223+00:00"
}
```

Domain telemetry is domain-only. Full URLs/paths/queries are not stored.

## 6. Security and Hardening

Implemented hardening controls include:
- API key migration from plaintext env to machine-tied obfuscated value in SQLite config (`src/utils/crypto.py`)
- BOM-safe env loading for Windows-created `.env`
- Linux/macOS restrictive DB file permissions
- Auth cooldown on repeated auth failures
- Watchdog and stale send-state recovery
- HTTPS transport and API key auth headers

## 7. Runtime Paths

Windows:
- Data dir: `%APPDATA%\\LocalMonitorAgent`
- DB: `%APPDATA%\\LocalMonitorAgent\\agent.db`
- Logs: `%APPDATA%\\LocalMonitorAgent\\logs\\agent.log`
- Config: `%APPDATA%\\LocalMonitorAgent\\.env`

macOS:
- Data dir: `~/Library/Application Support/LocalMonitorAgent`
- Logs: `~/Library/Logs/LocalMonitorAgent`

Linux:
- Data dir: `~/.local/share/LocalMonitorAgent`
- Logs: `~/.local/share/LocalMonitorAgent/logs`

## 8. CLI Surface

From `src/main.py`:
- `--version`
- `--status`
- `--reset`
- `--uninstall`
- `--setup`

## 9. Known Operational Notes

- Console hiding on Windows works when app owns the console (double-click launch). If launched from an existing terminal, the terminal console remains visible by design.
- Domain capture is improved for modern browser traffic, but exact domain attribution can still be limited by DNS visibility and shared CDN infrastructure.

## 10. Related Docs

- `docs/DEPLOYMENT_GUIDE.md`
- `docs/USER_GUIDE.md`
- `docs/PILOT_CHECKLIST.md`
- `docs/PLAN/PLAN.md`
- `docs/SUMMARY/SUMMARY_6.md`
