# Phase 13: Pilot Deployment — Plan

## 13.0 — Pre-Deployment Fixes

Before deploying to anyone, these gaps need closing:

- **Auto-start on boot** — not implemented yet. Agent must survive reboots.
  - Windows: Add registry key `HKCU\...\Run` or Task Scheduler entry
  - Should be set during first launch setup automatically
  - Tray menu option to enable/disable

- **Command-line arguments** — admin needs `--status`, `--reset`, `--version` without launching full agent
  - `--version` → print version, exit
  - `--status` → read SQLite, print health info, exit
  - `--reset` → clear identity config (force re-setup), exit
  - `--uninstall` → remove auto-start, clean data, exit

- **Graceful first-launch in exe** — currently requires terminal. Need a fallback:
  - If exe launched without prior setup → show a simple tkinter dialog instead of CLI prompts
  - Or: provide a separate `setup.bat` that runs exe with `--setup` flag in console mode

---

## 13.1 — Windows Installer Script

**`scripts/install_windows.bat`**

- Copies `LocalMonitorAgent.exe` to `%LOCALAPPDATA%\Programs\LocalMonitorAgent\`
- Creates `%APPDATA%\LocalMonitorAgent\.env` with API key (prompted or passed as arg)
- Registers auto-start (registry)
- Creates Start Menu shortcut
- Creates desktop shortcut (optional)
- Launches agent for first-time setup

**`scripts/uninstall_windows.bat`**

- Kills running agent process
- Removes auto-start registry key
- Removes install directory
- Optionally removes data directory (`%APPDATA%\LocalMonitorAgent\`)
- Removes shortcuts

---

## 13.2 — Health Check / Diagnostic Tool

**`scripts/health_check.py`** (runs standalone, no venv needed)

- Is agent process running? (check lock file + PID)
- SQLite DB exists? Size?
- Pending records count per table
- Last successful sync timestamp
- Config values (employee_id, device_mac — no secrets)
- Network connectivity to API base URL
- Auto-start registered?
- Agent version from DB or exe

Output: clean terminal report, optionally JSON for remote collection.

---

## 13.3 — Documentation

**`docs/DEPLOYMENT_GUIDE.md`** — For IT admin

- Prerequisites (Windows 10/11, network access to API)
- Step-by-step install
- How to pre-configure `.env`
- How to verify installation
- Troubleshooting common issues
- Uninstall procedure

**`docs/USER_GUIDE.md`** — For employees

- What this agent does (transparency)
- What it does NOT do (privacy assurance)
- First launch walkthrough
- System tray usage
- How to pause/resume
- Who to contact for issues

**`docs/PILOT_CHECKLIST.md`** — Verification checklist

- Per-machine validation steps
- Data appearing in backend?
- App tracking accurate?
- Domain tracking accurate?
- No full URLs leaking?
- Performance impact acceptable?
- Session timing correct?

---

## 13.4 — Internal Testing (Self-Test)

- Install via installer script on own machine
- Run for 48 hours continuously
- Verify across: reboot, sleep/wake, network disconnect/reconnect, VPN toggle
- Check backend data quality
- Monitor: memory usage, CPU usage, disk usage, SQLite growth
- Test: pause/resume, quit and restart, lock screen behavior

---

## 13.5 — Pilot Group Deployment (5-10 machines)

- Deploy via installer script or manual copy
- Run for 1 week
- Collect feedback:
  - Performance impact noticed?
  - Any crashes? (check crash.log)
  - System tray visible and working?
  - Auto-start working after reboot?
- Monitor backend data:
  - All pilot devices reporting?
  - Data gaps?
  - Category accuracy?

---

## 13.6 — Data Validation

- Cross-check app usage against manual observation (1 hour sample)
- Cross-check domains against browser history (voluntary)
- Verify: no full URLs, no query params, no page content
- Verify: idle detection triggers correctly
- Verify: session start/end timestamps accurate
- Verify: bytes uploaded/downloaded in reasonable range

---

## Execution Order

| Step | What                                                              | Effort           |
| ---- | ----------------------------------------------------------------- | ---------------- |
| 1    | Auto-start on boot                                                | 1-2 hours        |
| 2    | CLI arguments (`--version`, `--status`, `--reset`, `--uninstall`) | 2-3 hours        |
| 3    | Install/uninstall scripts                                         | 2-3 hours        |
| 4    | Health check script                                               | 1-2 hours        |
| 5    | Documentation (3 docs)                                            | 2-3 hours        |
| 6    | Rebuild exe with changes                                          | 30 min           |
| 7    | Self-test 48 hours                                                | 2 days (passive) |
| 8    | Pilot deployment                                                  | 1 week (passive) |

---
