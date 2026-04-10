@echo off
REM ============================================================
REM Local Monitor Agent - Windows Installer
REM ============================================================
REM Usage:
REM   install_windows.bat                     (prompts for API key)
REM   install_windows.bat YOUR_API_KEY        (silent API key)
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  Local Monitor Agent - Installer
echo ========================================
echo.

REM --- Paths ---
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\LocalMonitorAgent"
set "DATA_DIR=%APPDATA%\LocalMonitorAgent"
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
set "EXE_SOURCE=%PROJECT_ROOT%\dist\LocalMonitorAgent.exe"

REM --- Check exe exists ---
if not exist "%EXE_SOURCE%" (
    echo ERROR: Executable not found at:
    echo   %EXE_SOURCE%
    echo.
    echo Run build_windows.bat first to create the executable.
    echo.
    pause
    exit /b 1
)

REM --- Check not already running ---
tasklist /FI "IMAGENAME eq LocalMonitorAgent.exe" 2>NUL | find /I "LocalMonitorAgent.exe" >NUL
if not errorlevel 1 (
    echo WARNING: Agent is currently running. Stopping it first...
    taskkill /IM LocalMonitorAgent.exe /F >NUL 2>&1
    timeout /t 2 /nobreak >NUL
)

REM --- API Key ---
set "API_KEY=%~1"
if "%API_KEY%"=="" (
    echo.
    set /p "API_KEY=Enter your API Key: "
)

if "%API_KEY%"=="" (
    echo ERROR: API Key is required.
    pause
    exit /b 1
)

REM --- Create directories ---
echo.
echo Installing...
echo.

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"

REM --- Copy executable ---
echo   [1/5] Copying executable...
copy /Y "%EXE_SOURCE%" "%INSTALL_DIR%\LocalMonitorAgent.exe" >NUL
if errorlevel 1 (
    echo ERROR: Failed to copy executable.
    pause
    exit /b 1
)
echo         OK: %INSTALL_DIR%\LocalMonitorAgent.exe

REM --- Create .env config ---
echo   [2/5] Creating configuration...
(
    echo API_KEY=%API_KEY%
    echo API_BASE_URL=https://emp-manan.mvlab.cloud
    echo LOG_LEVEL=INFO
) > "%DATA_DIR%\.env"
echo         OK: %DATA_DIR%\.env

REM --- Register auto-start ---
echo   [3/5] Registering auto-start...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "LocalMonitorAgent" /t REG_SZ /d "\"%INSTALL_DIR%\LocalMonitorAgent.exe\"" /f >NUL 2>&1
if errorlevel 1 (
    echo         WARN: Could not register auto-start
) else (
    echo         OK: Auto-start registered
)

REM --- Create Start Menu shortcut ---
echo   [4/5] Creating Start Menu shortcut...
set "SHORTCUT_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
if not exist "%SHORTCUT_DIR%" mkdir "%SHORTCUT_DIR%"

REM Use PowerShell to create shortcut
powershell -NoProfile -Command ^
    "$ws = New-Object -ComObject WScript.Shell; ^
     $s = $ws.CreateShortcut('%SHORTCUT_DIR%\Local Monitor Agent.lnk'); ^
     $s.TargetPath = '%INSTALL_DIR%\LocalMonitorAgent.exe'; ^
     $s.WorkingDirectory = '%INSTALL_DIR%'; ^
     $s.Description = 'Local Monitor Agent - Productivity Analytics'; ^
     $s.Save()" >NUL 2>&1
if errorlevel 1 (
    echo         WARN: Could not create shortcut
) else (
    echo         OK: Start Menu shortcut created
)

REM --- Summary ---
echo   [5/5] Verifying installation...
if exist "%INSTALL_DIR%\LocalMonitorAgent.exe" (
    echo         OK: Installation verified
) else (
    echo         ERROR: Installation verification failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Installation Complete!
echo ========================================
echo.
echo  Installed to: %INSTALL_DIR%
echo  Config at:    %DATA_DIR%\.env
echo  Auto-start:   Enabled
echo.
echo  NEXT STEPS:
echo  1. Run the agent for first-time setup:
echo     "%INSTALL_DIR%\LocalMonitorAgent.exe" --setup
echo.
echo  2. Or launch normally (will prompt for setup):
echo     "%INSTALL_DIR%\LocalMonitorAgent.exe"
echo.

set /p "LAUNCH=Launch agent now for setup? [Y/n]: "
if /I "%LAUNCH%"=="n" (
    echo.
    echo Done. Launch the agent manually when ready.
) else (
    echo.
    echo Launching agent...
    start "" "%INSTALL_DIR%\LocalMonitorAgent.exe"
)

echo.
pause