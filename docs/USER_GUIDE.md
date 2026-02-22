# Local Monitor Agent - User Guide

Audience: employees using a managed device with Local Monitor Agent installed

## 1. What This App Does

The Local Monitor Agent runs in the background and collects productivity telemetry for:

- Application usage (which app is active, active vs idle time, app switches)
- Network domains visited (domain only, not full URL)

The tray icon shows that monitoring is active and provides controls.

## 2. What Is Collected

Collected data includes:

- App name (for example: VSCode, Chrome, Slack)
- Active duration and idle duration per app
- Domain name (for example: github.com)
- Per-domain bytes uploaded/downloaded (estimated)
- Per-domain duration
- Session-level totals

## 3. What Is Not Collected

Not collected:

- Keystrokes
- Screenshots
- Window titles/document names
- Full URLs, page paths, search queries
- Page content, form data, cookies, credentials
- Clipboard content
- Webcam or microphone data

Domain-level tracking is not equivalent to full browsing history capture.

## 4. First-Time Setup

On first launch, the app asks for:

1. Employee ID (numeric)
2. Password
3. TOTP code

Depending on launch mode:

- GUI setup wizard is shown in normal desktop launch
- CLI setup is used if launched in an interactive terminal

After successful login, device registration is completed and future launches do not ask again.

## 5. Tray Icon and Menu

Tray menu options include:

- Status line
- Your name and employee ID
- Call it a day / Resume Work
- View Dashboard
- Auto-start toggle
- Quit Agent

Icon state:

- Green: running
- Yellow: paused
- Gray/red: stopped/error states

## 6. Pause and Resume

To pause monitoring and send collected data:

1. Right-click tray icon
2. Click `Call it a day` - This will immediately flush all collected data to the backend and pause monitoring

To resume:

1. Right-click tray icon
2. Click `Resume Work`

## 7. Auto-Start

The app is typically configured to start when you sign in.
You can toggle this from the tray menu using the auto-start option.

## 8. Offline Behavior

If network is unavailable:

- Data is buffered locally in SQLite queue
- Sync resumes automatically when connectivity returns

## 9. Updates

The agent can update itself when a newer approved version is available from the backend.
During an update it may briefly restart.

## 10. Privacy Summary

The app is designed for metadata-level productivity analytics.
It does not capture content or credentials.

## 11. If You Need Help

If you think the agent is not working:

1. Check tray icon status
2. Restart the app
3. Contact IT and share:
   - approximate time of issue
   - any visible error text

IT can run diagnostics with:

- `LocalMonitorAgent.exe --status`
- `python scripts/health_check.py`

## 12. Frequently Asked Questions

Q: Does this slow down my computer?
A: Normal target usage is low CPU and low memory.

Q: Does it track everything I do in browser pages?
A: No. It records domain-level metadata, not full URL/content.

Q: Can I stop it?
A: You can pause or quit from tray menu. Organizational policy on this is managed by your admin.

Q: What if I am offline?
A: Data queues locally and syncs when online again.
