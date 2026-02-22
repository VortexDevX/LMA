# Local Monitor Agent - Pilot Checklist

Use this checklist per pilot machine.

## 1. Machine Metadata

- [ ] Machine name:
- [ ] Employee name:
- [ ] Employee ID:
- [ ] OS and version:
- [ ] Installation date:
- [ ] Installed by:

## 2. Preflight

- [ ] Backend API reachable from machine
- [ ] Valid API key available
- [ ] Build artifact available (`dist/LocalMonitorAgent.exe`)
- [ ] Employee has password + TOTP ready

## 3. Installation

- [ ] Installed via `scripts/install_windows.ps1` or `scripts/install_windows.bat`
- [ ] Exe present at `%LOCALAPPDATA%\\Programs\\LocalMonitorAgent\\LocalMonitorAgent.exe`
- [ ] Config present at `%APPDATA%\\LocalMonitorAgent\\.env`
- [ ] `API_KEY` present in `.env`
- [ ] Auto-start registered
- [ ] Start Menu shortcut created (Windows deployment path)

## 4. First Launch Setup

- [ ] First-launch setup completed successfully
- [ ] Login endpoint succeeded (`/api/v1/auth/login`)
- [ ] Device registration attempted (`/api/v1/devices/`)
- [ ] Local identity written (`employee_id`, `employee_name`, `device_mac`)

## 5. Runtime Verification

- [ ] Tray icon visible
- [ ] `Pause Monitoring` and `Resume Monitoring` both work
- [ ] `View Dashboard` opens browser
- [ ] Auto-start toggle works from tray menu
- [ ] `LocalMonitorAgent.exe --status` returns expected identity and pending stats

## 6. Telemetry Verification

### 6.1 App usage

- [ ] Open at least two apps for 2-3 minutes
- [ ] App usage records appear locally (`pending_app_usage` / sent path)
- [ ] Backend receives app usage payloads

### 6.2 Domain visits

- [ ] Visit known domains (for example: github.com, youtube.com)
- [ ] Domain records appear locally with domain-only format
- [ ] No full URL/query/path captured
- [ ] Backend receives domain visit payloads

### 6.3 Session records

- [ ] Session start record created on launch
- [ ] Session update records appear over time
- [ ] Session end record created on shutdown

## 7. Resilience Checks

### 7.1 Network interruption

- [ ] Disconnect network for 2-5 minutes
- [ ] Agent keeps running
- [ ] Pending queue grows while offline
- [ ] Queue drains after reconnect

### 7.2 Reboot

- [ ] Reboot machine
- [ ] Agent auto-starts on login
- [ ] Tray icon appears
- [ ] Monitoring resumes without manual setup

### 7.3 Auth failure handling

- [ ] Simulate invalid API key (test machine only)
- [ ] Agent enters auth cooldown behavior (no aggressive request hammering)
- [ ] Restore valid key and verify recovery

### 7.4 Process recovery

- [ ] Confirm no collector crashes during normal use
- [ ] If crash is induced, watchdog recovers collector threads

## 8. Auto-Update Validation (If Update Endpoint Is Enabled)

- [ ] Update endpoint returns higher version metadata
- [ ] Agent detects update
- [ ] Binary download and checksum verification succeed
- [ ] Agent restarts into new version
- [ ] Backup file exists and rollback path is valid

## 9. Privacy Validation

Inspect DB:

```sql
SELECT payload_json FROM pending_domain_visits LIMIT 5;
SELECT payload_json FROM pending_app_usage LIMIT 5;
```

Confirm:
- [ ] Domain records contain only domain names
- [ ] No full URLs or query strings
- [ ] No screenshots/keystroke/window-title content in payloads

## 10. Performance Checks (4+ hour run)

- [ ] CPU remains within acceptable range for pilot baseline
- [ ] Memory remains stable (no obvious leak trend)
- [ ] DB growth rate is reasonable
- [ ] Log rotation behaves correctly

## 11. Health Diagnostics

- [ ] `LocalMonitorAgent.exe --status` reviewed
- [ ] `python scripts/health_check.py` reviewed
- [ ] No critical errors in `%APPDATA%\\LocalMonitorAgent\\logs\\agent.log`

## 12. Pilot Feedback

- [ ] Employee reports no blocking UX issues
- [ ] Employee confirms tray controls are understandable
- [ ] Any concerns documented and triaged

## 13. Issue Log

| ID | Issue | Severity | Owner | Status |
|----|-------|----------|-------|--------|
| 1  |       |          |       |        |
| 2  |       |          |       |        |
| 3  |       |          |       |        |

## 14. Sign-Off

- [ ] Pilot machine accepted
- [ ] Issues (if any) documented
- [ ] Ready for broader rollout on similar profile machines

Verified by:
Date:
