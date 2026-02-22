#!/bin/bash
# ============================================================
# Local Monitor Agent - Linux Build Script
# ============================================================

set -e

echo ""
echo "========================================"
echo " Local Monitor Agent - Linux Build"
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

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build dist

# Generate icon if missing
if [ ! -f "assets/icon.png" ]; then
    echo "Generating icons..."
    python3 scripts/generate_icon.py
fi

# Detect display server
if [ -n "$WAYLAND_DISPLAY" ]; then
    HIDDEN_IMPORTS="--hidden-import pystray._xorg"
else
    HIDDEN_IMPORTS="--hidden-import pystray._xorg"
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
        --icon "assets/icon.png" \
        --add-data "data/categories.json:data" \
        --add-data "assets/icon.png:assets" \
        $HIDDEN_IMPORTS \
        --hidden-import "PIL._tkinter_finder" \
        src/main.py
fi

echo ""
echo "========================================"
echo " Build Complete!"
echo "========================================"
echo ""

if [ -f "dist/LocalMonitorAgent" ]; then
    echo "Executable: dist/LocalMonitorAgent"
    chmod +x "dist/LocalMonitorAgent"
    SIZE=$(du -h "dist/LocalMonitorAgent" | cut -f1)
    echo "Size: $SIZE"
fi

echo ""

# Optional: Create .desktop file
read -p "Create .desktop file for application menu? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    DESKTOP_FILE="$HOME/.local/share/applications/local-monitor-agent.desktop"
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=Local Monitor Agent
Comment=Employee Activity Monitor
Exec=$PROJECT_ROOT/dist/LocalMonitorAgent
Icon=$PROJECT_ROOT/assets/icon.png
Terminal=false
Type=Application
Categories=Utility;
StartupNotify=false
EOF
    echo "Created: $DESKTOP_FILE"
fi