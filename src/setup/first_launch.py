"""
First Launch Setup.
Handles employee authentication and device registration on first run.
CLI-based for now (GUI in Phase 15).
"""

import sys
import logging
import getpass

from src.platform import get_platform
from src.storage.sqlite_buffer import SQLiteBuffer
from src.network.api_sender import APISender

logger = logging.getLogger("agent.setup")


def run_first_launch(buffer: SQLiteBuffer, sender: APISender) -> bool:
    """
    Run the first-launch setup flow.
    Prompts for employee code, password, and TOTP, verifies with backend,
    registers the device.

    Returns True if setup completed successfully, False otherwise.
    """
    platform = get_platform()
    system_info = platform.get_system_info()

    print("")
    print("=" * 50)
    print("  Local Monitoring Agent - First Launch Setup")
    print("=" * 50)
    print("")
    print(f"  Device:   {system_info.hostname}")
    print(f"  OS:       {system_info.os_name} {system_info.os_version}")
    print(f"  MAC:      {system_info.mac_address}")
    print(f"  IP:       {system_info.local_ip}")
    print("")

    # Step 1: Get employee code
    employee_code = _prompt_employee_code()
    if employee_code is None:
        return False

    # Step 2: Get password and TOTP, then verify via login
    login_result = _verify_login(sender, employee_code)
    if login_result is None:
        return False

    employee_data = login_result

    # Step 3: Register device
    employee_id = employee_data.get("employee_id") or employee_data.get("id")
    device_registered = _register_device(
        sender, employee_id, system_info
    )

    # Step 4: Save identity
    if employee_id:
        buffer.set_config("employee_id", str(employee_id))
    buffer.set_config("employee_code", employee_code)
    buffer.set_config("device_mac", system_info.mac_address)
    buffer.set_config("hostname", system_info.hostname)

    if employee_data.get("full_name"):
        buffer.set_config("employee_name", employee_data["full_name"])
    if employee_data.get("access_token"):
        buffer.set_config("access_token", employee_data["access_token"])

    print("")
    print("=" * 50)
    name = employee_data.get("full_name", employee_code)
    print(f"  Setup complete! Welcome, {name}")
    print("  The agent will now run in the background.")
    print("=" * 50)
    print("")

    logger.info(
        f"First launch complete: employee_code={employee_code}, "
        f"device={system_info.hostname}"
    )
    return True


def _prompt_employee_code() -> str | None:
    """Prompt for employee code with retries."""
    for attempt in range(3):
        try:
            raw = input("  Enter your Employee Code: ").strip()
            if not raw:
                print("  Employee Code cannot be empty.")
                continue
            return raw
        except (KeyboardInterrupt, EOFError):
            print("\n  Setup cancelled.")
            return None

    print("  Too many invalid attempts. Setup cancelled.")
    return None


def _verify_login(sender: APISender, employee_code: str) -> dict | None:
    """Prompt for password and TOTP code, verify with backend via login."""
    for attempt in range(3):
        try:
            # Get password (hidden input)
            password = getpass.getpass("  Enter your password: ").strip()
            if not password:
                print("  Password cannot be empty.")
                continue

            # Get TOTP
            totp_code = input("  Enter your TOTP code: ").strip()
            if not totp_code:
                print("  TOTP code cannot be empty.")
                continue

            print("  Verifying...")
            result = sender.send_immediate(
                "/api/v1/auth/login",
                {
                    "employee_code": employee_code,
                    "password": password,
                    "totp_code": totp_code,
                },
            )

            if result is None:
                print("  Could not reach the server. Check your network.")
                continue

            # Check for access_token (successful login)
            if result.get("access_token"):
                name = result.get("full_name", "")
                print(f"  Verified successfully! ({name})")
                return result

            # Check for error message
            if result.get("detail"):
                print(f"  Login failed: {result['detail']}")
                continue

            print("  Invalid credentials. Please try again.")

        except (KeyboardInterrupt, EOFError):
            print("\n  Setup cancelled.")
            return None

    print("  Too many invalid attempts. Setup cancelled.")
    return None


def _register_device(
    sender: APISender, employee_id: int, system_info
) -> bool:
    """Register this device with the backend."""
    print("  Registering device...")

    result = sender.send_immediate(
        "/api/v1/devices/",
        {
            "employee_id": employee_id,
            "mac_address": system_info.mac_address,
            "ip_address": system_info.local_ip,
            "device_name": system_info.hostname,
            "device_type": _detect_device_type(),
        },
    )

    if result is not None:
        device_id = result.get("id", "unknown")
        print(f"  Device registered (id={device_id})")
        logger.info(f"Device registered: {result}")
        return True

    print("  Warning: Device registration failed. Will retry later.")
    logger.warning("Device registration failed during setup")
    return False


def _detect_device_type() -> str:
    """Detect if this is a laptop or desktop."""
    try:
        import psutil # type: ignore
        battery = psutil.sensors_battery()
        if battery is not None:
            return "laptop"
    except Exception:
        pass
    return "desktop"