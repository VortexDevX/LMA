# Local Monitor Agent

Cross-platform desktop telemetry agent for Employee Management. It collects metadata-level application, session, and domain activity, buffers offline in SQLite, and sends records to Employee API with a unique revocable device credential.

Current source version: `1.1.1`.

## Privacy boundary

The agent records app names, active/idle duration, switches, domain names, estimated domain traffic/duration, and session totals. It does not intentionally collect keystrokes, screenshots, clipboard, full URLs/paths/queries, page or form content, credentials, webcam, or microphone data. Read [PRIVACY.md](PRIVACY.md) before deployment.

## Authentication

Builds never embed `.env`, employee credentials, a shared API key, or the update private key. First launch authenticates the employee and calls `/api/v1/devices/enroll`; the returned per-device credential is stored with Windows DPAPI, macOS Keychain, or a user-only Linux file.

## Development

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.template .env
python -m src.main --help
python -m src.main --setup
```

## Verification

```powershell
python -m pytest -q
python -m ruff check .
python -m compileall -q src scripts
```

Current Windows baseline: 450 passed and one expected non-Windows permission-test skip.

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Technical overview](docs/LOCAL_AGENT_OVERVIEW.md)
- [Deployment guide](docs/DEPLOYMENT_GUIDE.md)
- [Pilot checklist](docs/PILOT_CHECKLIST.md)
- [GitHub build and signing](docs/GITHUB_RELEASE_SIGNING.md)
- [Security policy](SECURITY.md)
- [Intermediate LMA guide](../docs/LOCAL_MONITOR_AGENT.md)
- [Repository-wide configuration and acceptance](../docs/README.md)

The current updater manifest supports only one asset URL/checksum. Keep cross-platform auto-update disabled until manifest selection includes operating system and architecture and a real update/rollback pilot passes.
