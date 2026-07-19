# Local Monitor Agent - Deployment Guide

Audience: IT administrators and deployment engineers

## 1. Deployment Snapshot

Current implementation includes:

- Core telemetry pipeline (apps + domain-level network)
- Tray app and CLI controls
- GUI first-launch wizard fallback
- Cross-platform auto-start registration
- Hardening and retry controls
- Auto-update and rollback

Validation in current workspace:

- 450 tests passed, 1 expected platform skip on Windows

## 2. Prerequisites

Required:

- OS: Windows 10/11 (primary), macOS, or Linux
- Network access to backend API host
- Agent executable build artifact (`dist/LocalMonitorAgent.exe` on Windows)
- Employee credentials for first-time setup:
  - employee code
  - password
  - TOTP code

Backend endpoints expected:

- `POST /api/v1/auth/login`
- `POST /api/v1/devices/enroll`
- `POST /api/v1/telemetry/sessions`
- `POST /api/v1/telemetry/app-usage`
- `POST /api/v1/telemetry/domain-visits`
- `GET /api/v1/agent/latest-version` (for auto-update)

## 3. Windows Install (Recommended)

### 3.1 PowerShell installer

```powershell
cd <project-root>
.\scripts\install_windows.ps1
```

Optional silent mode:

```powershell
.\scripts\install_windows.ps1 -Silent
```

What it does:

- Copies exe to `%LOCALAPPDATA%\\Programs\\LocalMonitorAgent`
- Creates `%APPDATA%\\LocalMonitorAgent\\.env` (UTF-8 no BOM)
- Registers auto-start (HKCU Run)
- Creates Start Menu shortcut

### 3.2 Batch installer

```bat
cd <project-root>
scripts\install_windows.bat
```

## 4. Manual Install (Windows)

1. Copy binary:

- `%LOCALAPPDATA%\\Programs\\LocalMonitorAgent\\LocalMonitorAgent.exe`

2. Create config file:

- `%APPDATA%\\LocalMonitorAgent\\.env`

```dotenv
API_BASE_URL=https://emp-manan.mvlab.cloud
UPDATE_PUBLIC_KEY=MtABa8HiQ+WowR87lbpTs32yZa5OzvP5BgsZlaEBnyw=
LOG_LEVEL=INFO
```

3. Register auto-start:

```bat
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "LocalMonitorAgent" /t REG_SZ /d "\"%LOCALAPPDATA%\Programs\LocalMonitorAgent\LocalMonitorAgent.exe\"" /f
```

## 5. First Launch and Identity Setup

Normal launch:

```bat
"%LOCALAPPDATA%\Programs\LocalMonitorAgent\LocalMonitorAgent.exe"
```

Setup behavior:

- If interactive terminal exists: CLI setup flow is used
- If no terminal and tkinter exists: GUI setup wizard is used

Forced setup mode:

```bat
"%LOCALAPPDATA%\Programs\LocalMonitorAgent\LocalMonitorAgent.exe" --setup
```

Setup API sequence:

1. `POST /api/v1/auth/login`
2. `POST /api/v1/devices/enroll` with temporary login bearer token
3. Unique device credential stored with Windows DPAPI, macOS Keychain, or a
   user-only Linux credential file
4. Local identity config write (`employee_id`, `device_mac`, `employee_name`, etc.)

## 6. Post-Install Verification

### 6.1 CLI status

```bat
"%LOCALAPPDATA%\Programs\LocalMonitorAgent\LocalMonitorAgent.exe" --status
```

Check:

- Process state
- Employee/device identity
- Pending counts
- Last sync timestamp
- Device token configured

### 6.2 Health check script

```powershell
python scripts\health_check.py
python scripts\health_check.py --json
```

### 6.3 Runtime checks

- Tray icon visible
- App can pause/resume monitoring
- Dashboard menu opens browser
- Auto-start key exists
- Telemetry appears in backend

## 7. Important Runtime Paths

Windows:

- Exe: `%LOCALAPPDATA%\\Programs\\LocalMonitorAgent\\LocalMonitorAgent.exe`
- Data: `%APPDATA%\\LocalMonitorAgent`
- Config: `%APPDATA%\\LocalMonitorAgent\\.env`
- DB: `%APPDATA%\\LocalMonitorAgent\\agent.db`
- Logs: `%APPDATA%\\LocalMonitorAgent\\logs\\agent.log`
- Crash log: `%APPDATA%\\LocalMonitorAgent\\crash.log`

## 8. CLI Commands

- `LocalMonitorAgent.exe --version`
- `LocalMonitorAgent.exe --status`
- `LocalMonitorAgent.exe --reset`
- `LocalMonitorAgent.exe --uninstall`
- `LocalMonitorAgent.exe --setup`

## 9. Auto-Update Behavior

Update flow:

1. Agent checks `GET /api/v1/agent/latest-version`
2. If newer version exists, downloads binary
3. Verifies SHA-256 checksum
4. Backs up current exe (`.exe.backup`)
5. Applies update via helper script and restarts

Rollback behavior:

- If repeated startup crashes reach threshold, backup rollback is attempted on next startup.

## 10. Hardening Notes

Implemented:

- Unique revocable device token; no shared API key in executable or installer
- Windows DPAPI and macOS Keychain credential protection
- BOM-safe `.env` parsing
- Stale `sending` record reset at startup
- Sender auth cooldown on 401/403 to avoid request hammering

## 11. Troubleshooting

### 11.1 Console still visible when launched from terminal

Expected behavior: when exe is launched from an existing terminal, that terminal owns the console. Hidden console behavior applies to double-click/background launch.

### 11.2 Repeated auth errors (401/403)

Run `LocalMonitorAgent.exe --setup` to re-enroll the device. Also check backend
reachability and whether an administrator blocked the device.

Agent now applies auth cooldown after 401/403.

### 11.3 Pending records not draining

Check:

- `--status` pending count and last sync time
- `agent.log` for 4xx/5xx/timeout patterns
- Backend health for telemetry endpoints

### 11.4 Setup not completing

Check:

- Employee credentials and current TOTP
- Backend reachability
- Device enrollment endpoint response

### 11.5 Domain visits missing for browser traffic

Improved support exists (TCP + UDP/QUIC + DNS refresh), but attribution still depends on DNS visibility and remote endpoint mapping.

## 12. Uninstall

CLI:

```bat
LocalMonitorAgent.exe --uninstall
```

Script:

```bat
scripts\uninstall_windows.bat
```

Manual cleanup:

- Stop process
- Remove HKCU Run entry
- Remove install dir
- Optionally remove `%APPDATA%\\LocalMonitorAgent`

## 13. Rollout Recommendation

For pilot to production:

1. Run pilot with `docs/PILOT_CHECKLIST.md`
2. Track pending queue and sync success
3. Confirm update endpoint readiness before enabling broad rollout
4. Keep signed versioned builds and checksum manifest per release
