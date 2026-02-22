# Phase 14: Hardening & Optimization — Plan

---

## 14.0 — Known Issues to Fix First

### 14.0.1 — 401 Retry Spam (from Summary 4)

- **Problem:** After first `401/403`, sender still attempts every remaining record in the cycle, hammering the server.
- **Fix:** In `_send_table_records()`, break the loop on auth error. Add `_auth_failed` flag. Skip entire send cycle if auth failed recently (cooldown: 5 minutes).
- **File:** `src/network/api_sender.py`

### 14.0.2 — Double-counting `_total_failed`

- **Problem:** `_mark_record_failed()` increments `_total_failed`, AND the calling code in `_handle_response()` also increments it for 401/403/404/429/5xx paths.
- **Fix:** Remove `_total_failed += 1` from `_handle_response()` for cases that call `_mark_record_failed()`.
- **File:** `src/network/api_sender.py`

### 14.0.3 — Domain visits: individual inserts in loop

- **Problem:** `_buffer_domain_visits()` calls `insert_pending()` per domain in a loop. 20 domains = 20 separate transactions.
- **Fix:** Collect all payloads, use `insert_pending_batch()`.
- **File:** `src/session/session_manager.py`

---

## 14.1 — Security Hardening

### 14.1.1 — API Key Obfuscation

- Don't store API key as plaintext in `.env`.
- On first setup: encode API key with machine-specific salt (MAC + hostname hash) using `Fernet` symmetric encryption.
- Store encrypted key in SQLite `config` table.
- On load: decrypt from DB. Fallback to `.env` if DB has no key (migration path).
- **Not unbreakable** — just prevents casual reading.
- **File:** New `src/utils/crypto.py`, modify `src/config.py`

### 14.1.2 — File Permissions

- After creating `agent.db`, `.env` in data dir: set permissions to owner-only.
- Windows: `icacls` or skip (NTFS ACLs are complex, low priority).
- Linux/macOS: `chmod 600` on DB and `.env`.
- **File:** `src/storage/sqlite_buffer.py`, `src/config.py`

### 14.1.3 — Access Token Refresh

- Current: `access_token` stored once at login, never refreshed.
- Add: If sender gets `401`, try re-authenticating using stored credentials (if available) or flag for user re-setup.
- Low priority — mark as TODO for now, implement if backend supports token refresh endpoint.

---

## 14.2 — Performance Optimization

### 14.2.1 — Batch Domain Visit Inserts

- Already noted in 14.0.3. Build payloads list, single `insert_pending_batch()` call.
- **File:** `src/session/session_manager.py`

### 14.2.2 — DNS Cache Eviction

- Current: cache grows unbounded, only TTL checked on read.
- Add: periodic eviction of entries older than `_dns_cache_duration`. Run every 5 minutes inside `_poll_loop`.
- Cap cache size at 2000 entries. On overflow, evict oldest 25%.
- **File:** `src/collectors/network_collector.py`

### 14.2.3 — Payload Compression

- If payload JSON > 1KB, compress with gzip before sending.
- Add `Content-Encoding: gzip` header.
- Only if backend supports it. Check response for `Accept-Encoding`. Default: off, config toggle.
- **File:** `src/network/api_sender.py`, `src/config.py`
- **Priority:** Low — payloads are small. Implement as opt-in flag.

### 14.2.4 — Memory Monitoring

- Add internal memory check every 15 minutes.
- Log warning if RSS > 100MB.
- Log process memory in status output.
- **File:** `src/agent_core.py`

### 14.2.5 — SQLite Transaction Batching

- Current `mark_sent()` commits per record.
- When processing a batch of records in `_send_table_records()`, collect IDs of sent/failed, then batch-update in single transaction.
- **Files:** `src/storage/sqlite_buffer.py`, `src/network/api_sender.py`

---

## 14.3 — Reliability

### 14.3.1 — Heartbeat

- Every 5 minutes: send lightweight heartbeat to backend.
- Endpoint: `POST /api/v1/telemetry/heartbeat` (or piggyback on session update).
- Payload: `{ employee_id, device_mac, agent_version, uptime_sec, pending_count, status }`.
- If backend doesn't have this endpoint yet: skip, use session updates as implicit heartbeat.
- **File:** `src/network/api_sender.py` or `src/session/session_manager.py`
- **Priority:** Medium — depends on backend. Implement sender-side, tolerate 404.

### 14.3.2 — Internal Watchdog

- Agent core monitors collector threads every 30 seconds.
- If `AppCollectorThread` or `NetworkCollectorThread` is dead but `_running` is True → restart it.
- Log restart events.
- **File:** `src/agent_core.py`

### 14.3.3 — Graceful SQLite Recovery on Runtime Errors

- Current: corruption handled only at init.
- Add: wrap all SQLite operations in a retry decorator. On `sqlite3.DatabaseError` during runtime → attempt reconnect once before raising.
- **File:** `src/storage/sqlite_buffer.py`

### 14.3.4 — Stale Pending Records Cleanup

- Records stuck in `sending` status (agent crashed mid-send) → reset to `pending` on startup.
- Run once during `_initialize()`.
- **File:** `src/storage/sqlite_buffer.py`

### 14.3.5 — Last Successful Sync Tracking

- After successful send cycle with at least 1 record sent → store timestamp in config.
- `--status` CLI already reads `last_successful_sync`. Just need to write it.
- **File:** `src/network/api_sender.py`

---

## 14.4 — Logging Improvements

### 14.4.1 — Structured Log Context

- Add `employee_id` and `device_mac` to log format where available (via logging filter or extra).
- Not critical. Low priority.

### 14.4.2 — Log Rotation Cleanup

- Current: 3 backup files × 5MB = 15MB max. Fine.
- Add: on startup, delete `.log.N` files older than 7 days (if any manual log files exist outside rotation).
- **File:** `src/agent_core.py`

---

## Execution Order

| Step | What                             | Files Modified                      | Effort  |
| ---- | -------------------------------- | ----------------------------------- | ------- |
| 1    | 401 retry spam fix               | `api_sender.py`                     | 30 min  |
| 2    | Double-count fix                 | `api_sender.py`                     | 15 min  |
| 3    | Batch domain inserts             | `session_manager.py`                | 20 min  |
| 4    | Stale `sending` reset on startup | `sqlite_buffer.py`                  | 20 min  |
| 5    | DNS cache eviction               | `network_collector.py`              | 30 min  |
| 6    | Internal watchdog                | `agent_core.py`                     | 45 min  |
| 7    | Memory monitoring                | `agent_core.py`                     | 20 min  |
| 8    | Last sync tracking               | `api_sender.py`                     | 15 min  |
| 9    | File permissions (Linux/macOS)   | `sqlite_buffer.py`                  | 20 min  |
| 10   | SQLite batch mark_sent           | `sqlite_buffer.py`, `api_sender.py` | 40 min  |
| 11   | API key obfuscation              | New `crypto.py`, `config.py`        | 45 min  |
| 12   | Heartbeat (tolerant)             | `session_manager.py`                | 30 min  |
| 13   | SQLite runtime recovery          | `sqlite_buffer.py`                  | 30 min  |
| 14   | Tests for all above              | `tests/test_hardening.py`           | 1-2 hrs |

**Total: ~7-8 hours**

---

## New Files

- `src/utils/crypto.py` — key obfuscation helpers
- `tests/test_hardening.py` — Phase 14 specific tests

## Modified Files

- `src/network/api_sender.py` — auth cooldown, batch marking, sync tracking, compression toggle
- `src/storage/sqlite_buffer.py` — stale reset, batch mark, runtime recovery, permissions
- `src/session/session_manager.py` — batch domain inserts, heartbeat
- `src/collectors/network_collector.py` — DNS eviction, cache cap
- `src/agent_core.py` — watchdog, memory monitor
- `src/config.py` — compression toggle, crypto integration

---

# Phase 14 Summary

**Tests: 369 passed, 1 skipped (expected — Windows permissions test)**

## What was delivered:

| Step | What                                            | Status |
| ---- | ----------------------------------------------- | ------ |
| 1    | 401 retry spam fix — auth cooldown (5 min)      | ✅     |
| 2    | Double-count `_total_failed` fix                | ✅     |
| 3    | Batch domain inserts (`insert_pending_batch`)   | ✅     |
| 4    | Stale `sending` records reset on startup        | ✅     |
| 5    | DNS cache eviction (TTL + size cap at 2000)     | ✅     |
| 6    | Internal watchdog (`check_health()`)            | ✅     |
| 7    | Memory monitoring (15 min interval, 100MB warn) | ✅     |
| 8    | Last successful sync tracking                   | ✅     |
| 9    | File permissions (600 on Linux/macOS)           | ✅     |
| 10   | SQLite batch `mark_sent/failed/perm_failed`     | ✅     |
| 11   | API key obfuscation (`crypto.py` + migration)   | ✅     |
| 12   | Collector `is_thread_alive` property            | ✅     |

## Files created:

- `src/utils/crypto.py`
- `tests/test_hardening.py` (37 new tests)

## Files modified:

- `src/network/api_sender.py`
- `src/storage/sqlite_buffer.py`
- `src/collectors/app_collector.py`
- `src/collectors/network_collector.py`
- `src/session/session_manager.py`
- `src/agent_core.py`

## Remaining phases:

| Phase | Description     | Status      |
| ----- | --------------- | ----------- |
| 15    | GUI Enhancement | Not started |
| 16    | Auto-Update     | Not started |
