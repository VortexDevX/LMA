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
  and GitHub artifact attestations. Windows and Linux artifacts are unsigned;
  the macOS app is ad-hoc signed for build validation only.
- `v*` tag: same checks, then mandatory platform signing. The release fails if
  trusted signing credentials are absent or invalid. Successful tagged builds
  publish versioned GitHub Release assets.

Never add `.env`, `API_KEY`, or an `ENV_FILE` secret to this workflow.

## Required GitHub repository secrets

### Windows

- `CODESIGN_PFX_BASE64`: base64 content of a public-CA-issued Authenticode
  code-signing PFX/P12 certificate.
- `CODESIGN_PASSWORD`: PFX/P12 password.

Create the base64 value locally without committing the certificate:

```powershell
[Convert]::ToBase64String(
  [IO.File]::ReadAllBytes("trusted-code-signing.pfx")
) | Set-Clipboard
```

The old self-signed `CN=Local Monitor Agent` certificate proves that signing
works, but it is not publicly trusted. It is suitable only for devices where its
public certificate is deployed to the trusted publisher/root stores by an
administrator or organization policy. Replace it before making a tagged public
release.

Some certificate vendors provide non-exportable hardware or cloud keys instead
of a PFX. In that case, replace the PFX step with that provider's official GitHub
Action or signing client. Microsoft Artifact Signing is one such alternative.

### Linux

- `GPG_PRIVATE_KEY`: ASCII-armored private signing key.
- `GPG_PASSPHRASE`: its passphrase (may be empty only for an intentionally
  unprotected CI-only key).

Publish the matching public key through a trusted project channel. Linux does not
have a single universal executable-publisher trust system equivalent to Windows
Authenticode; users verify the detached `.asc` signature and checksum.

### macOS

- `MACOS_CERTIFICATE_P12_BASE64`: base64 Developer ID Application certificate.
- `MACOS_CERTIFICATE_PASSWORD`: P12 password.
- `MACOS_SIGNING_IDENTITY`: for example,
  `Developer ID Application: Company Name (TEAMID)`.
- `APPLE_ID`: Apple Developer account email.
- `APPLE_APP_PASSWORD`: app-specific password.
- `APPLE_TEAM_ID`: Apple Developer Team ID.

Public distribution requires an Apple Developer ID certificate, hardened-runtime
signing, timestamping, notarization, and stapling. The workflow performs all five
for tagged releases.

## Make a release

1. Update `project.version` in `pyproject.toml`.
2. Commit and push the tested source.
3. Create a matching tag, such as `v1.0.3`.
4. Push the tag.

```bash
git tag v1.0.3
git push origin v1.0.3
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
gpg --verify LocalMonitorAgent-linux.asc LocalMonitorAgent-linux
```

macOS:

```bash
spctl -a -vv --type execute /Applications/LocalMonitorAgent.app
xcrun stapler validate LocalMonitorAgent-macos.dmg
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
