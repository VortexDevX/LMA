#!/usr/bin/env python3
"""Generate Ed25519 release keys or sign a local-agent update manifest."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from src.utils.update_signing import canonical_manifest_payload  # noqa: E402


def _write_secret(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="ascii")
    if os.name != "nt":
        path.chmod(0o600)


def generate_keys(private_path: Path, public_path: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    _write_secret(private_path, base64.b64encode(private_raw).decode("ascii"))
    if public_path.exists():
        private_path.unlink(missing_ok=True)
        raise FileExistsError(f"refusing to overwrite {public_path}")
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        base64.b64encode(public_raw).decode("ascii") + "\n", encoding="ascii"
    )


def sign_manifest(private_path: Path, manifest_path: Path, output_path: Path) -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(private_path.read_text(encoding="ascii").strip(), validate=True)
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    signature = private_key.sign(canonical_manifest_payload(manifest))
    manifest["signature"] = base64.b64encode(signature).decode("ascii")
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-keys")
    generate.add_argument("--private", required=True, type=Path)
    generate.add_argument("--public", required=True, type=Path)
    sign = commands.add_parser("sign")
    sign.add_argument("--private", required=True, type=Path)
    sign.add_argument("--manifest", required=True, type=Path)
    sign.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "generate-keys":
            generate_keys(args.private, args.public)
            print(f"Private key: {args.private} (keep offline and secret)")
            print(f"Public key: {args.public}")
        else:
            sign_manifest(args.private, args.manifest, args.output)
            print(f"Signed manifest: {args.output}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
