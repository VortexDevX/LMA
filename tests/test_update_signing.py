import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src.utils.update_signing import (
    canonical_manifest_payload,
    verify_manifest_signature,
)


def test_signed_release_manifest_verifies_and_tampering_fails():
    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    manifest = {
        "version": "2.0.0",
        "download_url": "https://downloads.example.com/agent.exe",
        "checksum": "a" * 64,
        "release_notes": "Security update",
        "mandatory": True,
    }
    manifest["signature"] = base64.b64encode(
        private_key.sign(canonical_manifest_payload(manifest))
    ).decode("ascii")
    public_key = base64.b64encode(public_raw).decode("ascii")

    assert verify_manifest_signature(manifest, public_key) is True

    manifest["download_url"] = "https://attacker.example.com/agent.exe"
    assert verify_manifest_signature(manifest, public_key) is False
