# Local Monitoring Agent - Build Progress Summary

---

## Project Location

```
V:\Projects\EmployeeManagement\local-monitor-agent
```

## Python Version

```
Python 3.14.3 (win32)
```

## Total Test Status

```
183 passed | 0 failed | 37.95s
```

---

## Completed Phases

### Phase 0: Project Setup

- Full directory structure (`src/`, `tests/`, `data/`, `scripts/`, etc.)
- Virtual environment with all dependencies
- `pyproject.toml`, `.gitignore`, `.env`, `.env.template`
- `src/config.py` - AgentConfig dataclass singleton with platform-aware paths, .env loading
- Git repo initialized

**Status: DONE**

---

### Phase 1: Platform Abstraction Layer (15 tests)

- `src/platform/base.py` - Abstract interface with dataclasses (`ForegroundAppInfo`, `NetworkConnection`, `SystemInfo`)
- `src/platform/windows.py` - Win32 API via ctypes (`GetForegroundWindow`, `GetLastInputInfo`), psutil, process name cache, known app mappings
- `src/platform/macos.py` - pyobjc with osascript/ioreg fallbacks
- `src/platform/linux.py` - xdotool/xprintidle for X11, swaymsg for Wayland, /proc fallbacks
- `src/platform/__init__.py` - Factory pattern with singleton

**Status: DONE - 15/15 tests**

---

### Phase 2: App Activity Collector (14 tests)

- `src/collectors/app_collector.py`:
  - 1-second polling loop in daemon thread
  - Per-app tracking: `active_duration_sec`, `idle_duration_sec`, `switch_count`
  - State machine: ACTIVE/IDLE based on `IDLE_THRESHOLD` (60s)
  - Session split on idle > `SESSION_SPLIT_IDLE` (300s)
  - Screen lock detection pauses tracking
  - Ignored apps filtering from categories.json
  - Debounce: filters < `MIN_FOCUS_DURATION` (2s)
  - Thread-safe accumulator with `flush()` returning API-ready dicts

**Status: DONE - 14/14 tests**

---

### Phase 6: Local Buffer / SQLite (38 tests)

- `src/storage/sqlite_buffer.py`:
  - WAL mode SQLite for crash safety
  - Tables: `config`, `pending_sessions`, `pending_app_usage`, `pending_domain_visits`, `sent_log`
  - Key-value config store for identity persistence
  - Pending record CRUD: insert, insert_batch, get_pending, get_retryable
  - Status lifecycle: pending -> sent / failed -> permanently_failed
  - Exponential backoff calculation for retries
  - Cleanup of old sent records, vacuum
  - Corruption recovery (backup + fresh DB)
  - Thread-safe with `threading.Lock`

**Status: DONE - 38/38 tests**

---

### Phase 4: Categorization Module (48 tests)

- `src/categorization/categorizer.py`:
  - Rule-based classification into: productivity, communication, entertainment, social, other
  - App matching: exact, substring, .exe stripping, case insensitive
  - Domain matching: exact, parent domain fallback, suffix, www. stripping
  - Browser detection (separate tracking)
  - Ignored domains: localhost, IPs, CDNs, wildcard patterns
  - Ignored apps: system processes
  - Dynamic rule updates from backend with version gating
  - Persists updated rules to disk
- `scripts/generate_categories.py` - Generates `data/categories.json` (78 apps, 64 domains, 17 ignored domains, 23 ignored apps)

**Notable fix:** PowerShell encoding issues corrupted categories.json. Tests that call `update_rules` now mock `_save_rules` to prevent overwriting the real file.

**Status: DONE - 48/48 tests**

---

### Phase 5: Session Manager (26 tests)

- `src/session/session_manager.py`:
  - Coordinates AppCollector + Categorizer + SQLiteBuffer
  - Identity management: employee_id + device_mac persisted in buffer
  - Session lifecycle: start -> flush loop (300s) -> session update loop (900s) -> stop
  - Packages collector data into API-spec payloads:
    - Session payloads (start/update/end with active_sec, idle_sec, bytes, bandwidth)
    - App usage batch payloads (array of app records per window)
    - Domain visit payloads (normalized, categorized, filtered)
  - Running totals for session stats
  - Status reporting via `get_status()`

**Status: DONE - 26/26 tests**

---

### Phase 7: API Sender (25 tests)

- `src/network/api_sender.py`:
  - Reads pending records from SQLite buffer, sends via HTTPS
  - `requests.Session` for connection pooling
  - Endpoint mapping: pending_sessions -> `/api/v1/telemetry/sessions`, etc.
  - Response handling:
    - 2xx: mark sent
    - 400: permanently failed (bad data, no retry)
    - 401/403: auth error, mark failed
    - 404: permanently failed
    - 429: rate limited, mark failed
    - 5xx: mark failed for retry
  - Network availability check (socket connect) before send cycle
  - Immediate send: `send_immediate()` / `get_immediate()` for auth and device registration
  - Periodic cleanup of old sent records (hourly)
  - Force send trigger, status reporting
  - Background thread with configurable interval

**Notable fix:** Original code had `if not self._running and not retry: break` in send loop which skipped all records when sender wasn't started as a thread. Removed the guard.

**Status: DONE - 25/25 tests**

---

### Phase 8: Agent Core (14 tests)

- `src/agent_core.py`:
  - Main orchestrator tying all components together
  - Startup sequence: logging -> lock file -> SQLite -> APISender -> SessionManager -> first launch check -> start all -> main loop
  - Graceful shutdown: stop session manager -> stop sender -> flush buffer -> close DB -> remove lock
  - Single instance enforcement via PID lock file
  - Combined status reporting from all components
  - Signal handling (SIGINT, SIGTERM)
- `src/main.py` - Simplified to just instantiate and run AgentCore

**Status: DONE - 14/14 tests**

---

### Phase 9: First Launch Setup (included in Phase 8 tests)

- `src/setup/first_launch.py`:
  - CLI-based setup flow (GUI planned for Phase 15)
  - Prompts for employee ID (numeric, 3 retries)
  - Prompts for TOTP code, verifies via `POST /api/v1/auth/verify`
  - Registers device via `POST /api/v1/devices/`
  - Auto-detects: MAC address, hostname, IP, device type (laptop/desktop via battery check)
  - Saves identity to SQLite config: employee_id, device_mac, employee_name, employee_code
  - Handles: keyboard interrupt, network errors, invalid input, retry logic

**Status: DONE - tested as part of Phase 8 (14 tests cover setup flows)**

---

## File Tree (all source files with code)

```
src/
  __init__.py
  main.py                    -- Entry point (calls AgentCore.run())
  config.py                  -- AgentConfig singleton
  agent_core.py              -- Main orchestrator
  platform/
    __init__.py              -- Factory + re-exports
    base.py                  -- Abstract interface + dataclasses
    windows.py               -- Win32 implementation
    macos.py                 -- macOS implementation
    linux.py                 -- Linux implementation
  collectors/
    app_collector.py         -- App activity tracking
    network_collector.py     -- (empty, Phase 3)
  categorization/
    categorizer.py           -- Rule-based classification
  session/
    session_manager.py       -- Aggregation + buffering coordinator
  storage/
    sqlite_buffer.py         -- SQLite persistence layer
  network/
    api_sender.py            -- HTTP sender with retry logic
  setup/
    first_launch.py          -- CLI setup flow
  ui/
    tray.py                  -- (empty, Phase 10)
data/
  categories.json            -- Category rules (78 apps, 64 domains)
scripts/
  generate_categories.py     -- UTF-8 categories.json generator
tests/
  test_platform.py           -- 15 tests
  test_app_collector.py      -- 14 tests
  test_sqlite_buffer.py      -- 38 tests
  test_categorizer.py        -- 48 tests
  test_session_manager.py    -- 26 tests
  test_api_sender.py         -- 25 tests
  test_agent_core.py         -- 17 tests
```

---

## Known Issues Encountered & Resolved

| Issue                                             | Root Cause                                                                             | Fix                                                                     |
| ------------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `pyproject.toml` UnicodeDecodeError               | PowerShell wrote em-dash characters in non-UTF-8 encoding                              | Rewrote file with ASCII-only content                                    |
| `categories.json` not loading (all rules empty)   | PowerShell encoding corruption                                                         | Created `scripts/generate_categories.py` to write with guaranteed UTF-8 |
| `categories.json` overwritten to `{"version": 9}` | `test_update_overrides_existing` called `_save_rules` on real file                     | Mocked `_save_rules` in all update tests                                |
| `main.py` missing `logging.handlers` import       | `RotatingFileHandler` referenced before import                                         | Added `import logging.handlers` at top                                  |
| API sender buffered tests all failing (10 tests)  | `if not self._running and not retry: break` skipped records when called outside thread | Removed the guard condition                                             |

---

## Remaining Phases

| Phase | Description              | Status      |
| ----- | ------------------------ | ----------- |
| 3     | Network/Domain Collector | Next        |
| 10    | System Tray              | Not started |
| 12    | Packaging (PyInstaller)  | Not started |
| 13    | Pilot Deployment         | Not started |
| 14    | Hardening & Optimization | Not started |
| 15    | GUI Enhancement          | Not started |
| 16    | Auto-Update              | Not started |

---

## Dependencies Installed

```
psutil, requests, pystray, Pillow, scapy, dnspython,
pyinstaller, pytest, pytest-cov, pytest-mock, responses,
ruff, black, schedule
```

---

## How to Run

```bash
# Activate venv
.\venv\Scripts\Activate.ps1

# Run all tests
python -m pytest tests/ -v

# Run agent (will trigger first-launch setup if not configured)
python -m src.main

# Regenerate categories.json if corrupted
python scripts/generate_categories.py
```
