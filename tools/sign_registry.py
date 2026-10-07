#!/usr/bin/env python3
"""Sign a reviewed Geosquare V2 registry manifest with a local Ed25519 private key."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import rfc8785
from cryptography.hazmat.primitives import serialization


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True, help="PEM private key; never commit it")
    parser.add_argument("--input", type=Path, required=True, help="Reviewed unsigned manifest")
    parser.add_argument("--output", type=Path, required=True, help="Signed manifest output")
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()

    private_key_path = args.private_key.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if private_key_path == repository_root or repository_root in private_key_path.parents:
        raise SystemExit("private key must be stored outside the repository")

    manifest = json.loads(args.input.read_text(encoding="utf-8"))
    if "signature" in manifest:
        raise SystemExit("input manifest must be unsigned")
    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    signature = private_key.sign(rfc8785.dumps(manifest))
    manifest["signature"] = {
        "algorithm": "Ed25519",
        "key_id": args.key_id,
        "canonicalization": "RFC8785",
        "value": base64.b64encode(signature).decode("ascii"),
    }
    args.output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote signed registry manifest: {args.output}")


if __name__ == "__main__":
    main()
