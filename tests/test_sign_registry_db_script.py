"""Tests for tools/sign_registry_db.py."""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from hypothesis import given, settings
from hypothesis import strategies as st

from geosquare_v2.db import MigrationTool
from registry_db_helpers import build_legacy_json_registry

SCRIPT_PATH = Path(__file__).parents[1] / "tools" / "sign_registry_db.py"


def _write_private_key_pem(path: Path) -> ed25519.Ed25519PrivateKey:
    private_key = ed25519.Ed25519PrivateKey.generate()
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path.write_bytes(pem_bytes)
    return private_key


def test_missing_db_file_aborts_without_writing_sig(tmp_path):
    private_key_path = tmp_path / "key.pem"
    _write_private_key_pem(private_key_path)
    output_path = tmp_path / "registry.db.sig"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--private-key",
            str(private_key_path),
            "--db",
            str(tmp_path / "nonexistent.db"),
            "--output",
            str(output_path),
            "--key-id",
            "test-key",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not output_path.exists()


def test_signing_script_produces_valid_signature_and_does_not_modify_db(tmp_path):
    source = build_legacy_json_registry(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    MigrationTool(source).migrate(db_path)
    before = db_path.read_bytes()

    private_key_path = tmp_path / "key.pem"
    private_key = _write_private_key_pem(private_key_path)
    output_path = tmp_path / "registry.db.sig"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--private-key",
            str(private_key_path),
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--key-id",
            "test-key",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert db_path.read_bytes() == before

    sidecar = json.loads(output_path.read_text())
    assert sidecar["algorithm"] == "Ed25519"
    assert sidecar["key_id"] == "test-key"
    digest = hashlib.sha256(before).digest()
    assert sidecar["sha256"] == digest.hex()
    public_key = private_key.public_key()
    public_key.verify(base64.b64decode(sidecar["value"]), digest)


@settings(max_examples=10, deadline=None)
@given(st.integers(min_value=1, max_value=1))
def test_property_sign_round_trips_and_preserves_db_bytes(tmp_path_factory, _unused):
    """Property 5: Signing round-trips through verification, and never mutates the database file.

    Validates: Requirements 3.1, 3.2, 3.3, 3.6
    """
    tmp_path = tmp_path_factory.mktemp("prop5")
    source = build_legacy_json_registry(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    MigrationTool(source).migrate(db_path)
    before = db_path.read_bytes()

    private_key_path = tmp_path / "key.pem"
    private_key = _write_private_key_pem(private_key_path)
    output_path = tmp_path / "registry.db.sig"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--private-key",
            str(private_key_path),
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--key-id",
            "prop-key",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert db_path.read_bytes() == before

    sidecar = json.loads(output_path.read_text())
    digest = hashlib.sha256(before).digest()
    assert sidecar["sha256"] == digest.hex()
    private_key.public_key().verify(base64.b64decode(sidecar["value"]), digest)
