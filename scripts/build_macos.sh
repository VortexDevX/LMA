#!/bin/bash
# ============================================================
# Local Monitor Agent - macOS Build Script
# ============================================================

set -e

echo ""
echo "========================================"
echo " Local Monitor Agent - macOS Build"
echo "========================================"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "Project root: $PROJECT_ROOT"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found"
    exit 1
fi

# Activate venv if exists
if [ -f "venv/bin/activate" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Install/upgrade PyInstaller
echo "Installing PyInstaller..."
pip install --upgrade pyinstaller > /dev/null 2>&1

# Install macOS dependencies
echo "Installing macOS dependencies..."
pip install pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz > /dev/null 2>&1

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist

# Generate icon if missing
if [ ! -f "assets/icon.icns" ]; then
    echo "Generating icons..."
    python3 scripts/generate_icon.py
fi

# Build
if [ -f "local-monitor-agent.spec" ]; then
    echo "Building with spec file..."
    pyinstaller local-monitor-agent.spec --noconfirm
else
    echo "Building with command line options..."
    pyinstaller \
        --name "LocalMonitorAgent" \
        --onefile \
        --windowed \
        --icon "assets/icon.icns" \
        --add-data "data/categories.json:data" \
        --add-data "assets/icon.png:assets" \
        --hidden-import "pystray._darwin" \
        --hidden-import "PIL._tkinter_finder" \
        --osx-bundle-identifier "com.company.localmonitoragent" \
        src/main.py
fi

echo ""
echo "========================================"
echo " Build Complete!"
echo "========================================"
echo ""

if [ -f "dist/LocalMonitorAgent" ]; then
    echo "Executable: dist/LocalMonitorAgent"
    SIZE=$(du -h "dist/LocalMonitorAgent" | cut -f1)
    echo "Size: $SIZE"
elif [ -d "dist/LocalMonitorAgent.app" ]; then
    echo "App Bundle: dist/LocalMonitorAgent.app"
    SIZE=$(du -sh "dist/LocalMonitorAgent.app" | cut -f1)
    echo "Size: $SIZE"
fi

echo ""