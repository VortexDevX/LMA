# Local Monitoring Agent - Build Progress Summary

## Project Location

`V:\Projects\EmployeeManagement\local-monitor-agent`

## Python Version

Python 3.14.3 (win32)

## Completed Phases

### Phase 0: Project Setup

✅ **Status: DONE**

- Created full directory structure (`src/`, `tests/`, `data/`, `scripts/`, etc.)
- Created virtual environment at `venv/`
- Installed all dependencies: `psutil`, `requests`, `pystray`, `Pillow`, `scapy`, `dnspython`, `pyinstaller`, `pytest`, `ruff`, `black`, `schedule`
- Created `pyproject.toml`, `.gitignore`, `.env`, `.env.template`
- Created `src/config.py` with `AgentConfig` dataclass (platform-aware paths, .env loading, singleton)
- Created `src/main.py` entry point (logging, signal handling, lock file, skeleton loop)
- Initialized git repo

### Phase 1: Platform Abstraction Layer

✅ **Status: DONE - 15/15 tests passing**

#### `src/platform/base.py` - Abstract base class defining the interface

- `get_foreground_app()` → `ForegroundAppInfo`
- `get_idle_duration_sec()` → `float`
- `is_screen_locked()` → `bool`
- `get_system_info()` → `SystemInfo`
- `get_mac_address()`, `get_hostname()`, `get_local_ip()`
- `get_active_connections()` → `list[NetworkConnection]`
- `get_process_name()`, `normalize_app_name()`

#### `src/platform/windows.py` - Windows implementation

- Win32 API via `ctypes` (`GetForegroundWindow`, `GetLastInputInfo`)
- `psutil` for process/network info
- Process name cache (500 entries max)
- Known app name mappings (`chrome.exe` → Chrome, `code.exe` → VSCode, etc.)

#### `src/platform/macos.py` - macOS implementation

- `pyobjc` (NSWorkspace, Quartz) with osascript fallback
- `ioreg` for idle detection
- `ifconfig` for MAC address

#### `src/platform/linux.py` - Linux implementation

- `xdotool`/`xprintidle` for X11
- `swaymsg` for Wayland
- `/proc` filesystem fallbacks
- `/sys/class/net` for MAC address

#### `src/platform/__init__.py` - Factory pattern with singleton

#### Testing

- `tests/test_platform.py` - 15 tests covering all platform methods

### Phase 2: Application Activity Collector

✅ **Status: DONE - 14/14 tests passing**

#### `src/collectors/app_collector.py`

- Polls foreground app every 1 second (configurable)
- Tracks per-app: `active_duration_sec`, `idle_duration_sec`, `switch_count`
- State detection: **ACTIVE** vs **IDLE** (based on `IDLE_THRESHOLD`)
- Session split on idle > `SESSION_SPLIT_IDLE` (5 min)
- Screen lock detection (pauses tracking)
- Ignored apps filtering (system processes from `categories.json`)
- Debounce: filters apps with < `MIN_FOCUS_DURATION` total time
- Thread-safe accumulator with `flush()` method
- `AppRecord` dataclass with `to_dict()` for API payload format

#### Testing

- `tests/test_app_collector.py` - 14 tests

### Phase 6: Local Buffer (SQLite)

✅ **Status: DONE - 38/38 tests passing**

#### `src/storage/sqlite_buffer.py`

- SQLite database with WAL mode for crash safety
- **Tables**: `config`, `pending_sessions`, `pending_app_usage`, `pending_domain_visits`, `sent_log`
- Config key-value store: `get_config()`, `set_config()`, `delete_config()`, `get_all_config()`
- Pending record operations: `insert_pending()`, `insert_pending_batch()`, `get_pending()`
- Status management: `mark_sent()`, `mark_failed()`, `mark_permanently_failed()`
- Retry logic: `get_retryable()` with exponential backoff calculation
- Cleanup: `cleanup_sent()` removes old sent records, `vacuum()`
- Stats: `get_stats()`, `get_pending_count()`
- Corruption recovery: detects corrupt DB, backs up, creates fresh
- Thread-safe with `threading.Lock`
- Platform-aware data directory (AppData on Windows, Library on macOS, .local on Linux)

#### Testing

- `tests/test_sqlite_buffer.py` - 38 tests including thread safety and corruption recovery

### Phase 4: Categorization Module

✅ **Status: DONE - 48/48 tests passing**

#### `src/categorization/categorizer.py`

- Rule-based classification of apps and domains
- **Categories**: productivity, communication, entertainment, social, other
- App matching: exact match, substring match, .exe stripping
- Domain matching: exact, parent domain fallback, suffix matching
- www. prefix stripping, case insensitive
- Browser detection (separate from categories)
- Ignored domains: localhost, IPs, CDNs, system traffic, wildcard patterns
- Ignored apps: system processes
- Dynamic rule updates from backend with version tracking
- Saves updated rules to disk (with `_save_rules` mocked in tests)

#### `scripts/generate_categories.py` - Generates `data/categories.json` with proper UTF-8 encoding

- 78 app entries across 5 groups
- 64 domain entries across 4 categories
- 17 ignored domains
- 23 ignored apps

#### Testing

- `tests/test_categorizer.py` - 48 tests (all rule update tests mock `_save_rules` to prevent overwriting the real file)

#### Notable Issue Fixed

PowerShell created `categories.json` with non-UTF-8 encoding. The `test_update_overrides_existing` test was calling `_save_rules` which overwrote the real file with `{"version": 9}`.

**Fixed by:**

1. Creating a Python script to generate the file with guaranteed UTF-8
2. Mocking `_save_rules` in all update tests

### Phase 5: Session Manager

✅ **Status: DONE - 26/26 tests passing**

#### `src/session/session_manager.py`

- Coordinates `AppCollector`, `Categorizer`, and `SQLiteBuffer`
- Identity management: `employee_id` + `device_mac` stored in buffer config
- Session lifecycle: start → periodic flush → periodic session update → stop
- **Flush loop**: every `BATCH_SEND_INTERVAL` (300s), collects app data, writes to buffer
- **Session update loop**: every `SESSION_UPDATE_INTERVAL` (900s), writes session stats
- Packages data into API-ready payloads matching the spec:
  - Session payloads (start/update/end)
  - App usage batch payloads
  - Domain visit payloads (with categorization and normalization)
- Running totals: `active_sec`, `idle_sec`, `bytes_up`, `bytes_down`
- Status reporting: `get_status()` dict
- Domain visit buffering with filtering (ignored domains, IPs, empty)

#### Testing

- `tests/test_session_manager.py` - 26 tests

### Phase 7: API Sender ⚠️ IN PROGRESS

**Status: 15/25 passing, 10 FAILING**

#### `src/network/api_sender.py`

- Reads pending records from SQLite buffer
- Sends to backend API via HTTPS (`requests.Session` for connection pooling)
- Endpoint mapping: `pending_sessions` → `/api/v1/telemetry/sessions`, etc.
- **Response handling**:
  - `2xx`: mark sent
  - `400`: mark permanently failed (bad data)
  - `401/403`: auth error, mark failed
  - `404`: mark permanently failed
  - `429`: rate limited, mark failed
  - `5xx`: mark failed for retry
- Network detection: socket connect check before send cycle
- Immediate send: `send_immediate()` and `get_immediate()` for auth/device registration
- Periodic cleanup of old sent records (every hour)
- Force send trigger
- Status reporting

#### Testing

- `tests/test_api_sender.py` - 25 tests

#### Current Error: API Sender Tests

The `responses` library mocks HTTP calls correctly (verified by `send_immediate` tests passing), but the buffered sending tests all fail. Records remain in pending status after `_send_all_pending()` is called.

**Root cause:** The `APISender` uses `self._session` (a `requests.Session` instance) for all HTTP calls. The `responses` library intercepts `requests` calls globally, but the sender's `_session` was created at `__init__` time before `@responses.activate` sets up the mock. The `responses` decorator patches the module-level `requests`, but the session's internal adapter may not be getting intercepted properly.

#### Failing Tests (10)

- `test_sends_pending_session` - record stays pending
- `test_sends_pending_app_usage` - record stays pending
- `test_sends_pending_domain_visit` - record stays pending
- `test_400_marks_permanently_failed` - record stays pending
- `test_500_marks_failed_for_retry` - record stays pending
- `test_404_marks_permanently_failed` - record stays pending
- `test_429_rate_limited` - `_last_error` is None (send never happened)
- `test_sends_multiple_records` - all 5 records stay pending
- `test_sends_across_tables` - all 3 records stay pending
- `test_force_send` - record stays pending

#### Passing Tests (15)

- Init, lifecycle, immediate send (4 tests)
- GET immediate (2 tests)
- Network detection (2 tests)
- Status (2 tests)
- All pass fine

## Overall Test Status

| Metric          | Value |
| --------------- | ----- |
| **Total Tests** | 166   |
| **Passing**     | 156   |
| **Failing**     | 10    |

## File Tree (Source Files with Code)

```
src/
├── __init__.py
├── main.py                          # Entry point
├── config.py                        # AgentConfig singleton
├── agent_core.py                    # (empty, Phase 8)
├── platform/
│   ├── __init__.py                  # Factory + re-exports
│   ├── base.py                      # Abstract interface
│   ├── windows.py                   # Win32 implementation
│   ├── macos.py                     # macOS implementation
│   └── linux.py                     # Linux implementation
├── collectors/
│   ├── __init__.py
│   ├── app_collector.py             # App activity tracking
│   └── network_collector.py         # (empty, Phase 3)
├── categorization/
│   ├── __init__.py
│   └── categorizer.py               # Rule-based classification
├── session/
│   ├── __init__.py
│   └── session_manager.py           # Aggregation + buffering coordinator
├── storage/
│   ├── __init__.py
│   └── sqlite_buffer.py             # SQLite persistence layer
├── network/
│   ├── __init__.py
│   └── api_sender.py                # HTTP sender with retry logic
├── setup/
│   ├── __init__.py
│   └── first_launch.py              # (empty, Phase 9)
└── ui/
    ├── __init__.py
    └── tray.py                      # (empty, Phase 10)

data/
└── categories.json                  # Category rules (generated by script)

scripts/
└── generate_categories.py           # UTF-8 categories.json generator

tests/
├── __init__.py
├── conftest.py
├── test_platform.py                 # 15 tests
├── test_app_collector.py           # 14 tests
├── test_sqlite_buffer.py           # 38 tests
├── test_categorizer.py             # 48 tests
├── test_session_manager.py         # 26 tests
└── test_api_sender.py              # 25 tests (10 failing)
```

## Remaining Phases

| Phase | Description               | Status                  |
| ----- | ------------------------- | ----------------------- |
| 7     | API Sender                | 10 test failures to fix |
| 8     | Agent Core (Orchestrator) | Not started             |
| 3     | Network/Domain Collector  | Not started             |
| 9     | Setup / First Launch      | Not started             |
| 10    | System Tray               | Not started             |
| 12    | Packaging (PyInstaller)   | Not started             |
| 13    | Pilot Deployment          | Not started             |
