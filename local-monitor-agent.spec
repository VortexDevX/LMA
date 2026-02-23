# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Local Monitor Agent.

Usage:
    pyinstaller local-monitor-agent.spec --noconfirm
"""

import sys
import os
from pathlib import Path

# Project root
PROJECT_ROOT = Path(SPECPATH)

# Platform detection
IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Code Signing Configuration (from environment variables)
CODESIGN_IDENTITY = os.environ.get("CODESIGN_IDENTITY", None)
ENTITLEMENTS_FILE = os.environ.get("ENTITLEMENTS_FILE", None)
if ENTITLEMENTS_FILE and Path(ENTITLEMENTS_FILE).exists():
    ENTITLEMENTS_FILE = str(Path(ENTITLEMENTS_FILE).absolute())
else:
    ENTITLEMENTS_FILE = None

block_cipher = None

# Data files to bundle
datas = [
    (str(PROJECT_ROOT / "data" / "categories.json"), "data"),
    (str(PROJECT_ROOT / "assets" / "icon.png"), "assets"),
    (str(PROJECT_ROOT / ".env"), "."),
]

# Add .ico for Windows wizard window icon
if IS_WINDOWS and (PROJECT_ROOT / "assets" / "icon.ico").exists():
    datas.append((str(PROJECT_ROOT / "assets" / "icon.ico"), "assets"))

# Add Tcl/Tk data files for tkinter (needed for setup wizard)
try:
    import tkinter
    _tk_dir = os.path.dirname(tkinter.__file__)

    # Search multiple potential Tcl/Tk data locations
    _tcl_search_paths = [
        os.path.join(_tk_dir, "..", "tcl"),                    # Windows
        os.path.join(os.path.dirname(sys.executable), "tcl"),  # Windows alt
        os.path.join(sys.prefix, "lib"),                       # Linux/macOS
        os.path.join(sys.prefix, "share"),                     # Linux alt
    ]

    for _search in _tcl_search_paths:
        if os.path.isdir(_search):
            for item in os.listdir(_search):
                item_path = os.path.join(_search, item)
                if os.path.isdir(item_path) and (item.startswith("tcl") or item.startswith("tk")):
                    datas.append((item_path, item))
                    print(f"[SPEC] Adding Tcl/Tk data: {item_path}")

except ImportError:
    print("[SPEC] WARNING: tkinter not available - setup wizard may not work in bundled exe")

# Binary files (SSL DLLs for Windows)
binaries = []
if IS_WINDOWS:
    python_base = os.path.dirname(sys.executable)
    dll_dir = os.path.join(python_base, "DLLs")
    
    ssl_dlls = ["libssl-3.dll", "libcrypto-3.dll", "_ssl.pyd"]
    for dll_name in ssl_dlls:
        dll_path = os.path.join(dll_dir, dll_name)
        if os.path.exists(dll_path):
            binaries.append((dll_path, "."))
            print(f"[SPEC] Adding SSL binary: {dll_path}")

    # Add tkinter DLL
    tk_dll = os.path.join(dll_dir, "_tkinter.pyd")
    if os.path.exists(tk_dll):
        binaries.append((tk_dll, "."))
        print(f"[SPEC] Adding tkinter binary: {tk_dll}")

# Hidden imports
hiddenimports = [
    "PIL._tkinter_finder",
    "ssl",
    "_ssl",
    "certifi",
    "src.utils.autostart",
    "tkinter",
    "tkinter.ttk",
    "_tkinter",
]

if IS_WINDOWS:
    hiddenimports.append("pystray._win32")
elif IS_MACOS:
    hiddenimports.extend(["pystray._darwin", "AppKit", "Foundation", "Quartz"])
else:
    hiddenimports.append("pystray._xorg")

# Excludes (reduce size)
excludes = [
    "unittest",
    "pydoc",
    "doctest",
    "difflib",
    "multiprocessing",
]

# Analysis
a = Analysis(
    [str(PROJECT_ROOT / "src" / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Platform-specific executable
if IS_WINDOWS:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="LocalMonitorAgent",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
        version=str(PROJECT_ROOT / "version_info.txt") if (PROJECT_ROOT / "version_info.txt").exists() else None,
    )

elif IS_MACOS:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="LocalMonitorAgent",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=CODESIGN_IDENTITY,
        entitlements_file=ENTITLEMENTS_FILE,
        icon=str(PROJECT_ROOT / "assets" / "icon.icns") if (PROJECT_ROOT / "assets" / "icon.icns").exists() else str(PROJECT_ROOT / "assets" / "icon.png"),
    )

    app = BUNDLE(
        exe,
        name="LocalMonitorAgent.app",
        icon=str(PROJECT_ROOT / "assets" / "icon.icns") if (PROJECT_ROOT / "assets" / "icon.icns").exists() else str(PROJECT_ROOT / "assets" / "icon.png"),
        bundle_identifier="com.company.localmonitoragent",
        info_plist={
            "CFBundleName": "Local Monitor Agent",
            "CFBundleDisplayName": "Local Monitor Agent",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "LSBackgroundOnly": False,
            "LSUIElement": True,
            "NSHighResolutionCapable": True,
        },
    )

else:  # Linux
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="LocalMonitorAgent",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(PROJECT_ROOT / "assets" / "icon.png"),
    )