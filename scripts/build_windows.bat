@echo off
REM ============================================================
REM Local Monitor Agent - Windows Build Script
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  Local Monitor Agent - Windows Build
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

REM Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
cd /d "%PROJECT_ROOT%"

echo Project root: %PROJECT_ROOT%
echo.

REM Activate venv if exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Install/upgrade PyInstaller
echo Installing PyInstaller...
pip install --upgrade pyinstaller >nul 2>&1

REM Clean previous builds
echo Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Generate icon if missing
if not exist "assets\icon.ico" (
    echo Generating icons...
    python scripts\generate_icon.py
)

REM Check for spec file
if exist "local-monitor-agent.spec" (
    echo Building with spec file...
    pyinstaller local-monitor-agent.spec --noconfirm
) else (
    echo Building with command line options...
    pyinstaller ^
        --name "LocalMonitorAgent" ^
        --onefile ^
        --windowed ^
        --icon "assets\icon.ico" ^
        --add-data "data\categories.json;data" ^
        --add-data "assets\icon.png;assets" ^
        --hidden-import "pystray._win32" ^
        --hidden-import "PIL._tkinter_finder" ^
        --version-file "version_info.txt" ^
        src\main.py
)

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    exit /b 1
)

echo.
echo ========================================
echo  Build Complete!
echo ========================================
echo.
echo Executable: dist\LocalMonitorAgent.exe
echo.

REM Show file size
for %%A in ("dist\LocalMonitorAgent.exe") do (
    set "SIZE=%%~zA"
    set /a "SIZE_MB=!SIZE! / 1048576"
    echo Size: !SIZE_MB! MB
)

echo.
pause