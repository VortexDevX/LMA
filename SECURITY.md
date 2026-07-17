# Local Monitoring Agent Security

## Supported releases

Only the newest deployed agent release should receive security fixes. The current source version is `1.0.2`; update this statement as part of every release. Older builds should be upgraded or removed.

## Reporting a vulnerability

This repository does not define a public security mailbox. Before production, the deployment owner must add a monitored private reporting address and response SLA here. Do not report a vulnerability through a public issue or include real API keys, employee data, database dumps, or private signing keys in a report.

Until that contact is configured, treat production release as blocked for external users.

## Credential and local-data handling

- The agent service key is read from `API_KEY` in the protected environment/config file. Restrict that file to the agent service account and rotate the key if exposed.
- The employee password and TOTP code are used only for setup/login and must never be logged or persisted.
- Current builds remove legacy `api_key_enc` and `access_token` values from SQLite. The old XOR helper was obfuscation, not encryption, and must not be described as secure storage.
- SQLite contains monitoring data. Apply operating-system ACLs, use full-disk encryption where appropriate, and do not include the database in support bundles.
- Production API traffic must use HTTPS with normal certificate validation. Never use `verify=False`.

## Release and update security

1. Generate the Ed25519 release key on a trusted operator machine with `scripts/sign_update_manifest.py generate-keys`.
2. Store the private key offline or in a controlled signing service. Never install it on an employee device or API host.
3. Build/code-sign the platform binary, calculate SHA-256, and create the manifest.
4. Sign the manifest and publish it through the authenticated employee API endpoint.
5. Deploy only the base64 public key as `UPDATE_PUBLIC_KEY`.
6. Test that manifest tampering, the wrong public key, and a wrong binary checksum all fail closed.

Platform code signing and the release-manifest signature solve different problems; production packages should use both.

## Backend expectations

- `LOCAL_AGENT_API_KEY` on employee-api must match the agent `API_KEY` and must be unique to this service role.
- Telemetry endpoints must enforce the `local_agent` role and employee/device ownership rules.
- Authentication endpoints need shared rate limiting in multi-worker/high-availability deployments.
- Administrative mutations and sensitive reads should create centralized audit records.
- Secrets, logs, backups, CORS origins, reverse proxy headers, TLS, and PostgreSQL permissions must be reviewed on the target deployment.

## Security verification

Run the unit suite, changed-file lint gate, dependency audit, signed-manifest tampering tests, offline buffer/retry tests, and platform package-signature verification before release. See the root `TESTING_GUIDE.md` for executable commands.
