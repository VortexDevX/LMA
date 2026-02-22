@echo off
REM ============================================================
REM Local Monitor Agent - Windows Uninstaller
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  Local Monitor Agent - Uninstaller
echo ========================================
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\Programs\LocalMonitorAgent"
set "DATA_DIR=%APPDATA%\LocalMonitorAgent"

REM --- Confirm ---
set /p "CONFIRM=Are you sure you want to uninstall Local Monitor Agent? [y/N]: "
if /I not "%CONFIRM%"=="y" (
    echo Cancelled.
    pause
    exit /b 0
)

echo.
echo Uninstalling...
echo.

REM --- Stop running agent ---
echo   [1/5] Stopping agent...
tasklist /FI "IMAGENAME eq LocalMonitorAgent.exe" 2>NUL | find /I "LocalMonitorAgent.exe" >NUL
if not errorlevel 1 (
    taskkill /IM LocalMonitorAgent.exe /F >NUL 2>&1
    timeout /t 2 /nobreak >NUL
    echo         OK: Agent stopped
) else (
    echo         OK: Agent was not running
)

REM --- Remove auto-start ---
echo   [2/5] Removing auto-start...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "LocalMonitorAgent" /f >NUL 2>&1
if errorlevel 1 (
    echo         OK: Auto-start was not registered
) else (
    echo         OK: Auto-start removed
)

REM --- Remove Start Menu shortcut ---
echo   [3/5] Removing shortcuts...
set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Local Monitor Agent.lnk"
if exist "%SHORTCUT%" (
    del /F /Q "%SHORTCUT%" >NUL 2>&1
    echo         OK: Start Menu shortcut removed
) else (
    echo         OK: No shortcut found
)

REM --- Remove install directory ---
echo   [4/5] Removing program files...
if exist "%INSTALL_DIR%" (
    rmdir /S /Q "%INSTALL_DIR%" >NUL 2>&1
    if exist "%INSTALL_DIR%" (
        echo         WARN: Could not fully remove %INSTALL_DIR%
        echo               (files may be in use, remove manually)
    ) else (
        echo         OK: %INSTALL_DIR% removed
    )
) else (
    echo         OK: Install directory not found
)

REM --- Remove data directory ---
echo   [5/5] Agent data...
if exist "%DATA_DIR%" (
    echo.
    echo   Data directory: %DATA_DIR%
    echo   Contains: database, logs, configuration
    echo.
    set /p "DEL_DATA=  Delete all agent data? [y/N]: "
    if /I "!DEL_DATA!"=="y" (
        rmdir /S /Q "%DATA_DIR%" >NUL 2>&1
        if exist "%DATA_DIR%" (
            echo         WARN: Could not fully remove data directory
        ) else (
            echo         OK: Data directory removed
        )
    ) else (
        echo         SKIP: Data directory kept at %DATA_DIR%
    )
) else (
    echo         OK: No data directory found
)

echo.
echo ========================================
echo  Uninstall Complete
echo ========================================
echo.
pause