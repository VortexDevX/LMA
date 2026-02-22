"""
Simple API key obfuscation using XOR with machine-specific salt.
Not cryptographically secure — just prevents casual plaintext reading.
"""

import hashlib
import base64
import socket
import uuid
import logging

logger = logging.getLogger("agent.crypto")


def get_machine_salt() -> bytes:
    """Generate a machine-specific salt from hostname and MAC address."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    mac = hex(uuid.getnode())
    raw = f"{hostname}:{mac}:localmonitoragent".encode("utf-8")
    return hashlib.sha256(raw).digest()


def obfuscate(plaintext: str, salt: bytes) -> str:
    """
    Obfuscate a string using XOR with a derived key.
    Returns base64-encoded string.
    """
    if not plaintext:
        return ""

    key = hashlib.pbkdf2_hmac("sha256", salt, b"lma_obfuscate_v1", 10000)
    data = plaintext.encode("utf-8")
    obfuscated = bytes(d ^ key[i % len(key)] for i, d in enumerate(data))
    return base64.b64encode(obfuscated).decode("ascii")


def deobfuscate(obfuscated: str, salt: bytes) -> str:
    """
    Reverse obfuscation. Returns original plaintext.
    Raises ValueError on invalid input.
    """
    if not obfuscated:
        return ""

    key = hashlib.pbkdf2_hmac("sha256", salt, b"lma_obfuscate_v1", 10000)
    data = base64.b64decode(obfuscated)
    plaintext_bytes = bytes(d ^ key[i % len(key)] for i, d in enumerate(data))
    return plaintext_bytes.decode("utf-8")