# GitHub Release Signing

This is the authoritative release procedure for Local Monitor Agent (LMA).

## What GitHub Actions needs

GitHub Actions does **not** need the agent runtime `.env`, `API_KEY`, or backend
credentials. The build must remain secret-free. An installed agent receives its
runtime configuration separately, normally at:

- Windows: `%APPDATA%\LocalMonitorAgent\.env`
- Linux/macOS: the platform application-data directory selected by the installer

The public `UPDATE_PUBLIC_KEY` in `.env.template` and `release-public.key` is safe
to distribute. The matching `release-private.key` signs update manifests and must
remain offline and out of Git/GitHub Actions.

## Workflow behavior

`.github/workflows/build.yml` has two modes:

- Push or manual run: tests, Ruff, Windows/Linux/macOS builds, SHA-256 checksums,
  GitHub artifact attestations, and ad-hoc signing for macOS.
- `v*` tag: same checks plus mandatory Windows Authenticode signing. The current
  temporary policy accepts either a publicly trusted certificate or a valid
  self-signed code-signing certificate. Linux remains checksum/attestation
  verified. macOS remains ad-hoc self-signed by project choice. Successful
  builds publish versioned GitHub Release assets.

Never add `.env`, `API_KEY`, or an `ENV_FILE` secret to this workflow.

## Required GitHub repository secrets

### Windows

- `CODESIGN_PFX_BASE64`: base64 content of an Authenticode code-signing PFX/P12
  certificate. A self-signed code-signing certificate is temporarily accepted.
- `CODESIGN_PASSWORD`: PFX/P12 password.

Create the base64 value locally without committing the certificate:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("trusted-code-signing.pfx")
) | Set-Clipboard
```

The self-signed `CN=Local Monitor Agent` certificate proves artifact integrity,
but it is not publicly trusted. Windows will still show an unknown-publisher
warning unless its public certificate is deployed to the trusted publisher/root
stores by an administrator or organization policy.

The workflow currently sets `ALLOW_SELF_SIGNED_WINDOWS: "true"`. The verifier
accepts this only when the file is timestamped, the embedded certificate is
self-issued, currently valid, has the Code Signing EKU, and the Authenticode
signature becomes `Valid` after temporarily trusting that exact certificate in
the ephemeral CI user's root store. The certificate is removed immediately.
This does not accept unsigned files, hash mismatches, expired certificates, or
arbitrary untrusted certificate chains.

Change the workflow value to `"false"` after obtaining a publicly trusted
certificate. Replace the self-signed certificate before distributing to normal
public users if you want Windows SmartScreen/publisher trust without managed
certificate installation.

For a manual trusted-PFX build, run `scripts\sign_windows.bat`. Its PowerShell
implementation prompts without echoing the password, timestamps the file, and
fails closed for self-signed or untrusted production certificates.

Some certificate vendors provide non-exportable hardware or cloud keys instead
of a PFX. In that case, replace the PFX step with that provider's official GitHub
Action or signing client. Microsoft Artifact Signing is one such alternative.

### Linux

No repository secret is required. Releases include SHA-256 checksums and GitHub
artifact attestations. Linux does not have one universal publisher-trust system
equivalent to Windows Authenticode.

### macOS

No repository secret is required. Workflow performs ad-hoc signing (`codesign
--sign -`) as requested. This validates bundle integrity but does not create an
Apple-trusted or notarized application. Users may need to approve first launch
through macOS Privacy & Security or use an administrator deployment policy.

## Make a release

1. Update `project.version` in `pyproject.toml`.
2. Commit and push the tested source.
3. Create a matching tag, such as `v1.1.1`.
4. Push the tag.

```bash
git tag v1.1.1
git push origin v1.1.1
```

Do not delete and recreate a published release to replace files. Publish a new
version instead.

## Verify downloaded artifacts

Windows:

```powershell
Get-AuthenticodeSignature .\LocalMonitorAgent.exe | Format-List Status,StatusMessage,SignerCertificate
```

Linux:

```bash
sha256sum -c LocalMonitorAgent-linux.sha256
```

macOS:

```bash
codesign --verify --deep --strict --verbose=2 /Applications/LocalMonitorAgent.app
```

GitHub artifact attestation (all platforms):

```bash
gh attestation verify PATH_TO_ARTIFACT --repo VortexDevX/LMA
```

## Update-system limitation

OS code signing and the Ed25519 update-manifest signature solve different
problems; both are required. Current update manifest has one `download_url` and
one checksum. It cannot safely select different Windows, Linux, and macOS assets.
Do not enable one cross-platform auto-update manifest until the manifest and
client select an asset by operating system and architecture.
