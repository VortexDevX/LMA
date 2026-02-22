#!/usr/bin/env python3
"""
Local Monitor Agent - Health Check / Diagnostic Tool

Standalone script. No venv required (uses only stdlib + sqlite3).
Can be run on any machine to check agent status.

Usage:
    python health_check.py
    python health_check.py --json
"""

import sys
import os
import json
import sqlite3
import socket
import argparse
from pathlib import Path
from datetime import datetime


def get_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "LocalMonitorAgent"


def check_process(data_dir: Path) -> dict:
    """Check if agent process is running."""
    lock_file = data_dir / "agent.lock"
    result = {"running": False, "pid": None, "lock_file_exists": lock_file.exists()}

    if lock_file.exists():
        try:
            pid = int(lock_file.read_text().strip())
            result["pid"] = pid
            # Check if process exists (cross-platform)
            try:
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                    if handle:
                        kernel32.CloseHandle(handle)
                        result["running"] = True
                else:
                    os.kill(pid, 0)
                    result["running"] = True
            except (OSError, PermissionError):
                result["running"] = False
        except (ValueError, Exception) as e:
            result["error"] = str(e)

    return result


def check_database(data_dir: Path) -> dict:
    """Check database status and contents."""
    db_path = data_dir / "agent.db"
    result = {
        "exists": db_path.exists(),
        "path": str(db_path),
        "size_mb": 0,
        "config": {},
        "pending": {},
        "total_pending": 0,
    }

    if not db_path.exists():
        return result

    try:
        result["size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 3)

        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Read config (exclude sensitive data)
        try:
            cursor.execute("SELECT key, value FROM config")
            for row in cursor.fetchall():
                key = row["key"]
                if key in ("access_token", "api_key"):
                    result["config"][key] = "***configured***"
                else:
                    result["config"][key] = row["value"]
        except sqlite3.OperationalError:
            result["config_error"] = "config table not found"

        # Count pending records per table
        tables = ["pending_sessions", "pending_app_usage", "pending_domain_visits"]
        for table in tables:
            try:
                cursor.execute(f"SELECT status, COUNT(*) as cnt FROM {table} GROUP BY status")
                counts = {}
                for row in cursor.fetchall():
                    counts[row["status"]] = row["cnt"]
                result["pending"][table] = counts
                result["total_pending"] += counts.get("pending", 0)
            except sqlite3.OperationalError:
                result["pending"][table] = {"error": "table not found"}

        # Last sent record timestamp
        try:
            cursor.execute(
                "SELECT MAX(created_at) as last_sent FROM sent_log"
            )
            row = cursor.fetchone()
            if row and row["last_sent"]:
                result["last_sent"] = row["last_sent"]
            else:
                result["last_sent"] = "Never"
        except sqlite3.OperationalError:
            result["last_sent"] = "Unknown"

        conn.close()

    except Exception as e:
        result["error"] = str(e)

    return result


def check_autostart() -> dict:
    """Check if auto-start is registered."""
    result = {"enabled": False, "method": None}

    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_QUERY_VALUE,
            )
            try:
                value, _ = winreg.QueryValueEx(key, "LocalMonitorAgent")
                result["enabled"] = True
                result["method"] = "registry"
                result["path"] = value
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except Exception as e:
            result["error"] = str(e)

    elif sys.platform == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.company.localmonitoragent.plist"
        result["enabled"] = plist.exists()
        result["method"] = "launchagent"
        if plist.exists():
            result["path"] = str(plist)

    else:
        desktop = Path.home() / ".config" / "autostart" / "localmonitoragent.desktop"
        result["enabled"] = desktop.exists()
        result["method"] = "desktop_entry"
        if desktop.exists():
            result["path"] = str(desktop)

    return result


def check_network(api_url: str = "manan.digimeck.in") -> dict:
    """Check network connectivity to backend API."""
    result = {"reachable": False, "host": api_url, "latency_ms": None}

    try:
        start = datetime.now()
        sock = socket.create_connection((api_url, 443), timeout=5)
        elapsed = (datetime.now() - start).total_seconds() * 1000
        sock.close()
        result["reachable"] = True
        result["latency_ms"] = round(elapsed, 1)
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        result["error"] = str(e)

    return result


def check_env_config(data_dir: Path) -> dict:
    """Check .env configuration file."""
    env_path = data_dir / ".env"
    result = {"exists": env_path.exists(), "path": str(env_path), "keys": []}

    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key = line.split("=", 1)[0].strip()
                        result["keys"].append(key)
            result["has_api_key"] = "API_KEY" in result["keys"]
        except Exception as e:
            result["error"] = str(e)
    else:
        result["has_api_key"] = False

    return result


def check_logs(data_dir: Path) -> dict:
    """Check log files."""
    if sys.platform == "darwin":
        log_dir = Path.home() / "Library" / "Logs" / "LocalMonitorAgent"
    else:
        log_dir = data_dir / "logs"

    result = {"log_dir": str(log_dir), "exists": log_dir.exists(), "files": []}

    if log_dir.exists():
        for f in sorted(log_dir.glob("*.log*")):
            stat = f.stat()
            result["files"].append({
                "name": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

        # Read last 5 lines of main log
        main_log = log_dir / "agent.log"
        if main_log.exists():
            try:
                with open(main_log, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    result["last_lines"] = [l.rstrip() for l in lines[-5:]]
            except Exception:
                pass

    return result


def run_health_check(as_json: bool = False):
    """Run all health checks and print report."""
    data_dir = get_data_dir()

    checks = {
        "timestamp": datetime.now().isoformat(),
        "platform": sys.platform,
        "data_dir": str(data_dir),
        "process": check_process(data_dir),
        "database": check_database(data_dir),
        "autostart": check_autostart(),
        "network": check_network(),
        "env_config": check_env_config(data_dir),
        "logs": check_logs(data_dir),
    }

    if as_json:
        print(json.dumps(checks, indent=2))
        return

    # Pretty print
    print("")
    print("=" * 55)
    print("  Local Monitor Agent - Health Check")
    print(f"  {checks['timestamp']}")
    print("=" * 55)
    print("")

    # Process
    proc = checks["process"]
    if proc["running"]:
        _ok(f"Process RUNNING (PID {proc['pid']})")
    elif proc["lock_file_exists"]:
        _warn(f"NOT RUNNING (stale lock, PID {proc['pid']})")
    else:
        _info("Process not running")

    # Auto-start
    auto = checks["autostart"]
    if auto["enabled"]:
        _ok(f"Auto-start enabled ({auto['method']})")
    else:
        _warn("Auto-start not registered")

    # Env config
    env = checks["env_config"]
    if env["exists"] and env.get("has_api_key"):
        _ok(f".env configured ({len(env['keys'])} keys)")
    elif env["exists"]:
        _warn(".env exists but missing API_KEY")
    else:
        _fail(f".env not found at {env['path']}")

    # Network
    net = checks["network"]
    if net["reachable"]:
        _ok(f"API reachable ({net['latency_ms']}ms)")
    else:
        _fail(f"API unreachable: {net.get('error', 'unknown')}")

    # Database
    db = checks["database"]
    if db["exists"]:
        _ok(f"Database: {db['size_mb']} MB")
        cfg = db["config"]
        emp = cfg.get("employee_id", "Not configured")
        name = cfg.get("employee_name", "Unknown")
        mac = cfg.get("device_mac", "Not configured")
        print(f"           Employee: {name} (ID: {emp})")
        print(f"           Device:   {mac}")

        # Pending
        total = db["total_pending"]
        if total > 0:
            _warn(f"{total} pending records")
            for table, counts in db["pending"].items():
                if isinstance(counts, dict) and not counts.get("error"):
                    p = counts.get("pending", 0)
                    f = counts.get("failed", 0)
                    if p > 0 or f > 0:
                        print(f"           {table}: pending={p} failed={f}")
        else:
            _ok("No pending records")

        last = db.get("last_sent", "Never")
        print(f"           Last sent: {last}")
    else:
        _warn("Database not created yet (agent never run)")

    # Logs
    logs = checks["logs"]
    if logs["exists"] and logs["files"]:
        total_kb = sum(f["size_kb"] for f in logs["files"])
        _ok(f"Logs: {len(logs['files'])} file(s), {total_kb:.1f} KB total")
        if logs.get("last_lines"):
            print("           Last log entry:")
            for line in logs["last_lines"][-2:]:
                print(f"             {line[:80]}")
    elif logs["exists"]:
        _info("Log directory exists but empty")
    else:
        _info("No log directory yet")

    print("")
    print("=" * 55)

    # Overall verdict
    issues = []
    if not env.get("has_api_key"):
        issues.append("API key not configured")
    if not net["reachable"]:
        issues.append("Cannot reach API server")
    if not db["exists"]:
        issues.append("Database not initialized")
    elif not db["config"].get("employee_id"):
        issues.append("Employee not configured (run setup)")
    if db.get("total_pending", 0) > 100:
        issues.append(f"{db['total_pending']} records stuck pending")

    if not issues:
        print("  VERDICT: ALL GOOD")
    else:
        print("  ISSUES FOUND:")
        for issue in issues:
            print(f"    - {issue}")

    print("=" * 55)
    print("")


def _ok(msg):
    print(f"  [OK]   {msg}")

def _warn(msg):
    print(f"  [WARN] {msg}")

def _fail(msg):
    print(f"  [FAIL] {msg}")

def _info(msg):
    print(f"  [INFO] {msg}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Health Check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    run_health_check(as_json=args.json)