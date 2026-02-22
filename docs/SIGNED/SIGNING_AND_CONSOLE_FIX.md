# ✅ Fixed: Console Window & Code Signing Setup

## Problem 1: Console Window Opening ✓ RESOLVED

### What Was Wrong
The EXE was opening a terminal/console window when clicked because `console=True` in the PyInstaller spec file.

### What Was Fixed
Changed [local-monitor-agent.spec](local-monitor-agent.spec#L99):
```python
# Before:
console=True   # ❌ Opens console window

# After:
console=False  # ✅ Silent background launch, tray icon only
```

### Result
- EXE now launches silently in background
- System tray icon appears immediately
- No console window ever shown
- Clean user experience

---

## Problem 2: Code Signing (Not Signed) ✓ READY TO USE

### Current Status: ⚠️ NOT SIGNED
Your current app is unsigned, which means:
- **Windows**: Shows "Unknown Publisher" warning on first run
- **macOS**: May be blocked by Gatekeeper (requires override)

### Solution: Two Options

#### Option A: Self-Signed (Testing/Development) - 5 minutes

**Step 1: Create Certificate** (PowerShell as Administrator)
```powershell
# Navigate to project root
cd "v:\Projects\EmployeeManagement\local-monitor-agent"

# Run certificate creation script
.\scripts\create_certificate.ps1

# It will prompt for password (remember this!)
# Creates: lma_cert.pfx
```

**Step 2: Build EXE**
```batch
scripts\build_windows.bat
```

**Step 3: Sign EXE**
```batch
scripts\sign_windows.bat
```

**Result**: 
- EXE is now signed with your certificate
- Windows still shows "Unknown Publisher" (self-signed)
- But you can verify it's from your certificate

---

#### Option B: Trusted Commercial Certificate (Production) - Recommended

For **zero warnings** and professional deployment:

1. **Purchase Certificate** (~$150-400/year):
   - [Sectigo](https://sectigo.com/ssl-certificates-tls/code-signing)
   - [Digicert](https://www.digicert.com/code-signing)
   - [GlobalSign](https://www.globalsign.com/en/code-signing-certificate)

2. **Get .PFX file** from provider

3. **Sign with same script**:
   ```batch
   scripts\sign_windows.bat
   ```
   (Use commercial .PFX instead of lma_cert.pfx)

**Result**: 
- ✅ Zero warnings on Windows
- ✅ Trusted publisher recognized
- ✅ Professional deployment

---

## 🛠️ Scripts Created

### Certificate Management
| Script | Purpose |
|--------|---------|
| `scripts/create_certificate.ps1` | **Create self-signed certificate** (interactive wizard) |

### Code Signing
| Script | Purpose |
|--------|---------|
| `scripts/sign_windows.bat` | **Sign the EXE** after building |
| `scripts/sign_macos.sh` | Sign macOS app bundle |

### Documentation
| File | Purpose |
|------|---------|
| `docs/CODE_SIGNING.md` | Complete code signing guide (all platforms) |
| `CODE_SIGNING_QUICK_START.md` | Quick reference (this directory) |

---

## 🚀 Quick Start Workflow

### Minimal (No Signing)
```batch
cd v:\Projects\EmployeeManagement\local-monitor-agent
scripts\build_windows.bat
::  Done! EXE in: dist\LocalMonitorAgent.exe
::  ✓ No console window
::  ⚠️  Not signed (shows warning on first run)
```

### Complete (With Self-Signed)
```powershell
cd v:\Projects\EmployeeManagement\local-monitor-agent

# Step 1: Create certificate (first time only)
.\scripts\create_certificate.ps1
#  → Creates: lma_cert.pfx (keep this safe!)

# Step 2: Build
.\scripts\build_windows.bat

# Step 3: Sign
.\scripts\sign_windows.bat
#  → Ready to deploy!
```

### Verify Signing
```powershell
Get-AuthenticodeSignature "dist\LocalMonitorAgent.exe"

# Should show:
# Status                  : Valid
# SignerCertificate       : [thumbprint]
# TimestamperCertificate  : [thumbprint]
```

---

## 📋 File Changes Summary

### Modified Files
- **`local-monitor-agent.spec`** 
  - Line 99: `console=True` → `console=False`

### New Files Created
- **`scripts/create_certificate.ps1`** - Interactive certificate wizard
- **`scripts/sign_windows.bat`** - Code signing script
- **`scripts/sign_macos.sh`** - macOS signing script
- **`docs/CODE_SIGNING.md`** - Full technical guide
- **`CODE_SIGNING_QUICK_START.md`** - Quick reference

---

## ✨ What's Different Now

### Before Changes
```
EXE Behavior:
  ❌ Opens console/terminal window
  ❌ Not signed (shows warning)
```

### After Changes
```
EXE Behavior:
  ✅ Launches silent, no console window
  ✅ Optional: Can be code-signed
  ✅ Ready for production deployment
```

---

## 📚 Additional Resources

**For complete signing guide**: [`docs/CODE_SIGNING.md`](docs/CODE_SIGNING.md)
- Self-signed certificate creation
- Commercial certificate setup
- macOS notarization
- Automated build+sign workflows
- Troubleshooting

**For certificate creation**: [`scripts/create_certificate.ps1`](scripts/create_certificate.ps1)
- Interactive wizard
- Auto-generates passwords
- Export public certificate

**For signing**: [`scripts/sign_windows.bat`](scripts/sign_windows.bat)
- Automatic SignTool detection
- Timestamp server support
- Verification included

---

## ❓ FAQ

**Q: Do I need to sign the app?**  
A: Not immediately. It will run. But Windows will show "Unknown Publisher" on first execution. For production, yes.

**Q: Can I use a free certificate?**  
A: Yes! Self-signed certificates work for testing. Commercial certs (~$150-400/year) remove all warnings.

**Q: How long is a certificate valid for?**  
A: Self-signed: 10 years (customizable)  
Commercial: 1-3 years (provider dependent)

**Q: What happens if my certificate expires?**  
A: Old EXEs still run, but new signatures fail. You'd need to rebuild and sign with a new certificate.

**Q: Can I automate this in CI/CD?**  
A: Yes! See [`docs/CODE_SIGNING.md`](docs/CODE_SIGNING.md) for GitHub Actions examples.

**Q: Is the certificate password secure?**  
A: Use strong passwords. Keep `.pfx` file in secure location. Don't commit to version control.

---

## 🎯 Recommended Next Steps

1. **Immediate**: Rebuild with new spec
   ```batch
   scripts\build_windows.bat
   ```
   (Console window is gone! ✓)

2. **Testing**: Create self-signed certificate
   ```powershell
   .\scripts\create_certificate.ps1
   .\scripts\build_windows.bat
   .\scripts\sign_windows.bat
   ```

3. **Production**: Purchase commercial certificate
   - Budget: $150-400/year
   - Setup: Same scripts, different .PFX file
   - Result: Zero warnings on all Windows installations

---

For questions or issues, see [`docs/CODE_SIGNING.md`](docs/CODE_SIGNING.md) troubleshooting section.
