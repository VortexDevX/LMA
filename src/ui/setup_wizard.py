"""
Setup Wizard GUI.
tkinter-based login and device registration for first launch.
Used when no interactive terminal is available (windowed exe mode).
"""

import sys
import threading
import logging
from pathlib import Path

from src.config import config

logger = logging.getLogger("agent.ui.wizard")

_TK_AVAILABLE = False
try:
    import tkinter as tk
    from tkinter import ttk

    _TK_AVAILABLE = True
except ImportError:
    logger.debug("tkinter not available")


def is_tk_available() -> bool:
    """Check if tkinter is available for GUI."""
    return _TK_AVAILABLE


def run_setup_wizard(buffer, sender) -> bool:
    """
    Launch the setup wizard GUI.
    Blocks until complete or cancelled.
    Returns True if setup succeeded, False otherwise.
    """
    if not _TK_AVAILABLE:
        logger.error("Cannot launch setup wizard: tkinter not available")
        return False

    try:
        wizard = SetupWizard(buffer, sender)
        return wizard.run()
    except Exception as e:
        logger.error(f"Setup wizard failed: {e}")
        return False


class SetupWizard:
    """tkinter login wizard for first-launch authentication and device registration."""

    def __init__(self, buffer, sender):
        self._buffer = buffer
        self._sender = sender
        self._success = False
        self._root = None

        from src.platform import get_platform

        self._platform = get_platform()
        self._system_info = self._platform.get_system_info()

    def run(self) -> bool:
        """Create and show the wizard. Blocks until closed. Returns success."""
        self._root = tk.Tk()  # type: ignore
        self._root.title("Local Monitor Agent \u2014 Setup")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Center on screen
        w, h = 420, 400
        x = (self._root.winfo_screenwidth() - w) // 2
        y = (self._root.winfo_screenheight() - h) // 2
        self._root.geometry(f"{w}x{h}+{x}+{y}")

        self._set_window_icon()
        self._build_login_form()

        self._root.mainloop()
        return self._success

    def _set_window_icon(self):
        """Set window icon if available."""
        try:
            if getattr(sys, "frozen", False):
                base = Path(sys._MEIPASS)  # type: ignore
            else:
                base = Path(__file__).parent.parent.parent
            ico = base / "assets" / "icon.ico"
            if ico.exists():
                self._root.iconbitmap(str(ico))  # type: ignore
        except Exception:
            pass

    # --------------------------------------------------
    # Login form
    # --------------------------------------------------

    def _build_login_form(self):
        """Build the login screen."""
        for w in self._root.winfo_children():  # type: ignore
            w.destroy()

        frame = ttk.Frame(self._root, padding=20)  # type: ignore
        frame.pack(fill="both", expand=True)

        # Title
        ttk.Label(  # type: ignore
            frame, text="Local Monitor Agent", font=("", 14, "bold")
        ).pack(pady=(0, 5))
        ttk.Label(frame, text="First-time setup", font=("", 10)).pack(  # type: ignore
            pady=(0, 15)
        )

        # Device info box
        dev = ttk.LabelFrame(frame, text="Device", padding=8)  # type: ignore
        dev.pack(fill="x", pady=(0, 15))
        ttk.Label(dev, text=f"Host:  {self._system_info.hostname}").pack(  # type: ignore
            anchor="w"
        )
        ttk.Label(dev, text=f"MAC:   {self._system_info.mac_address}").pack(  # type: ignore
            anchor="w"
        )

        # Form fields
        form = ttk.Frame(frame)  # type: ignore
        form.pack(fill="x")

        ttk.Label(form, text="Employee ID:").pack(anchor="w")  # type: ignore
        self._emp_var = tk.StringVar()  # type: ignore
        emp_entry = ttk.Entry(form, textvariable=self._emp_var, width=30)  # type: ignore
        emp_entry.pack(fill="x", pady=(0, 8))
        emp_entry.focus_set()

        ttk.Label(form, text="Password:").pack(anchor="w")  # type: ignore
        self._pwd_var = tk.StringVar()  # type: ignore
        ttk.Entry(form, textvariable=self._pwd_var, show="\u2022", width=30).pack(  # type: ignore
            fill="x", pady=(0, 8)
        )

        ttk.Label(form, text="TOTP Code:").pack(anchor="w")  # type: ignore
        self._totp_var = tk.StringVar()  # type: ignore
        totp_entry = ttk.Entry(form, textvariable=self._totp_var, width=30)  # type: ignore
        totp_entry.pack(fill="x", pady=(0, 12))
        totp_entry.bind("<Return>", lambda e: self._on_login())

        # Status label
        self._status_var = tk.StringVar(value="")  # type: ignore
        self._status_label = ttk.Label(  # type: ignore
            form, textvariable=self._status_var, foreground="red", wraplength=380
        )
        self._status_label.pack(fill="x", pady=(0, 8))

        # Login button
        self._login_btn = ttk.Button(  # type: ignore
            form, text="Login & Setup", command=self._on_login
        )
        self._login_btn.pack(fill="x")

    # --------------------------------------------------
    # Login logic
    # --------------------------------------------------

    def _on_login(self):
        """Validate inputs, start login in background thread."""
        emp_raw = self._emp_var.get().strip()
        pwd = self._pwd_var.get()
        totp = self._totp_var.get().strip()

        if not emp_raw:
            self._show_error("Employee ID is required.")
            return
        try:
            emp_id = int(emp_raw)
            if emp_id <= 0:
                raise ValueError
        except ValueError:
            self._show_error("Employee ID must be a positive number.")
            return
        if not pwd:
            self._show_error("Password is required.")
            return
        if not totp:
            self._show_error("TOTP code is required.")
            return

        self._login_btn.configure(state="disabled")
        self._show_status("Verifying...")

        threading.Thread(
            target=self._do_login,
            args=(emp_id, pwd, totp),
            daemon=True,
        ).start()

    def _do_login(self, emp_id: int, password: str, totp: str):
        """Perform login + device registration in background thread."""
        try:
            # Step 1: Login
            result = self._sender.send_immediate(
                "/api/v1/auth/login",
                {
                    "employee_id": emp_id,
                    "password": password,
                    "totp_code": totp,
                },
            )

            if result is None:
                self._root.after(  # type: ignore
                    0, self._on_login_error, "Could not reach server. Check network."
                )
                return

            if not result.get("access_token"):
                msg = result.get("detail", "Invalid credentials.")
                self._root.after(0, self._on_login_error, msg)  # type: ignore
                return

            # Step 2: Register device (best-effort)
            self._sender.send_immediate(
                "/api/v1/devices/",
                {
                    "employee_id": emp_id,
                    "mac_address": self._system_info.mac_address,
                    "ip_address": self._system_info.local_ip,
                    "device_name": self._system_info.hostname,
                    "device_type": self._detect_device_type(),
                },
            )

            # Step 3: Save identity
            self._buffer.set_config("employee_id", str(emp_id))
            self._buffer.set_config("device_mac", self._system_info.mac_address)
            self._buffer.set_config("hostname", self._system_info.hostname)
            if result.get("full_name"):
                self._buffer.set_config("employee_name", result["full_name"])
            if result.get("employee_code"):
                self._buffer.set_config("employee_code", result["employee_code"])
            if result.get("access_token"):
                self._buffer.set_config("access_token", result["access_token"])

            name = result.get("full_name", f"Employee #{emp_id}")
            self._root.after(0, self._on_login_success, name)  # type: ignore

        except Exception as e:
            logger.error(f"Wizard login error: {e}", exc_info=True)
            self._root.after(0, self._on_login_error, f"Error: {e}")  # type: ignore

    def _on_login_error(self, message: str):
        """Called on main thread after login failure."""
        self._show_error(message)
        self._login_btn.configure(state="normal")

    def _on_login_success(self, name: str):
        """Called on main thread after successful login."""
        self._success = True
        self._build_success_screen(name)

    # --------------------------------------------------
    # Success screen
    # --------------------------------------------------

    def _build_success_screen(self, name: str):
        """Show setup-complete screen."""
        for w in self._root.winfo_children():  # type: ignore
            w.destroy()

        frame = ttk.Frame(self._root, padding=30)  # type: ignore
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="\u2713", font=("", 48), foreground="green").pack(  # type: ignore
            pady=(10, 5)
        )
        ttk.Label(frame, text="Setup Complete!", font=("", 16, "bold")).pack(  # type: ignore
            pady=(0, 10)
        )
        ttk.Label(frame, text=f"Welcome, {name}", font=("", 11)).pack(  # type: ignore
            pady=(0, 20)
        )

        info = ttk.Frame(frame)  # type: ignore
        info.pack(fill="x", pady=(0, 15))
        ttk.Label(info, text=f"Device:  {self._system_info.hostname}").pack(  # type: ignore
            anchor="w"
        )
        ttk.Label(info, text=f"MAC:     {self._system_info.mac_address}").pack(  # type: ignore
            anchor="w"
        )

        ttk.Label(  # type: ignore
            frame,
            text="The agent will now run in the background.\n"
            "You can access it from the system tray.",
            justify="center",
        ).pack(pady=(0, 20))

        self._autostart_var = tk.BooleanVar(value=True)  # type: ignore
        ttk.Checkbutton(  # type: ignore
            frame,
            text="Start automatically on boot",
            variable=self._autostart_var,
        ).pack(pady=(0, 15))

        ttk.Button(frame, text="Done", command=self._on_done).pack()  # type: ignore

    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def _on_done(self):
        """Handle Done button."""
        if self._autostart_var.get():
            try:
                from src.utils.autostart import register_autostart

                register_autostart()
            except Exception:
                pass
        self._root.destroy()  # type: ignore

    def _on_close(self):
        """Handle window X button."""
        self._root.destroy()  # type: ignore

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _show_error(self, msg: str):
        self._status_var.set(msg)
        self._status_label.configure(foreground="red")

    def _show_status(self, msg: str):
        self._status_var.set(msg)
        self._status_label.configure(foreground="#666666")

    @staticmethod
    def _detect_device_type() -> str:
        """Detect laptop vs desktop."""
        try:
            import psutil  # type: ignore

            if psutil.sensors_battery() is not None:
                return "laptop"
        except Exception:
            pass
        return "desktop"