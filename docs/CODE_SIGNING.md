# Code Signing Guide for Local Monitoring Agent

## Overview

Code signing prevents Windows and macOS from showing security warnings or blocking your application. This guide covers both platforms.

---

## Windows Code Signing

### Option 1: Self-Signed Certificate (Development/Testing)

**⚠️ Note**: Self-signed certificates will still show warnings, but are useful for testing the signing process.

#### Step 1: Generate a Self-Signed Certificate

```powershell
# Run as Administrator
# Generate a self-signed certificate valid for 10 years
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=Local Monitor Agent" `
  -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3") `
  -FriendlyName "LocalMonitorAgentSigningCert" `
  -CertStoreLocation "Cert:\CurrentUser\My" `
  -NotAfter (Get-Date).AddYears(10)

# Export certificate with private key to PFX file
$password = Read-Host -AsSecureString -Prompt "Enter certificate password"
Export-PfxCertificate -Cert $cert -FilePath "lma_cert.pfx" -Password $password

# Export public certificate to CER file (for distribution)
Export-Certificate -Cert $cert -FilePath "lma_cert.cer"

Write-Host "Certificate created: lma_cert.pfx"
Write-Host "Thumbprint: $($cert.Thumbprint)"
```

#### Step 2: Sign the EXE

After building with PyInstaller:

```powershell
# Install SignTool (part of Windows SDK)
# Download from: https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/

# Sign the executable
$signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
$password = Read-Host -AsSecureString -Prompt "Enter certificate password"

& $signtool sign /f lma_cert.pfx /p $password `
  /t http://timestamp.digicert.com /fd SHA256 `
  /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA.git" `
  "dist\LocalMonitorAgent.exe"

# Verify signature
& $signtool verify /pa "dist\LocalMonitorAgent.exe"
```

### Option 2: Trusted Code Signing Certificate (Production)

For production deployment without warnings, purchase a code signing certificate from:

- **Sectigo**: https://sectigo.com/ssl-certificates-tls/code-signing
- **Digicert**: https://www.digicert.com/code-signing
- **GlobalSign**: https://www.globalsign.com/en/code-signing-certificate
- **Comodo**: https://www.instantssl.com/code-signing

**Cost**: ~$150-400/year

#### Sign with Commercial Certificate

```powershell
# After obtaining .PFX from provider
$signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
$password = Read-Host -AsSecureString -Prompt "Enter certificate password"

& $signtool sign /f your_cert.pfx /p $password `
  /t http://timestamp.digicert.com /fd SHA256 `
  /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA.git" `
  "dist\LocalMonitorAgent.exe"

# Verify signature
& $signtool verify /pa "dist\LocalMonitorAgent.exe"
```

### Option 3: Automatic Signing in Build Script

Add to `scripts/build_windows.bat`:

```batch
REM Sign the executable if certificate exists
if exist "lma_cert.pfx" (
    echo Signing executable...
    set "SIGNTOOL=C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
    if exist "%SIGNTOOL%" (
        REM Get password from environment variable
        set /p CERT_PASSWORD="Enter certificate password: "
        "%SIGNTOOL%" sign /f lma_cert.pfx /p !CERT_PASSWORD! ^
          /t http://timestamp.digicert.com /fd SHA256 ^
          /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA.git" ^
          "dist\LocalMonitorAgent.exe"

        if errorlevel 1 (
            echo WARNING: Signing failed. Executable may not be signed.
        ) else (
            echo Executable signed successfully.
        )
    ) else (
        echo WARNING: SignTool not found. Skipping code signing.
    )
)
```

Or in PowerShell:

```powershell
# scripts/sign_executable.ps1
param(
    [string]$ExePath,
    [string]$CertPath,
    [string]$CertPassword,
    [string]$TimestampServer = "http://timestamp.digicert.com"
)

$signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"

if (-not (Test-Path $signtool)) {
    Write-Error "SignTool not found at $signtool"
    exit 1
}

Write-Host "Signing $ExePath..."

& $signtool sign /f $CertPath /p $CertPassword `
  /t $TimestampServer /fd SHA256 `
  /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA.git" `
  $ExePath

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Executable signed successfully"
    & $signtool verify /pa $ExePath
} else {
    Write-Host "✗ Signing failed"
    exit 1
}
```

Run after build:

```powershell
.\scripts\sign_executable.ps1 -ExePath "dist\LocalMonitorAgent.exe" `
  -CertPath "lma_cert.pfx" -CertPassword "your_password"
```

---

## macOS Code Signing

### Step 1: Create Apple Developer Certificate

1. Go to [Apple Developer](https://developer.apple.com/)
2. Create/renew your Developer ID Certificate
3. Download and install the certificate in Keychain

### Step 2: Codesign the App

```bash
# Get your certificate identifier
security find-identity -v -p codesigning

# Sign the app (use your certificate name)
codesign --deep --force --verify --verbose --sign "Developer ID Application: Your Name" \
  "dist/LocalMonitorAgent.app"

# Verify signature
codesign --verify --verbose "dist/LocalMonitorAgent.app"

# Check notarization status (optional)
spctl -a -vvv "dist/LocalMonitorAgent.app"
```

### Step 3: Notarize (Optional but Recommended)

```bash
# Package for submission
ditto -c -k --sequesterRsrc "dist/LocalMonitorAgent.app" LocalMonitorAgent.zip

# Submit for notarization (requires Apple ID)
xcrun notarytool submit LocalMonitorAgent.zip --apple-id your-apple-id@example.com \
  --password your-app-specific-password --team-id YOUR_TEAM_ID

# Check status (use the request UUID from submission)
xcrun notarytool info UUID --apple-id your-apple-id@example.com \
  --password your-app-specific-password --team-id YOUR_TEAM_ID

# Staple notarization ticket
xcrun stapler staple "dist/LocalMonitorAgent.app"
```

---

## Automated Build with Signing

### Windows (PowerShell)

Create `scripts/build_and_sign_windows.ps1`:

```powershell
param(
    [switch]$NoSign,
    [string]$CertPath = "lma_cert.pfx",
    [string]$CertPassword
)

Write-Host "Building Local Monitor Agent..."
pyinstaller local-monitor-agent.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "Build failed"
    exit 1
}

if (-not $NoSign -and (Test-Path $CertPath)) {
    Write-Host "Signing executable..."

    if (-not $CertPassword) {
        $CertPassword = Read-Host -AsSecureString -Prompt "Certificate password"
        $CertPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($CertPassword)
        )
    }

    .\scripts\sign_executable.ps1 -ExePath "dist\LocalMonitorAgent.exe" `
      -CertPath $CertPath -CertPassword $CertPassword

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Signing failed, but executable is still usable"
    }
}

Write-Host "`n✓ Build complete!"
Write-Host "Executable: dist\LocalMonitorAgent.exe"
```

Run:

```powershell
.\scripts\build_and_sign_windows.ps1 -CertPassword "your_password"
```

### macOS (Bash)

Create `scripts/build_and_sign_macos.sh`:

```bash
#!/bin/bash

CERT_NAME="${1:-Developer ID Application}"
NOTARIZE="${2:-false}"

echo "Building Local Monitor Agent..."
pyinstaller local-monitor-agent.spec --noconfirm

if [ $? -ne 0 ]; then
    echo "Build failed"
    exit 1
fi

echo "Signing application..."
codesign --deep --force --verify --verbose --sign "$CERT_NAME" \
  "dist/LocalMonitorAgent.app"

if [ $? -ne 0 ]; then
    echo "Signing failed"
    exit 1
fi

if [ "$NOTARIZE" = "true" ]; then
    echo "Preparing for notarization..."
    ditto -c -k --sequesterRsrc "dist/LocalMonitorAgent.app" LocalMonitorAgent.zip

    echo "Submitting to Apple for notarization..."
    xcrun notarytool submit LocalMonitorAgent.zip --wait \
      --apple-id "$APPLE_ID" \
      --password "$APPLE_PASSWORD" \
      --team-id "$APPLE_TEAM_ID"

    if [ $? -eq 0 ]; then
        echo "Stapling notarization ticket..."
        xcrun stapler staple "dist/LocalMonitorAgent.app"
    fi
fi

echo "✓ Build complete!"
ls -lh "dist/LocalMonitorAgent.app"
```

Run:

```bash
chmod +x scripts/build_and_sign_macos.sh
./scripts/build_and_sign_macos.sh "Your Certificate Name" true
```

---

## Verification

### Windows

```powershell
# Check if signed
Get-AuthenticodeSignature "dist\LocalMonitorAgent.exe"

# Result should show:
# Status       : Valid
# SignerCertificate : [thumbprint]
# TimestamperCertificate : [thumbprint]
```

### macOS

```bash
# Check signature
codesign --verify --verbose "dist/LocalMonitorAgent.app"

# Check notarization status
spctl -a -vvv "dist/LocalMonitorAgent.app"

# Should show "accepted" if notarized
```

---

## Troubleshooting

### Windows

| Issue                          | Solution                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------- |
| "SignTool not found"           | Install [Windows SDK](https://developer.microsoft.com/windows/downloads/windows-sdk/) |
| "Certificate not found"        | Ensure .PFX file exists and path is correct                                           |
| "The password is incorrect"    | Double-check certificate password                                                     |
| "Timestamp server unavailable" | Try different timestamp server or skip timestamp                                      |

### macOS

| Issue                       | Solution                                                  |
| --------------------------- | --------------------------------------------------------- |
| "Certificate not found"     | Import certificate in Keychain or create new Developer ID |
| "App blocked on other Macs" | Notarize the app through Apple                            |
| "Cannot verify app"         | Ensure certificate is valid and app is properly signed    |

---

## Linux Security Setup

### Overview

Linux distributions use different security mechanisms:

- **Mandatory Access Control (MAC)**: AppArmor (Ubuntu/Debian), SELinux (RHEL/Fedora)
- **GPG Signatures**: Digital signatures for distribution verification
- **Desktop Entry**: System integration and auto-start
- **File Permissions**: Secure file access control

### Automated Setup Script

The easiest way to secure your Linux app:

```bash
# Build the executable
./scripts/build_linux.sh

# Run security setup (creates apparmor profile, SELinux policy, desktop entry, GPG signature)
./scripts/sign_linux.sh
```

This creates:

- AppArmor profile for Ubuntu/Debian
- SELinux policy template for RHEL/Fedora
- Desktop entry file for system integration
- Optional GPG signature for distribution

### Manual Setup

#### 1. AppArmor Profile (Ubuntu/Debian)

```bash
# Create AppArmor profile
sudo tee /etc/apparmor.d/usr.local.bin.LocalMonitorAgent > /dev/null << 'EOF'
#include <tunables/global>

/usr/local/bin/LocalMonitorAgent {
  #include <abstractions/base>
  #include <abstractions/nameservice>

  # Allow execution
  /usr/local/bin/LocalMonitorAgent mr,

  # Data directory
  owner @{HOME}/.local/share/LocalMonitorAgent/ rw,
  owner @{HOME}/.local/share/LocalMonitorAgent/** rwk,

  # Logs
  owner @{HOME}/.local/share/LocalMonitorAgent/logs/ rwk,
  owner @{HOME}/.local/share/LocalMonitorAgent/logs/** rwk,

  # Database
  owner @{HOME}/.local/share/LocalMonitorAgent/agent.db rwk,

  # System information (read-only)
  /proc/stat r,
  /proc/meminfo r,
  /proc/uptime r,
  /sys/class/net/ r,
  /sys/class/net/** r,

  # Network
  network inet stream,
  network inet dgram,
}
EOF

# Load the profile
sudo apparmor_parser -r /etc/apparmor.d/usr.local.bin.LocalMonitorAgent

# Verify
sudo aa-status | grep LocalMonitorAgent
```

#### 2. SELinux Policy (RHEL/Fedora/CentOS)

```bash
# Create policy module
cat > localmonitoragent.te << 'EOF'
policy_module(localmonitoragent, 1.0.0)

type localmonitoragent_t;
type localmonitoragent_exec_t;

domain_type(localmonitoragent_t)
domain_entry_file(localmonitoragent_t, localmonitoragent_exec_t)

allow localmonitoragent_t self:process signal_perms;
allow localmonitoragent_t self:fifo_file rw_file_perms;
allow localmonitoragent_t self:unix_stream_socket create_stream_socket_perms;

kernel_read_system_proc(localmonitoragent_t)

# Network
corenet_all_recvfrom_netlabel(localmonitoragent_t)
corenet_tcp_sendrecv_generic_if(localmonitoragent_t)
corenet_tcp_sendrecv_generic_node(localmonitoragent_t)
corenet_tcp_bind_generic_node(localmonitoragent_t)
corenet_tcp_connect_all_ports(localmonitoragent_t)

# Home directory
userdom_manage_user_home_content_files(localmonitoragent_t)
userdom_manage_user_home_content_dirs(localmonitoragent_t)

logging_send_syslog_msg(localmonitoragent_t)
EOF

# Compile and install
sudo checkmodule -M -m -o localmonitoragent.mod localmonitoragent.te
sudo semodule_package -o localmonitoragent.pp -m localmonitoragent.mod
sudo semodule -i localmonitoragent.pp

# Verify
ls -Z /usr/local/bin/LocalMonitorAgent
```

#### 3. Desktop Entry (Auto-start)

```bash
# Create desktop entry
cat > ~/.config/autostart/LocalMonitorAgent.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=Local Monitor Agent
Comment=Employee productivity monitoring agent
Exec=/usr/local/bin/LocalMonitorAgent
Icon=LocalMonitorAgent
Terminal=false
Categories=Utility;System;
NoDisplay=true
X-GNOME-Autostart-enabled=true
X-KDE-autostart-condition=true
StartupNotify=false
EOF

# Make it executable
chmod 755 ~/.config/autostart/LocalMonitorAgent.desktop
```

#### 4. GPG Signature (Distribution)

Sign the binary with your GPG key:

```bash
# List keys
gpg --list-secret-keys --keyid-format=long

# Sign
gpg --sign --armor --detach-sign --default-key YOUR_KEY_ID dist/LocalMonitorAgent

# Verify
gpg --verify dist/LocalMonitorAgent.asc dist/LocalMonitorAgent
```

Users can then verify authenticity:

```bash
# Import your public key
gpg --import your_public_key.gpg

# Verify the signature
gpg --verify LocalMonitorAgent.asc LocalMonitorAgent
```

### Installation

After security setup:

```bash
# Install to system
sudo cp dist/LocalMonitorAgent /usr/local/bin/
sudo chmod 755 /usr/local/bin/LocalMonitorAgent

# Create data directory
mkdir -p ~/.local/share/LocalMonitorAgent

# Enable auto-start
mkdir -p ~/.config/autostart
cp LocalMonitorAgent.desktop ~/.config/autostart/

# Verify
./LocalMonitorAgent --status

# View logs
tail -f ~/.local/share/LocalMonitorAgent/logs/agent.log
```

### Verification

**AppArmor**:

```bash
sudo aa-status | grep LocalMonitorAgent
```

**SELinux**:

```bash
ls -Z /usr/local/bin/LocalMonitorAgent
getsebool -a | grep localmonitoragent
```

**GPG Signature**:

```bash
gpg --verify LocalMonitorAgent.asc LocalMonitorAgent
```

---

## Certificate Management

### View installed certificates (Windows)

```powershell
Get-ChildItem -Path Cert:\CurrentUser\My | Where-Object {$_.Extensions.KeyUsages -Like "*DigitalSignature*"}
```

### Renew/Replace certificates

```bash
# macOS - Check expiration
security find-certificate -a -c "Developer ID Application" | grep "End Date"

# Windows - Check in Certificates Manager (certmgr.msc)
# Look for expiration date under Personal > Certificates
```

---

## References

- [Microsoft Code Signing Documentation](https://docs.microsoft.com/en-us/dotnet/framework/tools/signtool-exe)
- [Apple Code Signing Guide](https://developer.apple.com/help/xcode/codesigning-guide)
- [AppArmor Documentation](https://gitlab.com/apparmor/apparmor/-/wikis/home)
- [SELinux Project](https://github.com/SELinuxProject)
- [GNU Privacy Guard (GPG)](https://gnupg.org/)
- [PyInstaller Code Signing](https://pyinstaller.org/en/v6.1.0/usage.html#codesigning)
- [Linux Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry-spec/)
