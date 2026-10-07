#!/usr/bin/env python3
"""Sign a built Geosquare V2 registry database with a local Ed25519 private key.

Unlike ``sign_registry.py`` (which canonicalizes and signs a JSON manifest), this script
signs the raw SHA-256 digest of a SQLite database file's bytes, since there is no JSON
document to canonicalize. The resulting signature is written to a detached sidecar file.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization

DEFAULT_DB = Path(__file__).resolve().parents[1] / "src" / "geosquare_v2" / "db" / "registry.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "src" / "geosquare_v2" / "db" / "registry.db.sig"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True, help="PEM private key; never commit it")
    parser.add_argument(
        "--db", type=Path, default=DEFAULT_DB, help=f"Built registry database file (default: {DEFAULT_DB})"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Signature sidecar output (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()

    private_key_path = args.private_key.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if private_key_path == repository_root or repository_root in private_key_path.parents:
        raise SystemExit("private key must be stored outside the repository")

    if not args.db.is_file():
        raise SystemExit(f"registry database not found: {args.db}")

    db_bytes = args.db.read_bytes()
    digest = hashlib.sha256(db_bytes).digest()

    private_key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    signature = private_key.sign(digest)

    sidecar = {
        "algorithm": "Ed25519",
        "key_id": args.key_id,
        "value": base64.b64encode(signature).decode("ascii"),
        "sha256": digest.hex(),
    }
    args.output.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote registry database signature: {args.output}")


if __name__ == "__main__":
    main()
