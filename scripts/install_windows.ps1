# ============================================================
# Local Monitor Agent - Windows Installer (PowerShell)
# ============================================================
# Usage:
#   .\install_windows.ps1
#   .\install_windows.ps1 -ApiKey "your_key"
#   .\install_windows.ps1 -ApiKey "your_key" -Silent
# ============================================================

param(
    [string]$ApiKey = "",
    [switch]$Silent = $false
)

$ErrorActionPreference = "Stop"

# --- Paths ---
$InstallDir = "$env:LOCALAPPDATA\Programs\LocalMonitorAgent"
$DataDir = "$env:APPDATA\LocalMonitorAgent"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$ExeSource = Join-Path $ProjectRoot "dist\LocalMonitorAgent.exe"

Write-Host ""
Write-Host "========================================"
Write-Host "  Local Monitor Agent - Installer"
Write-Host "========================================"
Write-Host ""

# --- Check exe ---
if (-not (Test-Path $ExeSource)) {
    Write-Host "ERROR: Executable not found at:" -ForegroundColor Red
    Write-Host "  $ExeSource"
    Write-Host ""
    Write-Host "Run build_windows.bat first."
    exit 1
}

# --- Stop if running ---
$proc = Get-Process -Name "LocalMonitorAgent" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "WARNING: Agent is running. Stopping..." -ForegroundColor Yellow
    Stop-Process -Name "LocalMonitorAgent" -Force
    Start-Sleep -Seconds 2
}

# --- API Key ---
if (-not $ApiKey) {
    $ApiKey = Read-Host "Enter your API Key"
    if (-not $ApiKey) {
        Write-Host "ERROR: API Key is required." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "Installing..."
Write-Host ""

# --- Create directories ---
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path "$DataDir\logs" -Force | Out-Null

# --- Copy executable ---
Write-Host "  [1/5] Copying executable..."
Copy-Item -Path $ExeSource -Destination "$InstallDir\LocalMonitorAgent.exe" -Force
Write-Host "        OK: $InstallDir\LocalMonitorAgent.exe"

# --- Create .env ---
Write-Host "  [2/5] Creating configuration..."
@"
API_KEY=$ApiKey
API_BASE_URL=https://manan.digimeck.in
LOG_LEVEL=INFO
"@ | Out-File -FilePath "$DataDir\.env" -Encoding utf8NoBOM -Force
Write-Host "        OK: $DataDir\.env"

# --- Auto-start ---
Write-Host "  [3/5] Registering auto-start..."
try {
    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
    Set-ItemProperty -Path $regPath -Name "LocalMonitorAgent" -Value "`"$InstallDir\LocalMonitorAgent.exe`""
    Write-Host "        OK: Auto-start registered"
} catch {
    Write-Host "        WARN: Could not register auto-start" -ForegroundColor Yellow
}

# --- Start Menu shortcut ---
Write-Host "  [4/5] Creating Start Menu shortcut..."
try {
    $ws = New-Object -ComObject WScript.Shell
    $shortcutPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Local Monitor Agent.lnk"
    $shortcut = $ws.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = "$InstallDir\LocalMonitorAgent.exe"
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.Description = "Local Monitor Agent"
    $shortcut.Save()
    Write-Host "        OK: Shortcut created"
} catch {
    Write-Host "        WARN: Could not create shortcut" -ForegroundColor Yellow
}

# --- Verify ---
Write-Host "  [5/5] Verifying..."
if (Test-Path "$InstallDir\LocalMonitorAgent.exe") {
    $size = (Get-Item "$InstallDir\LocalMonitorAgent.exe").Length / 1MB
    Write-Host "        OK: Installed ($([math]::Round($size, 1)) MB)"
} else {
    Write-Host "        ERROR: Verification failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================"
Write-Host "  Installation Complete!"
Write-Host "========================================"
Write-Host ""
Write-Host "  Installed to: $InstallDir"
Write-Host "  Config at:    $DataDir\.env"
Write-Host "  Auto-start:   Enabled"
Write-Host ""

if (-not $Silent) {
    $launch = Read-Host "Launch agent now for first-time setup? [Y/n]"
    if ($launch -ne "n") {
        Write-Host "Launching agent..."
        Start-Process -FilePath "$InstallDir\LocalMonitorAgent.exe"
    }
}
