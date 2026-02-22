# Phase 15: GUI Enhancement — Detailed Plan

---

## 15.0 — Decision: tkinter vs PyQt vs Custom

- **tkinter** — ships with Python, no extra dependency, works with PyInstaller, looks basic but functional.
- **PyQt/PySide** — better looking, heavier dependency (~50MB added to exe), licensing considerations.
- **Decision: tkinter.** Already available. Keeps exe small. Good enough for setup wizard + status window.

---

## 15.1 — Setup Wizard (Replace CLI)

Currently: `first_launch.py` uses `input()` and `getpass.getpass()`. Fails silently when exe runs in windowed mode (no stdin).

### 15.1.1 — Wizard Window

- 4-step wizard using `tkinter.Toplevel` or frame switching
- **Step 1:** Employee ID input (numeric field + "Next" button)
- **Step 2:** Password (masked entry) + TOTP code (6-digit entry) + "Verify" button
- **Step 3:** Device info confirmation (hostname, MAC, IP, device type — read-only labels) + "Register" button
- **Step 4:** Success screen ("Welcome, {name}! Agent is running.") + checkbox "Start on boot" + "Done" button
- Error messages displayed inline (red label below inputs), not popups
- Loading spinner or "Verifying..." label during API calls
- API calls run in background thread to avoid freezing GUI
- Window centered on screen, non-resizable, ~400x350px
- Agent icon in window title bar

### 15.1.2 — Integration with Agent Core

- `agent_core.py` `_ensure_configured()`: if no stdin (windowed mode) → launch GUI wizard instead of CLI
- If both stdin and GUI available → prefer GUI
- CLI still works for `--setup` flag (backward compat)
- Wizard returns `True/False` like CLI version
- Same backend calls: `POST /api/v1/auth/login`, `POST /api/v1/devices/`

### 15.1.3 — File Changes

- New: `src/ui/setup_wizard.py`
- Modify: `src/agent_core.py` (call wizard when no terminal)
- Modify: `src/setup/first_launch.py` (add `run_first_launch_gui()` export)

---

## 15.2 — Status Dashboard Window

Accessible from system tray menu → "View Status" (new menu item).

### 15.2.1 — Window Layout

- Small window (~450x400px), non-modal, closable (hides, doesn't quit agent)
- **Header:** Agent name + version + status indicator (green/yellow/red dot)
- **Identity section:** Employee name, ID, device MAC
- **Session section:**
  - Session started: timestamp
  - Active time: `Xh Ym`
  - Idle time: `Xh Ym`
  - Upload/Download: `X MB / Y MB`
- **Buffer section:**
  - Pending records: count
  - Last sync: timestamp or "Never"
  - DB size: `X.XX MB`
- **Sender section:**
  - Status: Connected / Auth Error / Offline
  - Total sent / failed
- **Footer:** "Close" button

### 15.2.2 — Auto-refresh

- Timer: refresh data every 10 seconds while window is visible
- Use `window.after(10000, refresh)` — tkinter-native, no extra thread
- Only refresh when window is open (not when hidden)

### 15.2.3 — File Changes

- New: `src/ui/status_window.py`
- Modify: `src/ui/tray.py` (add "View Status" menu item, open window on click)

---

## 15.3 — Toast Notifications

### 15.3.1 — Cross-platform approach

- **Windows:** Use `win10toast` or `plyer` library, or `ctypes` + Shell_NotifyIcon
- **macOS:** `osascript -e 'display notification ...'`
- **Linux:** `notify-send` command
- **Decision:** Use tray icon's built-in `notify()` method from `pystray` (if available). Fallback: skip.

### 15.3.2 — Notification events

- Agent started: "Local Monitor Agent is running" (on boot/startup)
- Sync failed: "Could not reach server. Data buffered locally." (on first failure, not every retry)
- Auth error: "Authentication failed. Check your API key." (once per cooldown)
- Pause/Resume: "Monitoring paused" / "Monitoring resumed"
- No spamming: each notification type has a cooldown (minimum 5 minutes between same type)

### 15.3.3 — File Changes

- New: `src/ui/notifications.py`
- Modify: `src/agent_core.py` (trigger notifications on events)
- Modify: `src/network/api_sender.py` (expose callback hook for sync failures)

---

## 15.4 — Tray Menu Enhancement

### Current menu:

```
Status: Running
Employee ID: 6
──────────────
Pause Monitoring
View My Stats
✓ Auto-start Enabled
──────────────
Monitor Agent v1.0.0
Quit Agent
```

### New menu:

```
Status: Running (●)
Employee: Rahul Shah (ID: 6)
──────────────
Pause Monitoring
View Status          ← NEW (opens status window)
View Dashboard       (renamed from "View My Stats")
✓ Auto-start Enabled
──────────────
Monitor Agent v1.0.0
Quit Agent
```

### File Changes

- Modify: `src/ui/tray.py`

---

## Execution Order

| Step | What                                  | Files                                     | Effort |
| ---- | ------------------------------------- | ----------------------------------------- | ------ |
| 1    | Setup wizard (`setup_wizard.py`)      | New `src/ui/setup_wizard.py`              | 1.5 hr |
| 2    | Integrate wizard into agent core      | Modify `agent_core.py`, `first_launch.py` | 30 min |
| 3    | Status dashboard window               | New `src/ui/status_window.py`             | 1 hr   |
| 4    | Notifications module                  | New `src/ui/notifications.py`             | 45 min |
| 5    | Tray menu enhancement                 | Modify `src/ui/tray.py`                   | 30 min |
| 6    | Wire notifications into core + sender | Modify `agent_core.py`, `api_sender.py`   | 30 min |
| 7    | Tests                                 | New `tests/test_gui.py`                   | 1 hr   |

**Total: ~5-6 hours**

---

## New Files

- `src/ui/setup_wizard.py`
- `src/ui/status_window.py`
- `src/ui/notifications.py`
- `tests/test_gui.py`

## Modified Files

- `src/agent_core.py` — wizard fallback, notification triggers
- `src/setup/first_launch.py` — export `run_first_launch_gui`
- `src/ui/tray.py` — new menu items, status window launch
- `src/network/api_sender.py` — notification callback hook

---

# Phase 15 Summary

## Status: COMPLETE

### Tests: 393 passed, 1 skipped (Windows permissions skip from Phase 14)

---

## What Was Delivered

| Item               | Description                                                     | Status |
| ------------------ | --------------------------------------------------------------- | ------ |
| Setup Wizard GUI   | tkinter-based login dialog for windowed exe mode                | ✅     |
| Agent Core         | fallback Auto-selects CLI vs GUI based on terminal availability | ✅     |
| Tray employee name | Shows employee name + ID instead of just ID                     | ✅     |
| Tray menu rename   | "View My Stats" → "View Dashboard"                              | ✅     |
| Status dict update | get_status() includes employee_name from buffer                 | ✅     |

---

## New Files

- src/ui/setup_wizard.py — tkinter 4-step wizard (login → device confirm → success → done)
- tests/test_gui.py — 23 tests

## Modified Files

- src/agent_core.py — \_ensure_configured() now tries CLI first (if terminal), falls back to GUI wizard (if tkinter available), fails if neither available. GUI path does not call register_autostart (wizard has checkbox). Added employee_name to get_status().

- src/ui/tray.py — \_employee_text() shows name + ID from status dict. "View My Stats" renamed to "View Dashboard".

## Setup Wizard Details

- Step 1: Employee ID (numeric input)
- Step 2: Password (masked) + TOTP code + "Login & Setup" button
- Step 3: API calls run in background thread (no GUI freeze)
- Step 4: Success screen with device info + "Start on boot" checkbox + "Done" button
- Error messages shown inline (red label), not popups
- Window: 420×400px, centered, non-resizable, agent icon in title bar
- Device registration failure does not block setup completion
- Returns True/False to agent core like CLI version

## Decision Log

- Chose tkinter over PyQt: ships with Python, no extra dependency, keeps exe small
- No status dashboard window: dashboard is on the website
- No toast notifications: kept scope minimal (background process)

## Test Breakdown (23 new tests in test_gui.py)

| Test Class               | Count | What                                                        |
| ------------------------ | ----- | ----------------------------------------------------------- |
| TestSetupWizardModule    | 7     | tkinter availability, device type detection, error handling |
| TestWizardLoginLogic     | 4     | Login success/failure/network error without launching GUI   |
| TestAgentCoreGUIFallback | 6     | CLI vs GUI selection, autostart behavior per path           |
| TestStatusEmployeeName   | 2     | employee_name in status dict                                |
| TestTrayEmployeeText     | 4     | Tray menu text with name/ID/fallback                        |

---

**Phase 15: Yes, fully done.** Scope was setup wizard GUI + tray improvements. Delivered.

**How testing works:** pytest finds all `test_*.py` files. Each test uses `unittest.mock.patch` to replace real OS/network/API calls with fakes. `responses` library intercepts HTTP requests. `tmp_path` gives each test a fresh temp directory. Tests verify return values, state changes, and method calls — no real servers or GUIs are launched.

**Phase 16: Done.** 435 passed, 1 skipped. Clean.

---

# Phase 16 Summary

## Status: COMPLETE

**Tests: 435 passed, 1 skipped**

---

## What Was Delivered

| Item                   | Description                                                                        | Status |
| ---------------------- | ---------------------------------------------------------------------------------- | ------ |
| Version comparison     | Semantic version comparison (major.minor.patch)                                    | ✅     |
| Update check           | `GET /api/v1/agent/latest-version` → compare with current                          | ✅     |
| Binary download        | Downloads new exe to temp dir with streaming                                       | ✅     |
| Checksum verification  | SHA-256 verification of downloaded binary                                          | ✅     |
| Backup before update   | Copies current exe to `.exe.backup` before replacing                               | ✅     |
| Update scripts         | Platform-specific scripts (`.bat` / `.sh`) to replace running exe                  | ✅     |
| Rollback               | Restores `.exe.backup` if available                                                | ✅     |
| Crash tracking         | Records crash count in SQLite, auto-rollback after 3 consecutive crashes           | ✅     |
| Periodic check         | Checks for updates every 24 hours in main loop                                     | ✅     |
| Agent core integration | Crash recording on fatal error, clean start reset, update status in `get_status()` | ✅     |

---

## New Files

- `src/utils/updater.py` — `Updater` class + `UpdateInfo` dataclass
- `tests/test_updater.py` — 42 tests

## Modified Files

- `src/agent_core.py` — Added `_updater` component, `_check_crash_rollback()` on startup, `_check_for_updates()` in main loop, crash recording in exception handler, `record_clean_start()` after successful startup, `update_available` in status dict

---

## Update Flow

```
Main loop (every 24h)
  → GET /api/v1/agent/latest-version
  → Compare remote vs current version
  → If newer:
      → Download binary to temp dir
      → Verify SHA-256 checksum
      → Backup current exe → .exe.backup
      → Launch update script (bat/sh)
      → Shutdown agent
      → Script waits 3s, replaces exe, restarts
      → If replace fails → restores backup
```

## Crash Rollback Flow

```
Agent starts
  → Read crash_count from SQLite
  → If crash_count >= 3:
      → Copy .exe.backup over current exe
      → Reset crash_count to 0
      → Continue running (rollback takes effect next launch)
  → After successful startup:
      → Set crash_count = 0
  → On fatal exception:
      → Increment crash_count
```

---

## Test Breakdown (42 new tests in `test_updater.py`)

| Test Class                     | Count | What                                                    |
| ------------------------------ | ----- | ------------------------------------------------------- |
| TestVersionComparison          | 12    | Major/minor/patch/same/older/partial/prerelease/invalid |
| TestUpdateCheck                | 8     | Backend responses, intervals, no-URL, exceptions        |
| TestChecksumVerification       | 5     | Valid/invalid/empty/missing/case-insensitive            |
| TestCrashTracking              | 8     | Increment/reset/threshold/invalid/missing               |
| TestApplyUpdate                | 3     | Not-frozen/missing-binary/backup-creation               |
| TestRollback                   | 3     | Not-frozen/no-backup/restore                            |
| TestAgentCoreUpdateIntegration | 3     | Status dict, crash recording, clean start               |

---

## All Phases Complete

| Phase     | Description              | Status | Tests            |
| --------- | ------------------------ | ------ | ---------------- |
| 0         | Project Setup            | ✅     | —                |
| 1         | Platform Abstraction     | ✅     | 15               |
| 2         | App Activity Collector   | ✅     | 14               |
| 3         | Network/Domain Collector | ✅     | 48               |
| 4         | Categorization Module    | ✅     | 48               |
| 5         | Session Manager          | ✅     | 26               |
| 6         | Local Buffer (SQLite)    | ✅     | 38               |
| 7         | API Sender               | ✅     | 25               |
| 8         | Agent Core               | ✅     | 17               |
| 9         | First Launch Setup       | ✅     | (in Phase 8)     |
| 10        | System Tray              | ✅     | 29               |
| 11        | Testing                  | ✅     | (all phases)     |
| 12        | Packaging                | ✅     | 28               |
| 13        | Pilot Deployment         | ✅     | 44               |
| 14        | Hardening & Optimization | ✅     | 37               |
| 15        | GUI Enhancement          | ✅     | 23               |
| 16        | Auto-Update              | ✅     | 42               |
| **Total** |                          |        | **435 + 1 skip** |
