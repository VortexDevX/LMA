# Local Monitoring Agent Privacy Notice

This document describes what the current agent code collects. The deploying organization must provide employees with its own notice, lawful basis, retention period, and contact details before a pilot or production rollout.

## Data collected

The agent records:

- employee ID/code and registered device identity (hostname, MAC address, OS, and local IP);
- foreground application/process name, active seconds, idle seconds, and switch count;
- destination domain, associated application, approximate duration, bytes uploaded/downloaded, and connection count;
- work-session timestamps and aggregate active/idle time;
- operational logs, retry state, agent version, and synchronization status.

The network collector is domain-level. It does not intentionally collect full URLs, page content, query strings, message content, keystrokes, clipboard contents, screenshots, camera/microphone data, or document contents. Application names and domains can still reveal sensitive activity and must be treated as personal monitoring data.

## Local storage and transfer

Pending telemetry and device identity are stored in the platform data directory in SQLite until synchronization. Successfully sent records are removed from the local pending tables after 24 hours; permanently failed records are removed after 7 days. Logs rotate, but the deployment owner must confirm host-level retention.

Telemetry is sent to `API_BASE_URL`. Production deployments must use HTTPS and restrict file/database permissions to the agent user. Normal installations use a unique revocable device credential stored outside SQLite with Windows DPAPI, macOS Keychain, or user-only Linux file permissions; they do not receive the central service API key. Current builds remove legacy credential copies from SQLite.

Server-side retention is not defined by the agent. Configure and document it in the employee API/database operations policy before deployment.

## Access, export, correction, and deletion

The deploying organization is the data controller/owner for operational purposes. It must define who can view telemetry, audit administrative access, and provide the applicable employee request process.

Local removal:

```text
LocalMonitorAgent --reset       clear local identity and require setup again
LocalMonitorAgent --uninstall   remove auto-start and optionally delete the local data directory
```

These commands do not delete records already synchronized to the server. Server-side export/deletion must be performed through an authorized backend process and must respect legal or business retention requirements.

## Deployment checklist

- Give employees a clear notice before installation and record required consent/acknowledgement.
- Test with non-sensitive pilot accounts and least-privilege admin roles.
- Set a documented server retention period and deletion job.
- Restrict API, database, log, and backup access; record privileged actions.
- Provide an internal privacy/security contact and incident process.
- Re-review this notice whenever collectors or payload schemas change.
