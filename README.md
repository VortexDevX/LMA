<div align="center">

# Local Monitoring Agent

### Cross-platform desktop telemetry agent for productivity analytics

<p>
  <img src="https://img.shields.io/badge/Python-111827?style=for-the-badge" alt="Python" />
  <img src="https://img.shields.io/badge/Desktop%20Agent-111827?style=for-the-badge" alt="Desktop Agent" />
  <img src="https://img.shields.io/badge/SQLite-111827?style=for-the-badge" alt="SQLite" />
  <img src="https://img.shields.io/badge/Tray%20UI-111827?style=for-the-badge" alt="Tray UI" />
  <img src="https://img.shields.io/badge/Offline%20Buffer-111827?style=for-the-badge" alt="Offline Buffer" />
  <img src="https://img.shields.io/badge/Privacy%20TODO-111827?style=for-the-badge" alt="Privacy TODO" />
</p>
<p>
  <a href="https://github.com/VortexDevX/LMA"><img src="https://img.shields.io/badge/GitHub%20Repo-111827?style=for-the-badge" alt="GitHub Repo" /></a>
</p>

</div>

---

## Overview

Local Monitoring Agent collects metadata-level activity signals, buffers locally, and syncs with a backend when available. Because this is a sensitive category, the README pairs technical setup with explicit privacy and security follow-up files.

<table>
<tr>
<td width="25%"><strong>Status</strong></td>
<td>Utility repo with privacy/security documentation placeholders added</td>
</tr>
<tr>
<td><strong>Stack</strong></td>
<td>Python, psutil, requests, pystray, Pillow, SQLite-style local buffering, pytest, Ruff, Black</td>
</tr>
<tr>
<td><strong>Built for</strong></td>
<td>Teams piloting metadata-level workplace telemetry with clear notice and controls</td>
</tr>
</table>

## Highlights

- Desktop agent structure with collectors, storage, sync, setup, and tray UI
- Offline-first buffering and backend sync orientation
- Windows/macOS/Linux packaging scripts and signing notes
- `PRIVACY.md` and `SECURITY.md` TODO placeholders added
- Monitoring behavior intentionally not altered

## Feature Map

<table>
<tr>
<td width="50%" valign="top">

### Collectors

Activity, app/window, network, and session-oriented modules.

</td>
<td width="50%" valign="top">

### Local Runtime

Local data, lock files, logs, and sync behavior handled by the app.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Tray UI

System-tray interface and setup wizard patterns for desktop use.

</td>
<td width="50%" valign="top">

### Compliance Work

Privacy and security docs are placeholders until real policy is written.

</td>
</tr>
</table>

## Quick Start

Build artifacts never embed `.env` or API keys. Installer writes runtime configuration to the platform data directory (on Windows, `%APPDATA%\\LocalMonitorAgent\\.env`). Keep `API_KEY` out of source control and release artifacts.

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m src.main --help
```

## Project Structure

- src/ - agent source modules
- tests/ - pytest suite
- scripts/ - build, install, signing, and health-check helpers
- docs/ - user, deployment, pilot, and signing documentation

## Notes

- Do not publish without completing privacy and security documentation.
- Monitoring/collector behavior was not changed.
- Local runtime files, certificates, venvs, and build outputs should stay ignored.
- GitHub builds and trusted release requirements: [docs/GITHUB_RELEASE_SIGNING.md](docs/GITHUB_RELEASE_SIGNING.md)

---

<div align="center">

<strong>Clean docs. Clear setup. No fake screenshots.</strong>

</div>
