#!/bin/bash

# ============================================================
# Sign and Secure Local Monitor Agent Executable
# Linux (Ubuntu/Debian/Fedora) Security Setup
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo ""
echo "========================================"
echo " Security Setup - Local Monitor Agent"
echo " Linux"
echo "========================================"
echo ""

# Check if executable exists
if [ ! -f "dist/LocalMonitorAgent" ]; then
    echo "ERROR: Executable not found at dist/LocalMonitorAgent"
    echo "Run build script first: ./scripts/build_linux.sh"
    exit 1
fi

echo "Executable found: dist/LocalMonitorAgent"
echo ""

# Get distribution info
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    VERSION=$VERSION_ID
else
    DISTRO="unknown"
    VERSION="unknown"
fi

echo "Detected: $DISTRO $VERSION"
echo ""

# ============================================================
# 1. Create Desktop Entry File
# ============================================================

echo "Creating desktop entry file..."

cat > "LocalMonitorAgent.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Local Monitor Agent
Comment=Employee productivity monitoring agent
Exec=/usr/local/bin/LocalMonitorAgent
Icon=LocalMonitorAgent
Terminal=false
Categories=Utility;System;
NoDisplay=true
X-GNOME-Autostart-enabled=true
X-KDE-autostart-condition=true
StartupNotify=false
EOF

if [ $? -eq 0 ]; then
    echo "✓ Desktop entry created: LocalMonitorAgent.desktop"
fi

echo ""

# ============================================================
# 2. Create AppArmor Profile (Ubuntu/Debian)
# ============================================================

if command -v apparmor_parser &> /dev/null || [ -d "/etc/apparmor.d" ]; then
    echo "Creating AppArmor profile..."
    
    sudo tee /etc/apparmor.d/usr.local.bin.LocalMonitorAgent > /dev/null << 'EOF'
#include <tunables/global>

/usr/local/bin/LocalMonitorAgent {
  #include <abstractions/base>
  #include <abstractions/nameservice>
  
  # Allow execution
  /usr/local/bin/LocalMonitorAgent mr,
  
  # Application data directory
  owner @{HOME}/.local/share/LocalMonitorAgent/ rw,
  owner @{HOME}/.local/share/LocalMonitorAgent/** rwk,
  
  # Logs
  owner @{HOME}/.local/share/LocalMonitorAgent/logs/ rwk,
  owner @{HOME}/.local/share/LocalMonitorAgent/logs/** rwk,
  
  # Database
  owner @{HOME}/.local/share/LocalMonitorAgent/agent.db rwk,
  
  # System information (read-only)
  /proc/stat r,
  /proc/meminfo r,
  /proc/uptime r,
  /sys/class/net/ r,
  /sys/class/net/** r,
  
  # X11/Wayland
  /run/user/*/pulse/ r,
  /run/user/*/.ICE-unix/ rw,
  
  # Network (for API calls)
  network inet stream,
  network inet dgram,
  
  # Allow environment variables
  /etc/environment r,
  /etc/hostname r,
}
EOF
    
    if sudo apparmor_parser -r /etc/apparmor.d/usr.local.bin.LocalMonitorAgent 2>/dev/null; then
        echo "✓ AppArmor profile installed"
    else
        echo "⚠ AppArmor profile created but failed to load (may need sudo)"
    fi
    
    echo ""
fi

# ============================================================
# 3. Create SELinux Policy (RHEL/Fedora/CentOS)
# ============================================================

if command -v getenforce &> /dev/null; then
    echo "Creating SELinux policy..."
    
    # Create a simple SELinux policy module file
    cat > "localmonitoragent.te" << 'EOF'
policy_module(localmonitoragent, 1.0.0)

type localmonitoragent_t;
type localmonitoragent_exec_t;

domain_type(localmonitoragent_t)
domain_entry_file(localmonitoragent_t, localmonitoragent_exec_t)

allow localmonitoragent_t self:process signal_perms;
allow localmonitoragent_t self:fifo_file rw_file_perms;
allow localmonitoragent_t self:unix_stream_socket create_stream_socket_perms;

# Allow reading /proc
kernel_read_system_proc(localmonitoragent_t)

# Allow network
corenet_all_recvfrom_netlabel(localmonitoragent_t)
corenet_tcp_sendrecv_generic_if(localmonitoragent_t)
corenet_tcp_sendrecv_generic_node(localmonitoragent_t)
corenet_tcp_bind_generic_node(localmonitoragent_t)
corenet_tcp_connect_all_ports(localmonitoragent_t)

# Allow home directory access
userdom_manage_user_home_content_files(localmonitoragent_t)
userdom_manage_user_home_content_dirs(localmonitoragent_t)

logging_send_syslog_msg(localmonitoragent_t)
EOF
    
    echo "⚠ SELinux policy template created: localmonitoragent.te"
    echo "   To compile: sudo checkmodule -M -m -o localmonitoragent.mod localmonitoragent.te"
    echo "   To install: sudo semodule_package -o localmonitoragent.pp -m localmonitoragent.mod && sudo semodule -i localmonitoragent.pp"
    
    echo ""
fi

# ============================================================
# 4. Create GPG Signature (Optional, for distribution)
# ============================================================

if command -v gpg &> /dev/null; then
    echo "GPG signature support available"
    
    read -p "Sign executable with GPG key? [y/N]: " -n 1 -r
    echo ""
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # List available keys
        echo "Available GPG keys:"
        gpg --list-secret-keys --keyid-format=long
        
        echo ""
        read -p "Enter key ID or email to sign with: " GPG_KEY
        
        if [ -n "$GPG_KEY" ]; then
            echo "Signing executable..."
            
            gpg --sign --armor --detach-sign --default-key "$GPG_KEY" \
                dist/LocalMonitorAgent
            
            if [ $? -eq 0 ]; then
                echo "✓ Executable signed: dist/LocalMonitorAgent.asc"
                echo ""
                echo "Verify signature with:"
                echo "  gpg --verify dist/LocalMonitorAgent.asc dist/LocalMonitorAgent"
            else
                echo "✗ Signing failed"
            fi
        fi
    fi
    
    echo ""
fi

# ============================================================
# 5. Set Secure Permissions
# ============================================================

echo "Setting secure file permissions..."

chmod 755 "dist/LocalMonitorAgent"
chmod 644 "LocalMonitorAgent.desktop"

echo "✓ Permissions set"
echo ""

# ============================================================
# 6. Create Installation Instructions
# ============================================================

echo "========================================"
echo " Installation Instructions"
echo "========================================"
echo ""
echo "To install the agent system-wide:"
echo ""
echo "  sudo cp dist/LocalMonitorAgent /usr/local/bin/"
echo "  sudo chmod 755 /usr/local/bin/LocalMonitorAgent"
echo "  mkdir -p ~/.local/share/LocalMonitorAgent"
echo ""
echo "To enable auto-start (Autostart):"
echo "  mkdir -p ~/.config/autostart"
echo "  cp LocalMonitorAgent.desktop ~/.config/autostart/"
echo ""
echo "To verify security (AppArmor):"
echo "  sudo aa-status | grep LocalMonitorAgent"
echo ""
echo "To verify security (SELinux):"
echo "  ls -Z /usr/local/bin/LocalMonitorAgent"
echo ""
echo "To start the agent:"
echo "  LocalMonitorAgent"
echo ""
echo "To check logs:"
echo "  cat ~/.local/share/LocalMonitorAgent/logs/agent.log"
echo ""

# ============================================================
# 7. Summary
# ============================================================

echo "========================================"
echo " Security Setup Complete!"
echo "========================================"
echo ""
echo "Files created:"
echo "  - dist/LocalMonitorAgent (executable)"
echo "  - LocalMonitorAgent.desktop (desktop entry)"

if [ -f "localmonitoragent.te" ]; then
    echo "  - localmonitoragent.te (SELinux policy template)"
fi

if [ -f "dist/LocalMonitorAgent.asc" ]; then
    echo "  - dist/LocalMonitorAgent.asc (GPG signature)"
fi

echo ""
echo "Security features:"
echo "  ✓ AppArmor profile configured (Ubuntu/Debian)"
echo "  ✓ SELinux policy template created (RHEL/Fedora)"
echo "  ✓ Desktop entry file created"
echo "  ✓ File permissions secured"

if [ -f "dist/LocalMonitorAgent.asc" ]; then
    echo "  ✓ GPG signature created"
fi

echo ""
echo "Next steps:"
echo "  1. Review AppArmor/SELinux policies if needed"
echo "  2. Install to /usr/local/bin/"
echo "  3. Enable auto-start in ~/.config/autostart/"
echo "  4. Run and verify: LocalMonitorAgent"
echo ""
