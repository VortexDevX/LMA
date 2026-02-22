# Local Monitoring Agent — Build Plan

---

## Phase 0: Project Setup & Tooling

- Choose Python as primary language (cross-platform)
- Set up project structure with `src/`, `config/`, `tests/`, `scripts/`
- Choose packaging tool: PyInstaller (for distributable binary)
- Set up virtual environment, `requirements.txt` / `pyproject.toml`
- Decide on SQLite library (`sqlite3` stdlib)
- Decide on HTTP client (`requests` or `httpx`)
- Decide on scheduling mechanism (`threading.Timer`, `schedule`, or `asyncio`)
- Decide on platform detection (`sys.platform` / `platform` module)
- Set up logging framework (`logging` module, rotating file handler)
- Create `.env` or `config.json` structure for local agent config
- Define constants: API base URL, default intervals, schema version

---

## Phase 1: Platform Abstraction Layer

**Goal:** Abstract OS-specific calls behind a unified interface.

### 1.1 — Define abstract interfaces

- `get_foreground_window_process()` → returns `(app_name, process_id)`
- `is_user_idle(threshold_sec)` → returns `bool`
- `get_idle_duration_sec()` → returns `int`
- `get_mac_address()` → returns `str`
- `get_hostname()` → returns `str`
- `get_local_ip()` → returns `str`
- `get_network_connections()` → returns list of `(pid, remote_ip, remote_port, bytes_sent, bytes_recv)`

### 1.2 — Windows implementation

- Foreground app: `ctypes` → `GetForegroundWindow()` → `GetWindowThreadProcessId()` → `psutil.Process(pid).name()`
- Idle detection: `ctypes` → `GetLastInputInfo()` → compare with `GetTickCount()`
- Network: `psutil.net_connections()` + `psutil.net_io_counters(pernic=False)`

### 1.3 — macOS implementation

- Foreground app: `NSWorkspace.sharedWorkspace().activeApplication()` via `pyobjc` or `subprocess` calling `osascript`
- Idle detection: `ioreg` command or `Quartz.CGEventSourceSecondsSinceLastEventType()`
- Network: `psutil.net_connections()` + `psutil.net_io_counters()`

### 1.4 — Linux implementation

- Foreground app: `xdotool getactivewindow getwindowpid` or read `/proc` + `_NET_ACTIVE_WINDOW` via `Xlib`
- Idle detection: `xprintidle` or `XScreenSaverQueryInfo` via `Xlib`
- Network: `psutil.net_connections()` + `psutil.net_io_counters()`

### 1.5 — Factory pattern

- `PlatformProvider.get()` → returns correct implementation based on `sys.platform`

---

## Phase 2: Application Activity Collector

**Goal:** Track which app is in foreground, for how long, and user activity state.

### 2.1 — Polling loop design

- Poll foreground app every 1 second
- On each poll: record `(timestamp, app_name, process_id)`
- Compare with previous poll to detect app switch

### 2.2 — State machine

- States: `ACTIVE`, `IDLE`, `NO_FOCUS`
- Transitions:
  - `ACTIVE → IDLE`: no input for 60 seconds (configurable)
  - `IDLE → ACTIVE`: input detected
  - Any → `NO_FOCUS`: screensaver, lock screen, minimized

### 2.3 — In-memory accumulator

- Dict keyed by `(app_name, process_id)`
- Each entry tracks:
  - `active_duration_sec` (incremented when state = ACTIVE)
  - `idle_duration_sec` (incremented when state = IDLE)
  - `switch_count` (incremented on each focus gain)
  - `first_seen` / `last_seen` timestamps

### 2.4 — Flush mechanism

- Every 5 minutes: snapshot the accumulator, reset counters
- Return list of app records for that window
- Filter out apps with < 2 seconds total (noise)

### 2.5 — Edge cases to handle

- App crash mid-tracking
- Multiple monitors (still one foreground)
- System apps to ignore (explorer.exe, Finder, systemd)
- Screen lock detection (pause tracking)
- Rapid alt-tab (debounce threshold: ignore < 1 sec focus)

---

## Phase 3: Network / Domain Collector

**Goal:** Capture domain-level network activity per process.

### 3.1 — Connection snapshot approach

- Use `psutil.net_connections(kind='inet')` every 5 seconds
- For each connection: get `(pid, remote_ip, remote_port, status)`
- Filter: only `ESTABLISHED` connections
- Filter: only ports 80 and 443 (HTTP/HTTPS)

### 3.2 — IP to domain resolution

- Reverse DNS: `socket.getfqdn(ip)` or `socket.gethostbyaddr(ip)`
- Cache resolved IPs → domain mapping (TTL: 10 minutes)
- Fallback: DNS sniffer approach (see 3.3)

### 3.3 — DNS sniffer (preferred method)

- Use `scapy` or raw socket to sniff DNS responses on port 53
- Build local cache: `domain → [ip1, ip2, ...]`
- When connection to IP seen, look up domain from cache
- This gives accurate domain names without reverse DNS issues
- Requires elevated privileges (admin/root)
- Alternative: parse OS DNS cache (`ipconfig /displaydns` on Windows, `dscacheutil` on macOS)

### 3.4 — Per-process traffic measurement

- `psutil.Process(pid).io_counters()` — gives bytes read/written (disk, not network)
- Alternative: `psutil.net_io_counters(pernic=True)` — gives totals per interface, not per process
- Best approach: periodic snapshots of connection state + estimate based on connection duration and bandwidth samples
- Or use platform-specific: Windows ETW, macOS NetworkStatistics framework, Linux `/proc/net/tcp` + iptables counters

### 3.5 — Domain aggregation

- Accumulate per `(domain, app_name)` pair:
  - `bytes_uploaded` (estimated)
  - `bytes_downloaded` (estimated)
  - `duration_sec` (time connection was open)
  - `first_visit` / `last_visit`
- Strip subdomains to base domain? Decision: keep as-is (e.g., `docs.google.com` stays, `www.github.com` → `github.com`)
- Normalize: remove `www.` prefix

### 3.6 — Domain stripping logic

- Input: full IP or resolved hostname
- Output: clean domain (e.g., `github.com`)
- Strip: protocol, path, port, `www.`
- Handle: CDN domains (akamai, cloudflare, cloudfront) → label as CDN or skip
- Handle: IP-only connections with no domain → skip or label "unknown"

### 3.7 — Flush mechanism

- Every 5 minutes: snapshot domain accumulator, reset
- Return list of domain visit records
- Filter: skip domains with < 1 second duration

### 3.8 — Edge cases

- VPN active (all traffic goes to one IP) → detect and flag
- Multiple browsers open
- Non-browser apps making HTTPS calls (Slack, VSCode, Electron apps)
- Background tabs (browser has connections open but no user interaction)
- IPv6 connections

---

## Phase 4: Categorization Module

**Goal:** Classify apps and domains into categories.

### 4.1 — Local rules file

- Ship a `categories.json` with agent
- Structure:
  ```
  {
    "apps": {
      "productivity": ["vscode", "code", "intellij", "figma", "notion", ...],
      "communication": ["slack", "teams", "zoom", "discord", ...],
      "entertainment": ["spotify", "vlc", "netflix", ...],
      "social": ["twitter", "instagram", ...],
      "browsers": ["chrome", "firefox", "edge", "safari", "brave", ...]
    },
    "domains": {
      "productivity": ["github.com", "gitlab.com", "stackoverflow.com", ...],
      "social": ["twitter.com", "facebook.com", "instagram.com", "linkedin.com", ...],
      "entertainment": ["youtube.com", "netflix.com", "twitch.tv", ...],
      "communication": ["slack.com", "teams.microsoft.com", ...]
    }
  }
  ```

### 4.2 — Matching logic

- Normalize app name: lowercase, strip `.exe`, strip path
- Match against rules: exact match first, then substring/fuzzy
- Domain match: exact, then wildcard (e.g., `*.google.com`)
- Default: `"other"`

### 4.3 — Backend sync

- On agent start: `GET /api/v1/config/categories` (if endpoint exists)
- Merge with local rules (backend overrides local)
- Cache locally with version number
- Re-fetch periodically (every 24 hours)

### 4.4 — Version tracking

- Store category config version
- Only update if backend version > local version

---

## Phase 5: Session Manager (Aggregator)

**Goal:** Clean, deduplicate, and merge raw data before sending.

### 5.1 — App event merging

- If same app has focus for multiple consecutive polls → single record with summed duration
- Ignore app focus events < 2 seconds (accidental switches)
- Cap idle detection: if idle > 5 minutes → split into separate session segment

### 5.2 — Domain event merging

- Multiple connections to same domain in same 5-min window → single record
- Sum bytes, take max duration
- Keep earliest `visited_at`

### 5.3 — Session splitting

- Detect gaps: if user idle > 5 minutes → end current micro-session, start new one
- Detect day boundary: split at midnight UTC

### 5.4 — Deduplication

- Hash each record `(employee_id, device_mac, timestamp, app/domain)` → dedupe key
- Before sending, check if record already sent (via local SQLite flag)

---

## Phase 6: Local Buffer (SQLite)

**Goal:** Persist data locally to survive crashes, network failures, restarts.

### 6.1 — Database schema

**Tables:**

- `config` — key-value store for employee_id, device_mac, session info
- `pending_sessions` — buffered network session payloads
- `pending_app_usage` — buffered app usage batches
- `pending_domain_visits` — buffered domain visit records
- `sent_log` — record of successfully sent payloads (for dedup)

### 6.2 — Each pending table has columns

- `id` (auto-increment)
- `payload_json` (TEXT — serialized JSON)
- `created_at` (TIMESTAMP)
- `retry_count` (INT, default 0)
- `last_retry_at` (TIMESTAMP, nullable)
- `status` (TEXT: "pending", "sending", "sent", "failed")

### 6.3 — Operations

- `insert_pending(table, payload)` — add new record
- `get_pending(table, limit=50)` — fetch oldest pending records
- `mark_sent(table, id)` — update status to "sent"
- `mark_failed(table, id)` — increment retry_count, update last_retry_at
- `cleanup_sent(older_than_hours=24)` — delete old sent records
- `get_config(key)` / `set_config(key, value)` — config read/write

### 6.4 — Database location

- Windows: `%APPDATA%/LocalMonitorAgent/agent.db`
- macOS: `~/Library/Application Support/LocalMonitorAgent/agent.db`
- Linux: `~/.local/share/LocalMonitorAgent/agent.db`

### 6.5 — Corruption handling

- On open failure: backup corrupt file, create fresh database
- Use WAL mode for crash safety

---

## Phase 7: API Sender (Telemetry Uploader)

**Goal:** Reliably send buffered data to backend API.

### 7.1 — Sender loop

- Runs every 5 minutes (configurable)
- Steps:
  1. Read pending records from SQLite (oldest first, limit 50)
  2. For each record: attempt HTTP POST
  3. On success (2xx): mark as sent
  4. On failure (4xx/5xx/timeout): mark as failed, increment retry
  5. Move to next record

### 7.2 — Retry strategy

- Max retries: 10
- Backoff: exponential (30s, 1m, 2m, 4m, 8m, 15m, 30m, 1h, 2h, 4h)
- After max retries: mark as "permanently_failed", log warning
- On network recovery: retry all pending

### 7.3 — Batch optimization

- Domain visits: if backend supports batch endpoint, send array
- If not: send one by one with small delay (100ms) to avoid rate limiting
- App usage: already batched by design

### 7.4 — Request construction

- Add headers: `X-API-Key`, `Content-Type: application/json`
- Add metadata header: `X-Agent-Version: 1.0.0`
- Timeout: 10 seconds per request
- Verify SSL: yes (no self-signed cert bypass)

### 7.5 — Response handling

- `200/201`: success → mark sent
- `400`: bad payload → log error, mark permanently failed (don't retry bad data)
- `401/403`: auth error → pause sending, alert user
- `404`: endpoint not found → log error, pause
- `429`: rate limited → back off, respect `Retry-After` header
- `500/502/503`: server error → retry with backoff
- Timeout/ConnectionError: retry with backoff

### 7.6 — Network detection

- Before sending: check if network is available
- Simple ping to API base URL or DNS resolution check
- If offline: skip send cycle, try next interval

---

## Phase 8: Agent Core (Controller / Orchestrator)

**Goal:** Tie all modules together, manage lifecycle.

### 8.1 — Startup sequence

1. Initialize logging
2. Load config from SQLite / config file
3. Check if first launch (no employee_id stored)
   - If yes: launch setup flow (Phase 9)
   - If no: proceed
4. Initialize platform abstraction layer
5. Initialize SQLite buffer
6. Start app activity collector (background thread)
7. Start network/domain collector (background thread)
8. Start session manager
9. Send initial session payload (`session_end: null`)
10. Start periodic sender (5-min timer)
11. Start session updater (15-min timer)
12. Register signal handlers (graceful shutdown)

### 8.2 — Main loop

- Keep main thread alive
- Handle OS signals: `SIGTERM`, `SIGINT` → graceful shutdown
- Handle `SIGHUP` → reload config (Linux/macOS)
- Watchdog: restart collectors if they crash

### 8.3 — Shutdown sequence

1. Stop collectors
2. Flush all pending data from collectors to SQLite
3. Run final send cycle (attempt to push everything)
4. Send session end payload (`session_end: now`)
5. Close SQLite connection
6. Exit cleanly

### 8.4 — Error isolation

- Each collector runs in its own thread with try/except
- Collector crash → log error, restart after 10 seconds
- Sender crash → log error, restart after 30 seconds
- Main thread never crashes (catch-all exception handler)

### 8.5 — Thread management

- `AppCollectorThread` — daemon thread, polls every 1 second
- `NetworkCollectorThread` — daemon thread, polls every 5 seconds
- `SenderThread` — daemon thread, runs every 5 minutes
- `SessionUpdaterThread` — daemon thread, runs every 15 minutes
- All threads share access to SQLite (use threading.Lock for writes)

---

## Phase 9: Setup / First Launch UI

**Goal:** One-time authentication and device registration.

### 9.1 — Decide on UI approach

- Option A: CLI-based (terminal input) — simplest, good for MVP
- Option B: Simple GUI (tkinter) — better UX, cross-platform
- Option C: System tray with dialog — best UX, more complex
- **Recommendation:** Start with CLI (Phase 9A), add GUI later (Phase 15)

### 9.2 — CLI setup flow

1. Print welcome message
2. Prompt: "Enter your Employee Code: "
3. Look up employee_id from code (may need a lookup endpoint or manual entry of numeric ID)
4. Prompt: "Enter your TOTP code: "
5. Call `POST /api/v1/auth/verify`
6. On success: store `employee_id` in SQLite config
7. Auto-detect MAC address, hostname, IP
8. Call `POST /api/v1/devices/`
9. On success: store device info in SQLite config
10. Print "Setup complete. Agent is now running."

### 9.3 — Error handling

- Invalid TOTP → retry up to 3 times
- Network error → retry with backoff
- Employee not found → prompt to re-enter code
- Device already registered → use existing registration (idempotent)

---

## Phase 10: System Tray / Background Service

**Goal:** Run agent invisibly with minimal user interaction.

### 10.1 — System tray icon

- Library: `pystray` (cross-platform)
- Icon: small monitoring icon (green = connected, yellow = buffering, red = error)
- Menu options:
  - "Status: Connected" (read-only)
  - "Employee: Rahul Shah" (read-only)
  - "Pause Monitoring" (toggle)
  - "View My Stats" (opens browser to dashboard)
  - "About"
  - "Quit"

### 10.2 — Auto-start on boot

- Windows: registry key `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` or Task Scheduler
- macOS: LaunchAgent plist in `~/Library/LaunchAgents/`
- Linux: systemd user service or `~/.config/autostart/` desktop entry

### 10.3 — Background process management

- Run as background process (not blocking terminal)
- PID file to prevent duplicate instances
- Lock file: `agent.lock` in data directory

---

## Phase 11: Testing

### 11.1 — Unit tests

- Platform abstraction: mock OS calls, verify outputs
- Categorization: test all matching rules
- Session manager: test merging, splitting, dedup logic
- SQLite buffer: test CRUD operations
- API sender: mock HTTP responses, verify retry logic

### 11.2 — Integration tests

- Full pipeline: collector → session manager → buffer → sender
- Mock API server (Flask/FastAPI local)
- Verify payload format matches spec exactly
- Verify timing (5-min batches, 15-min session updates)

### 11.3 — Platform tests

- Test on Windows 10/11
- Test on macOS 13+ (Ventura+)
- Test on Ubuntu 22.04+
- Verify foreground app detection works on each
- Verify network capture works on each
- Verify idle detection works on each

### 11.4 — Edge case tests

- Agent starts with no network → buffers locally → sends when network returns
- Agent crashes mid-send → restart, verify no duplicate data
- User locks screen → idle detection activates
- User switches apps rapidly → debounce works
- VPN enabled → domain resolution still works
- Multiple browsers open simultaneously
- Very long session (8+ hours) → no memory leak, no data loss

### 11.5 — Performance tests

- Memory usage < 50 MB steady state
- CPU usage < 2% average
- SQLite database size stays manageable (auto-cleanup)
- No disk thrashing

---

## Phase 12: Packaging & Distribution

### 12.1 — PyInstaller build

- Single executable per platform
- Bundle all dependencies
- Bundle `categories.json`
- Bundle icon assets
- Test: run built executable on clean machine (no Python installed)

### 12.2 — Installer creation

- Windows: NSIS or Inno Setup → `.exe` installer
  - Install to `C:\Program Files\LocalMonitorAgent\`
  - Create Start Menu shortcut
  - Register auto-start
  - Create uninstaller
- macOS: `.dmg` or `.pkg`
  - Install to `/Applications/LocalMonitorAgent.app`
  - Register LaunchAgent
- Linux: `.deb` package or AppImage
  - Install to `/opt/local-monitor-agent/`
  - Register systemd service

### 12.3 — Versioning

- Semantic versioning: `1.0.0`
- Version embedded in binary
- Version sent to backend with every request (`X-Agent-Version` header)

---

## Phase 13: Pilot Deployment

### 13.1 — Internal testing (2-3 people)

- Install on own machines
- Run for 48 hours
- Verify data appears in backend
- Check for bugs, crashes, data gaps

### 13.2 — Small pilot (5-10 employees)

- Deploy via installer
- Run for 1 week
- Monitor backend for data quality
- Collect feedback on:
  - Performance impact noticed?
  - Any crashes?
  - System tray working?
  - Auto-start working?

### 13.3 — Data validation

- Cross-check app usage with manual observation
- Cross-check domain visits with browser history (voluntary)
- Verify no full URLs or sensitive data leaking
- Verify session timing accuracy

---

## Phase 14: Hardening & Optimization

### 14.1 — Security hardening

- Encrypt SQLite database (SQLCipher or application-level encryption)
- Obfuscate API key storage (not plaintext in config)
- Certificate pinning for backend API (optional)
- Anti-tampering: detect if agent binary modified
- Secure config file permissions (read-only for non-admin)

### 14.2 — Performance optimization

- Profile memory usage, fix leaks
- Optimize polling intervals based on real-world data
- Reduce DNS lookups (better caching)
- Batch SQLite writes (transaction batching)
- Compress payloads if large (gzip)

### 14.3 — Reliability

- Watchdog process that restarts agent if it crashes
- Health check endpoint (agent reports own status)
- Heartbeat to backend every 5 minutes
- Alert backend if agent hasn't reported in 30 minutes

---

## Phase 15: GUI Enhancement (Post-MVP)

### 15.1 — Setup wizard

- Replace CLI with tkinter/PyQt wizard
- Step 1: Enter employee code
- Step 2: Enter TOTP
- Step 3: Confirm device info
- Step 4: "Setup complete" with checkbox for auto-start

### 15.2 — Status dashboard

- Small window showing:
  - Current status (monitoring / paused / error)
  - Today's active time
  - Top 3 apps used
  - Network status
  - Last sync time

### 15.3 — Notifications

- "Agent started" notification on boot
- "Sync failed — will retry" if network down
- "Agent updated to v1.1.0" after auto-update

---

## Phase 16: Auto-Update Mechanism (Post-MVP)

### 16.1 — Update check

- On startup: `GET /api/v1/agent/latest-version`
- Compare with current version
- If newer: download update

### 16.2 — Update flow

- Download new binary to temp directory
- Verify checksum/signature
- Replace current binary
- Restart agent

### 16.3 — Rollback

- Keep previous version as backup
- If new version crashes 3 times → rollback to previous

---

## Execution Order Summary

| Order | Phase                             | Priority | Estimated Effort |
| ----- | --------------------------------- | -------- | ---------------- |
| 1     | Phase 0: Project Setup            | Critical | 1 day            |
| 2     | Phase 1: Platform Abstraction     | Critical | 3 days           |
| 3     | Phase 2: App Activity Collector   | Critical | 3 days           |
| 4     | Phase 6: Local Buffer (SQLite)    | Critical | 2 days           |
| 5     | Phase 4: Categorization Module    | High     | 1 day            |
| 6     | Phase 5: Session Manager          | High     | 2 days           |
| 7     | Phase 7: API Sender               | Critical | 2 days           |
| 8     | Phase 8: Agent Core               | Critical | 2 days           |
| 9     | Phase 9: Setup / First Launch     | Critical | 1 day            |
| 10    | Phase 3: Network/Domain Collector | High     | 4 days           |
| 11    | Phase 10: System Tray             | Medium   | 2 days           |
| 12    | Phase 11: Testing                 | Critical | 3 days           |
| 13    | Phase 12: Packaging               | High     | 2 days           |
| 14    | Phase 13: Pilot                   | High     | 5 days           |
| 15    | Phase 14: Hardening               | Medium   | 3 days           |
| 16    | Phase 15: GUI                     | Low      | 3 days           |
| 17    | Phase 16: Auto-Update             | Low      | 3 days           |

**Total estimated: ~42 working days for full build**
**MVP (Phases 0–9, 11–12): ~22 working days**

---

## Dependencies List

| Package               | Purpose                                         |
| --------------------- | ----------------------------------------------- |
| `psutil`              | Process info, network connections, system stats |
| `requests` or `httpx` | HTTP client for API calls                       |
| `pystray`             | System tray icon (Phase 10)                     |
| `Pillow`              | Icon image for system tray                      |
| `scapy`               | DNS sniffing (Phase 3, optional)                |
| `pyobjc`              | macOS-specific APIs (macOS only)                |
| `pyinstaller`         | Packaging into executable                       |
| `pytest`              | Testing                                         |

---

## File Structure

```
local-monitor-agent/
├── src/
│   ├── __init__.py
│   ├── main.py                    # Entry point
│   ├── agent_core.py              # Orchestrator (Phase 8)
│   ├── config.py                  # Constants, config loading
│   ├── platform/
│   │   ├── __init__.py
│   │   ├── base.py                # Abstract interface
│   │   ├── windows.py             # Windows implementation
│   │   ├── macos.py               # macOS implementation
│   │   └── linux.py               # Linux implementation
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── app_collector.py       # Phase 2
│   │   └── network_collector.py   # Phase 3
│   ├── categorization/
│   │   ├── __init__.py
│   │   └── categorizer.py         # Phase 4
│   ├── session/
│   │   ├── __init__.py
│   │   └── session_manager.py     # Phase 5
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sqlite_buffer.py       # Phase 6
│   ├── network/
│   │   ├── __init__.py
│   │   └── api_sender.py          # Phase 7
│   ├── setup/
│   │   ├── __init__.py
│   │   └── first_launch.py        # Phase 9
│   └── ui/
│       ├── __init__.py
│       └── tray.py                # Phase 10
├── data/
│   └── categories.json            # Default category rules
├── assets/
│   └── icon.png                   # Tray icon
├── tests/
│   ├── test_app_collector.py
│   ├── test_network_collector.py
│   ├── test_categorizer.py
│   ├── test_session_manager.py
│   ├── test_sqlite_buffer.py
│   └── test_api_sender.py
├── scripts/
│   ├── build_windows.bat
│   ├── build_macos.sh
│   └── build_linux.sh
├── requirements.txt
├── pyproject.toml
├── README.md
└── .gitignore
```
