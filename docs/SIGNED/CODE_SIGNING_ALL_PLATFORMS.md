# Code Signing Quick Start - All Platforms

## 🪟 Windows

### Fastest Way (5 minutes)

```powershell
# Step 1: Create certificate (PowerShell as Administrator)
cd v:\Projects\EmployeeManagement\local-monitor-agent
.\scripts\create_certificate.ps1

# Step 2: Build
.\scripts\build_windows.bat

# Step 3: Sign
.\scripts\sign_windows.bat
```

**Result**: Signed EXE in `dist\LocalMonitorAgent.exe`

### Verify

```powershell
Get-AuthenticodeSignature "dist\LocalMonitorAgent.exe"
# Should show: Status : Valid
```

---

## 🍎 macOS

### Fastest Way (10 minutes)

```bash
# Step 1: Build
./scripts/build_macos.sh

# Step 2: Sign and Notarize
./scripts/sign_macos.sh
```

**What it does**:
- ✅ Code signs with Developer ID certificate
- ✅ Notarizes with Apple (removes Gatekeeper warnings)
- ✅ Staples notarization ticket

### Verify

```bash
codesign --verify --verbose "dist/LocalMonitorAgent.app"
spctl -a -vvv "dist/LocalMonitorAgent.app"
```

### Requirements

1. Apple Developer Account
2. Developer ID Certificate (created in Keychain)
3. App-specific password (from your Apple ID)

### Get App-Specific Password

1. Sign in to [appleid.apple.com](https://appleid.apple.com)
2. Security → App-specific passwords
3. Generate password for "Notarization"
4. Use when prompted during `sign_macos.sh`

---

## 🐧 Linux

### Fastest Way (5 minutes)

```bash
# Step 1: Build
./scripts/build_linux.sh

# Step 2: Security setup
./scripts/sign_linux.sh

# Step 3: Install
sudo cp dist/LocalMonitorAgent /usr/local/bin/
sudo chmod 755 /usr/local/bin/LocalMonitorAgent
```

**What it does**:
- ✅ Creates AppArmor profile (Ubuntu/Debian)
- ✅ Creates SELinux policy (RHEL/Fedora)
- ✅ Creates desktop entry file
- ✅ Optional: Signs with GPG key

### Verify

```bash
# Check AppArmor
sudo aa-status | grep LocalMonitorAgent

# Check file permissions
ls -Z /usr/local/bin/LocalMonitorAgent

# Check auto-start
ls ~/.config/autostart/LocalMonitorAgent.desktop
```

---

## 📊 Comparison

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Remove Warnings | ✅ Commercial cert | ✅ Notarization | ✅ AppArmor/SELinux |
| Cost | $150-400/year | Free (needs Apple ID) | Free |
| Learning Curve | Easy | Medium | Medium |
| Auto-start | Registry | LaunchAgent | Desktop Entry |
| Distribution | .EXE | .APP | Binary + .desktop |

---

## 📋 Checklist

### Windows
- [ ] Run `create_certificate.ps1` (first time only)
- [ ] Run `build_windows.bat`
- [ ] Run `sign_windows.bat`
- [ ] Verify with `Get-AuthenticodeSignature`

### macOS
- [ ] Have Developer ID Certificate in Keychain
- [ ] Have Apple ID + app-specific password
- [ ] Run `build_macos.sh`
- [ ] Run `sign_macos.sh`
- [ ] Verify with `codesign` and `spctl`

### Linux
- [ ] Run `build_linux.sh`
- [ ] Run `sign_linux.sh`
- [ ] Install to `/usr/local/bin/`
- [ ] Verify with `aa-status` or `ls -Z`

---

## ✅ Status After Signing

### Windows
```
Before: ⚠️  Unknown Publisher warning
After:  ✓ Signed by [Your Name]
        ✓ No warning on first launch
```

### macOS
```
Before: ⚠️  "Cannot open" warning (Gatekeeper)
After:  ✓ Opens without warnings
        ✓ Notarized by Apple
```

### Linux
```
Before: ❌ May need sudo to run
After:  ✓ AppArmor/SELinux configured
        ✓ Auto-start in ~/.config/autostart/
        ✓ Can run as user
```

---

## 🆘 Troubleshooting

### Windows

**"SignTool not found"**
- Install Windows SDK: https://developer.microsoft.com/windows/downloads/windows-sdk/

**"Certificate password incorrect"**
- Double-check password during certificate creation
- Re-run `create_certificate.ps1` to make new certificate

### macOS

**"Certificate not found"**
- Import Developer ID Certificate in Keychain
- Or create new at developer.apple.com

**"Notarization failed"**
- Verify Apple ID credentials
- Check app-specific password (not regular password)
- Check internet connection

### Linux

**"AppArmor parser not found"**
- Normal on systems without AppArmor
- SELinux will be used instead

**"Permission denied" when installing**
- Use `sudo` for `/usr/local/bin/`
- Don't use sudo for `~/.config/autostart/`

---

## 📚 Full Documentation

- [docs/CODE_SIGNING.md](../docs/CODE_SIGNING.md) - Complete technical guide
- Windows: [scripts/create_certificate.ps1](scripts/create_certificate.ps1)
- macOS: [scripts/sign_macos.sh](scripts/sign_macos.sh)
- Linux: [scripts/sign_linux.sh](scripts/sign_linux.sh)

---

## 🎯 Production Checklist

Before deploying to users:

### Windows
- [ ] Purchase code signing certificate from Sectigo/Digicert/etc
- [ ] Code sign EXE with commercial certificate
- [ ] Test on clean Windows machine (no warning)
- [ ] Create .MSI installer (optional)

### macOS
- [ ] Code sign with Developer ID
- [ ] Notarize with Apple
- [ ] Test on other Mac (no Gatekeeper warning)
- [ ] Create .DMG for distribution (optional)

### Linux
- [ ] Configure AppArmor/SELinux profiles
- [ ] Test fine-grained permissions
- [ ] Create GPG signature for distribution
- [ ] Provide .deb/.rpm packages (optional)

---

**Next**: Run build and signing scripts for your platform above! 🚀
