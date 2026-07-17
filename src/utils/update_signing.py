"""Canonical Ed25519 signing and verification for agent release manifests."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNED_FIELDS = (
    "version",
    "download_url",
    "checksum",
    "release_notes",
    "mandatory",
)


def canonical_manifest_payload(manifest: dict[str, Any]) -> bytes:
    payload = {
        "checksum": str(manifest.get("checksum", "")).strip().lower(),
        "download_url": str(manifest.get("download_url", "")).strip(),
        "mandatory": bool(manifest.get("mandatory", False)),
        "release_notes": str(manifest.get("release_notes", "")),
        "version": str(manifest.get("version", "")).strip(),
    }
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def verify_manifest_signature(manifest: dict[str, Any], public_key_b64: str) -> bool:
    if not public_key_b64 or not manifest.get("signature"):
        return False
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_b64, validate=True)
        )
        signature = base64.b64decode(str(manifest["signature"]), validate=True)
        public_key.verify(signature, canonical_manifest_payload(manifest))
        return True
    except (ValueError, TypeError, binascii.Error, InvalidSignature):
        return False
