#!/bin/bash

# ============================================================
# Sign Local Monitor Agent Executable
# macOS Code Signing Script
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo ""
echo "========================================"
echo " Code Signing - Local Monitor Agent"
echo "========================================"
echo ""

# Check if app exists
if [ ! -d "dist/LocalMonitorAgent.app" ]; then
    echo "ERROR: Application not found at dist/LocalMonitorAgent.app"
    echo "Run build script first: ./scripts/build_macos.sh"
    exit 1
fi

# Get certificate name (use argument or prompt)
if [ -n "$1" ]; then
    CERT_NAME="$1"
else
    echo "Available Developer ID certificates:"
    security find-identity -v -p codesigning | grep "Developer ID Application" || {
        echo ""
        echo "ERROR: No Developer ID certificates found"
        echo ""
        echo "To create a Developer ID certificate:"
        echo "1. Go to https://developer.apple.com/"
        echo "2. Create/renew your Developer ID Certificate"
        echo "3. Download and install in Keychain"
        exit 1
    }
    echo ""
    read -p "Enter certificate name or press Enter for first available: " CERT_NAME
    
    if [ -z "$CERT_NAME" ]; then
        # Use first available
        CERT_NAME=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/^[^"]*"\([^"]*\)".*/\1/')
    fi
fi

if [ -z "$CERT_NAME" ]; then
    echo "ERROR: No certificate selected"
    exit 1
fi

echo "Using certificate: $CERT_NAME"
echo ""

# Check if entitlements file exists
ENTITLEMENTS=""
if [ -f "macos_entitlements.plist" ]; then
    ENTITLEMENTS="--entitlements macos_entitlements.plist"
    echo "Using entitlements: macos_entitlements.plist"
fi

echo "Signing application..."
echo ""

# Sign the app
codesign --deep --force --verify --verbose --sign "$CERT_NAME" $ENTITLEMENTS \
    "dist/LocalMonitorAgent.app"

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Signing failed!"
    exit 1
fi

echo ""
echo "========================================"
echo " Verifying Signature"
echo "========================================"
echo ""

codesign --verify --verbose "dist/LocalMonitorAgent.app"

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Signature verification failed!"
    exit 1
fi

echo ""
echo "Checking notarization status..."
echo ""

spctl -a -vvv "dist/LocalMonitorAgent.app" || true

echo ""
echo "========================================"
echo " Signing Complete!"
echo "========================================"
echo ""
echo "Signed application: dist/LocalMonitorAgent.app"
echo ""

# Optional notarization
echo "Submit for Apple notarization to remove Gatekeeper warnings?"
echo "(This allows the app to run on other Macs without modification)"
echo ""
read -p "Submit for notarization? (requires Apple ID) [y/N]: " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "========================================"
    echo " Notarization (Apple)"
    echo "========================================"
    echo ""
    
    echo "Preparing for notarization..."
    if [ -f "LocalMonitorAgent.zip" ]; then
        rm "LocalMonitorAgent.zip"
    fi
    
    ditto -c -k --sequesterRsrc "dist/LocalMonitorAgent.app" LocalMonitorAgent.zip
    
    read -p "Enter Apple ID email: " APPLE_ID
    read -sp "Enter app-specific password (not regular password): " APPLE_PASSWORD
    echo ""
    read -p "Enter Team ID (found in Apple Developer account): " APPLE_TEAM_ID
    
    echo ""
    echo "Submitting to Apple for notarization..."
    echo "This may take 5-15 minutes..."
    echo ""
    
    xcrun notarytool submit LocalMonitorAgent.zip --wait \
        --apple-id "$APPLE_ID" \
        --password "$APPLE_PASSWORD" \
        --team-id "$APPLE_TEAM_ID"
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✓ Notarization successful!"
        echo ""
        echo "Stapling notarization ticket..."
        xcrun stapler staple "dist/LocalMonitorAgent.app"
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "✓ App is now notarized and ready for distribution"
            echo ""
            echo "The app will run on other Macs without any Gatekeeper warnings"
            
            # Cleanup
            rm -f LocalMonitorAgent.zip
        else
            echo "✗ Stapling failed"
            exit 1
        fi
    else
        echo "✗ Notarization failed"
        echo ""
        echo "The app is still signed and will work, but may show Gatekeeper warnings"
        exit 1
    fi
fi

echo ""
echo "Next steps:"
echo "  1. Test the app: open dist/LocalMonitorAgent.app"
echo "  2. Verify digital signature: codesign --verify --verbose dist/LocalMonitorAgent.app"
echo "  3. Check notarization: spctl -a -vvv dist/LocalMonitorAgent.app"
echo ""
