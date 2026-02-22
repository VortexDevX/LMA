@echo off
REM ============================================================
REM Sign Local Monitor Agent Executable
REM Windows Code Signing Script
REM ============================================================

setlocal enabledelayedexpansion

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
cd /d "%PROJECT_ROOT%"

echo.
echo ========================================
echo  Code Signing - Local Monitor Agent
echo ========================================
echo.

REM Check if executable exists
if not exist "dist\LocalMonitorAgent.exe" (
    echo ERROR: Executable not found at dist\LocalMonitorAgent.exe
    echo Run build script first: build_windows.bat
    exit /b 1
)

REM Check if certificate exists
if not exist "lma_cert.pfx" (
    echo ERROR: Certificate file not found: lma_cert.pfx
    echo.
    echo To create a certificate, run: .\scripts\create_certificate.ps1
    exit /b 1
)

REM Find SignTool dynamically
set "SIGNTOOL="
for /f "delims=" %%F in ('dir /b /s /o-n "C:\Program Files (x86)\Windows Kits\10\bin\*signtool.exe" 2^>nul ^| findstr /i "x64\\signtool.exe"') do (
    if not defined SIGNTOOL set "SIGNTOOL=%%F"
)

if not defined SIGNTOOL (
    echo ERROR: SignTool not found.
    echo.
    echo Install Windows SDK from:
    echo   https://developer.microsoft.com/windows/downloads/windows-sdk/
    echo.
    echo Or use PowerShell to sign instead:
    echo   Set-AuthenticodeSignature -FilePath "dist\LocalMonitorAgent.exe" -Certificate (Get-PfxCertificate "lma_cert.pfx"^)
    exit /b 1
)

echo SignTool found: %SIGNTOOL%
echo.

REM Get certificate password
set /p CERT_PASSWORD="Enter certificate password: "

echo.
echo Signing executable...
echo.

REM Sign the executable
"%SIGNTOOL%" sign /f lma_cert.pfx /p %CERT_PASSWORD% ^
  /t http://timestamp.digicert.com /fd SHA256 ^
  /d "Local Monitor Agent" /du "https://github.com/VortexDevX/LMA.git" ^
  "dist\LocalMonitorAgent.exe"

if errorlevel 1 (
    echo.
    echo ERROR: Signing failed!
    exit /b 1
)

echo.
echo ========================================
echo  Verifying Signature
echo ========================================
echo.

"%SIGNTOOL%" verify /pa "dist\LocalMonitorAgent.exe" 2>nul

if errorlevel 1 (
    echo.
    echo NOTE: Verification returned a warning. This is expected for
    echo self-signed certificates that are not in the Trusted Root store.
    echo.
    echo To fix, run create_certificate.ps1 again or manually trust the cert:
    echo   certutil -addstore -user Root lma_cert.cer
    echo.
    echo The executable IS signed - it will just show a publisher warning on other machines.
)

echo.
echo ========================================
echo  Signing Complete!
echo ========================================
echo.
echo Signed executable: dist\LocalMonitorAgent.exe
echo.
pause
