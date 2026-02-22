# Summary 4: Phase 13 Completion + Auth/Domain Reliability Fixes

## Date

- February 20, 2026

---

## Final Status

- **Phase 13 is complete.**
- Core packaging/deployment/ops features are delivered.
- Auth loading issues in bundled exe are fixed.
- Domain capture reliability for real browser traffic is improved.

---

## Two Important Observations

1. **Console doesn't hide when launched from terminal**

- `_hide_console()` uses `GetConsoleWindow`.
- This does not hide the console if exe is started from an existing terminal (terminal owns the console).
- It behaves correctly when exe is launched by double-click from Explorer.
- This is expected behavior.

2. **401 retry spam behavior**

- Sender attempts all failed records each cycle even after auth failure.
- It should stop current cycle after first `401/403` to avoid hammering.
- This is a **Phase 14 optimization**, not a Phase 13 blocker.

---

## Phase 13 Delivered

| Step | What                                                                         | Status      |
| ---- | ---------------------------------------------------------------------------- | ----------- |
| 1    | Auto-start on boot (Windows/macOS/Linux)                                     | ✅ 27 tests |
| 2    | CLI arguments (`--version`, `--status`, `--reset`, `--uninstall`, `--setup`) | ✅ 17 tests |
| 3    | Install/uninstall scripts (`.bat` + `.ps1`)                                  | ✅          |
| 4    | Health check script (standalone)                                             | ✅          |
| 5    | Documentation (3 docs)                                                       | ✅          |
| 6    | Rebuild exe with all changes                                                 | ✅ 19.6 MB  |

**Phase 13 test milestone:** `331 passed, 0 failed`

---

## New Files Created

- `src/utils/__init__.py`
- `src/utils/autostart.py`
- `tests/test_autostart.py`
- `tests/test_cli.py`
- `scripts/install_windows.bat`
- `scripts/install_windows.ps1`
- `scripts/uninstall_windows.bat`
- `scripts/health_check.py`
- `docs/DEPLOYMENT_GUIDE.md`
- `docs/USER_GUIDE.md`
- `docs/PILOT_CHECKLIST.md`

---

## Modified Files (Phase 13)

- `src/main.py` (CLI args + console hiding)
- `src/agent_core.py` (auto-start integration)
- `src/ui/tray.py` (auto-start toggle menu item)
- `tests/test_agent_core.py` (fixed `_verify_totp` → `_verify_login`)
- `local-monitor-agent.spec` (`console=True` + hidden import updates)

---

## Additional Fixes Completed After Phase 13

### 1) Bundled exe auth fix (`401`)

**Problem**

- `%APPDATA%\LocalMonitorAgent\.env` had BOM (`EF BB BF`), causing key parse as `\ufeffAPI_KEY`.

**Changes**

- `src/config.py`
  - Read env with `encoding="utf-8-sig"`
  - Defensive key cleanup: `lstrip("\ufeff")`
- `scripts/install_windows.ps1`
  - Write `.env` with `utf8NoBOM`

**Result**

- Bundled exe now loads `API_KEY` correctly.
- Repeated auth `401` due to missing key resolved.

### 2) Better sender debugging for backend failures

**File:** `src/network/api_sender.py`

- Added richer diagnostics for timeout/connection/request exceptions and `5xx`.
- Logs now include:
  - table + record id
  - URL
  - retry count
  - truncated response text
  - safe payload summary
- Helpers added:
  - `_truncate_text(...)`
  - `_payload_debug(...)`

### 3) Domain capture reliability upgrade

**File:** `src/collectors/network_collector.py`

- Added UDP flow capture for monitored ports (including UDP 443 / QUIC).
- Kept TCP requirement as established connections.
- Added periodic Windows DNS cache refresh during polling (every 30s).
- Extended DNS parser to include `AAAA` record parsing.

**Result**

- Better capture of domains from real browser traffic while preserving privacy model (domain only, no full URLs/content).

---

## Data Stored for Domain Visits (DB Format)

Stored in `pending_domain_visits.payload_json`:

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

SQL row also contains operational metadata:

- `id`
- `created_at`
- `retry_count`
- `last_retry_at`
- `status` (`pending` / `failed` / `sent`)

---

## Remaining from Original Plan

| Phase | Status                                 |
| ----- | -------------------------------------- |
| 14    | Hardening & Optimization — not started |
| 15    | GUI Enhancement — not started          |
| 16    | Auto-Update — not started              |

---

## Note on Test Counts

- Phase 13 completion milestone recorded as **331 passing**.
- Current working tree validation later reached **333 passing** after additional post-phase fixes/tests.
