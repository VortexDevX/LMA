"""
Local Monitoring Agent - Entry Point
"""

import sys
import os
import argparse


def _hide_console():
    """
    Hide the console window on Windows.
    Called when running in background mode (no CLI args).
    """
    if sys.platform != "win32":
        return

    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            SW_HIDE = 0
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def _has_cli_args() -> bool:
    """Check if any CLI flags were passed."""
    cli_flags = {"--version", "--status", "--reset", "--uninstall", "--setup", "--help", "-h"}
    return bool(cli_flags & set(sys.argv[1:]))


def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="LocalMonitorAgent",
        description="Local Monitoring Agent - Productivity Analytics",
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Print version and exit",
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Print agent status and exit",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Clear identity config (force re-setup on next launch)",
    )
    parser.add_argument(
        "--uninstall", action="store_true",
        help="Remove auto-start, clean data, and exit",
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="Force first-launch setup (even if already configured)",
    )
    return parser.parse_args()


def _cmd_version():
    """Print version and exit."""
    from src.config import config
    print(f"Local Monitor Agent v{config.AGENT_VERSION}")
    print(f"Python {sys.version.split()[0]} ({sys.platform})")
    return 0


def _cmd_status():
    """Print agent health status and exit."""
    from src.config import config
    from src.storage.sqlite_buffer import SQLiteBuffer
    from src.utils.autostart import is_autostart_enabled

    print(f"Local Monitor Agent v{config.AGENT_VERSION}")
    print(f"{'='*50}")

    # Lock file / running check
    if config.LOCK_FILE.exists():
        try:
            pid = int(config.LOCK_FILE.read_text().strip())
            import psutil # type: ignore
            if psutil.pid_exists(pid):
                print(f"Process:      RUNNING (PID {pid})")
            else:
                print(f"Process:      NOT RUNNING (stale lock, PID {pid})")
        except Exception:
            print("Process:      UNKNOWN")
    else:
        print("Process:      NOT RUNNING")

    # Auto-start
    print(f"Auto-start:   {'Enabled' if is_autostart_enabled() else 'Disabled'}")

    # Database
    if config.DB_PATH.exists():
        try:
            buffer = SQLiteBuffer(db_path=config.DB_PATH)
            stats = buffer.get_stats()
            emp_id = buffer.get_config("employee_id", "Not configured")
            emp_name = buffer.get_config("employee_name", "Unknown")
            device_mac = buffer.get_config("device_mac", "Not configured")
            last_sync = buffer.get_config("last_successful_sync", "Never")

            print(f"Database:     {config.DB_PATH} ({buffer.db_size_mb:.2f} MB)")
            print(f"Employee:     {emp_name} (ID: {emp_id})")
            print(f"Device MAC:   {device_mac}")
            print(f"Last sync:    {last_sync}")
            print(f"{'='*50}")
            print("Pending Records:")

            pending = buffer.get_pending_count()
            print(f"  Total:          {pending}")
            for table, counts in stats.items():
                if isinstance(counts, dict):
                    p = counts.get("pending", 0)
                    f = counts.get("failed", 0)
                    s = counts.get("sent", 0)
                    print(f"  {table:25s} pending={p}  failed={f}  sent={s}")

            buffer.close()
        except Exception as e:
            print(f"Database:     ERROR - {e}")
    else:
        print("Database:     Not created yet")

    # Paths
    print(f"{'='*50}")
    print(f"Data dir:     {config.DATA_DIR}")
    print(f"Log dir:      {config.LOG_DIR}")
    print(f"API URL:      {config.API_BASE_URL}")
    print(f"API key:      {'Configured' if config.API_KEY else 'NOT SET'}")

    return 0


def _cmd_reset():
    """Clear identity config to force re-setup."""
    from src.config import config
    from src.storage.sqlite_buffer import SQLiteBuffer

    # Check not running
    if config.LOCK_FILE.exists():
        try:
            pid = int(config.LOCK_FILE.read_text().strip())
            import psutil # type: ignore
            if psutil.pid_exists(pid):
                print(f"ERROR: Agent is running (PID {pid}). Stop it first.")
                return 1
        except Exception:
            pass

    if not config.DB_PATH.exists():
        print("Nothing to reset. Database doesn't exist.")
        return 0

    confirm = input("This will clear your identity. You'll need to re-setup. Continue? [y/N]: ")
    if confirm.strip().lower() != "y":
        print("Cancelled.")
        return 0

    try:
        buffer = SQLiteBuffer(db_path=config.DB_PATH)
        buffer.delete_config("employee_id")
        buffer.delete_config("device_mac")
        buffer.delete_config("employee_name")
        buffer.delete_config("employee_code")
        buffer.delete_config("access_token")
        buffer.delete_config("hostname")
        buffer.close()
        print("Identity cleared. Run the agent again to re-setup.")
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


def _cmd_uninstall():
    """Remove auto-start, optionally clean all data."""
    from src.config import config
    from src.utils.autostart import unregister_autostart, is_autostart_enabled
    import shutil

    # Check not running
    if config.LOCK_FILE.exists():
        try:
            pid = int(config.LOCK_FILE.read_text().strip())
            import psutil # type: ignore
            if psutil.pid_exists(pid):
                print(f"ERROR: Agent is running (PID {pid}). Stop it first.")
                return 1
        except Exception:
            pass

    print("Uninstalling Local Monitor Agent...")

    # Remove auto-start
    if is_autostart_enabled():
        if unregister_autostart():
            print("  [OK] Auto-start removed")
        else:
            print("  [WARN] Could not remove auto-start")
    else:
        print("  [OK] Auto-start was not registered")

    # Remove lock file
    if config.LOCK_FILE.exists():
        config.LOCK_FILE.unlink(missing_ok=True)
        print("  [OK] Lock file removed")

    # Ask about data
    confirm = input(f"\nDelete all agent data in {config.DATA_DIR}? [y/N]: ")
    if confirm.strip().lower() == "y":
        try:
            shutil.rmtree(config.DATA_DIR, ignore_errors=True)
            print(f"  [OK] Data directory removed: {config.DATA_DIR}")
        except Exception as e:
            print(f"  [WARN] Could not remove data directory: {e}")

        # Remove logs too
        try:
            if config.LOG_DIR.exists() and config.LOG_DIR != config.DATA_DIR:
                shutil.rmtree(config.LOG_DIR, ignore_errors=True)
                print(f"  [OK] Log directory removed: {config.LOG_DIR}")
        except Exception:
            pass
    else:
        print("  [SKIP] Data directory kept")

    print("\nUninstall complete.")
    return 0


def _cmd_setup():
    """Force first-launch setup."""
    from src.config import config
    from src.storage.sqlite_buffer import SQLiteBuffer
    from src.network.api_sender import APISender
    from src.setup.first_launch import run_first_launch
    from src.utils.autostart import register_autostart

    buffer = SQLiteBuffer(db_path=config.DB_PATH)
    sender = APISender(buffer)

    # Clear existing identity first
    buffer.delete_config("employee_id")
    buffer.delete_config("device_mac")
    buffer.delete_config("employee_name")
    buffer.delete_config("employee_code")
    buffer.delete_config("access_token")
    buffer.delete_config("hostname")

    success = run_first_launch(buffer, sender)

    if success:
        if register_autostart():
            print("  Auto-start registered.")
        else:
            print("  Note: Auto-start not registered (run as exe for auto-start).")

    buffer.close()
    return 0 if success else 1


def main():
    """Main entry point for the monitoring agent."""
    # If no CLI args, hide console and run in background
    if not _has_cli_args():
        _hide_console()

    # Ensure stdout/stderr exist (safety net)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    try:
        # Parse CLI args
        try:
            args = _parse_args()
        except SystemExit:
            return

        # Handle CLI commands
        if args.version:
            sys.exit(_cmd_version())
        if args.status:
            sys.exit(_cmd_status())
        if args.reset:
            sys.exit(_cmd_reset())
        if args.uninstall:
            sys.exit(_cmd_uninstall())
        if args.setup:
            sys.exit(_cmd_setup())

        # Normal run (console already hidden)
        from src.agent_core import AgentCore
        agent = AgentCore()
        exit_code = agent.run()
        sys.exit(exit_code)

    except Exception as e:
        log_path = os.path.join(
            os.environ.get("APPDATA", "."),
            "LocalMonitorAgent",
            "crash.log",
        )
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a") as f:
            import traceback
            f.write(f"\n{'='*50}\n")
            f.write(f"Crash at: {__import__('datetime').datetime.now()}\n")
            f.write(f"Error: {e}\n")
            traceback.print_exc(file=f)
        sys.exit(1)


if __name__ == "__main__":
    main()