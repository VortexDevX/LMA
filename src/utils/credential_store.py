"""Platform-protected storage for the per-device API credential."""

import base64
import ctypes
import getpass
import logging
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

from src.config import config

logger = logging.getLogger("agent.credentials")

_SERVICE_NAME = "com.vortexdevx.local-monitor-agent.device"
_ACCOUNT_NAME = getpass.getuser() or "LocalMonitorAgent"
_ENTROPY = b"LocalMonitorAgent/device-token/v1"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _make_blob(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _windows_protect(data: bytes) -> bytes:
    source, source_buffer = _make_blob(data)
    entropy, entropy_buffer = _make_blob(_ENTROPY)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    success = crypt32.CryptProtectData(
        ctypes.byref(source),
        "Local Monitor Agent device credential",
        ctypes.byref(entropy),
        None,
        None,
        0,
        ctypes.byref(output),
    )
    _ = source_buffer, entropy_buffer
    if not success:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def _windows_unprotect(data: bytes) -> bytes:
    source, source_buffer = _make_blob(data)
    entropy, entropy_buffer = _make_blob(_ENTROPY)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    success = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        0,
        ctypes.byref(output),
    )
    _ = source_buffer, entropy_buffer
    if not success:
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


class CredentialStore:
    """Store one device token without placing it in SQLite or `.env`."""

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir or config.DATA_DIR
        self._path = self._data_dir / "device-credential.dat"

    def load(self) -> str | None:
        try:
            if sys.platform == "darwin":
                result = subprocess.run(
                    [
                        "/usr/bin/security",
                        "find-generic-password",
                        "-a",
                        _ACCOUNT_NAME,
                        "-s",
                        _SERVICE_NAME,
                        "-w",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                token = result.stdout.strip() if result.returncode == 0 else ""
            elif self._path.exists():
                stored = self._path.read_bytes()
                if sys.platform == "win32":
                    token = _windows_unprotect(base64.b64decode(stored, validate=True)).decode()
                else:
                    token = stored.decode("utf-8")
            else:
                return None

            return token if token.startswith("lma_") else None
        except Exception as exc:
            logger.warning("Could not load device credential: %s", exc)
            return None

    def save(self, token: str) -> None:
        if not token.startswith("lma_") or len(token) < 32:
            raise ValueError("Invalid device credential")

        self._data_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            result = subprocess.run(
                [
                    "/usr/bin/security",
                    "add-generic-password",
                    "-U",
                    "-a",
                    _ACCOUNT_NAME,
                    "-s",
                    _SERVICE_NAME,
                    "-w",
                    token,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise OSError(result.stderr.strip() or "macOS Keychain write failed")
            return

        raw = token.encode("utf-8")
        if sys.platform == "win32":
            raw = base64.b64encode(_windows_protect(raw))

        temporary = self._path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
            if sys.platform != "win32":
                self._path.chmod(0o600)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self) -> None:
        if sys.platform == "darwin":
            subprocess.run(
                [
                    "/usr/bin/security",
                    "delete-generic-password",
                    "-a",
                    _ACCOUNT_NAME,
                    "-s",
                    _SERVICE_NAME,
                ],
                check=False,
                capture_output=True,
                timeout=10,
            )
        self._path.unlink(missing_ok=True)
