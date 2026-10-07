"""Tests for geosquare_v2.db.DbRegistryLoader."""

from __future__ import annotations

import base64
import json

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosquare_v2.db import DbRegistryLoader
from geosquare_v2.errors import (
    ArtifactHashMismatchError,
    ManifestSignatureError,
    ManifestValidationError,
)
from registry_db_helpers import build_legacy_json_registry, build_signed_registry_db, sign_database


def _build_source(tmp_path):
    return build_legacy_json_registry(tmp_path / "source")


def test_load_succeeds_with_valid_signature(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    registry = DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()
    assert len(registry) == 2
    assert "TS" in registry
    assert "TX" in registry


def test_missing_signature_file_raises_manifest_validation_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (db_dir / "registry.db.sig").unlink()
    with pytest.raises(ManifestValidationError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


def test_untrusted_key_id_raises_manifest_signature_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, _trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    with pytest.raises(ManifestSignatureError):
        DbRegistryLoader({}, db_dir, boundary_root=source).load()


def test_tampered_db_bytes_raises_manifest_signature_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    db_path = db_dir / "registry.db"
    data = bytearray(db_path.read_bytes())
    data[-1] ^= 0xFF
    db_path.write_bytes(bytes(data))
    with pytest.raises(ManifestSignatureError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


def test_tampered_signature_value_raises_manifest_signature_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    sig_path = db_dir / "registry.db.sig"
    sidecar = json.loads(sig_path.read_text())
    tampered = bytearray(base64.b64decode(sidecar["value"]))
    tampered[0] ^= 0xFF
    sidecar["value"] = base64.b64encode(bytes(tampered)).decode("ascii")
    sig_path.write_text(json.dumps(sidecar))
    with pytest.raises(ManifestSignatureError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


def test_boundary_hash_mismatch_raises_artifact_hash_mismatch_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (source / "boundaries" / "TS.geojson").write_text('{"type": "Polygon", "coordinates": []}')
    with pytest.raises(ArtifactHashMismatchError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source, verify_boundaries=True).load()


def test_missing_boundary_file_raises_artifact_hash_mismatch_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (source / "boundaries" / "TS.geojson").unlink()
    with pytest.raises(ArtifactHashMismatchError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source, verify_boundaries=True).load()


def test_load_succeeds_without_boundary_files_when_verification_disabled(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)

    # Simulate shipping just the database, without any boundaries/ directory at all.
    isolated_db_dir = tmp_path / "delivered"
    isolated_db_dir.mkdir()
    (isolated_db_dir / "registry.db").write_bytes((db_dir / "registry.db").read_bytes())
    (isolated_db_dir / "registry.db.sig").write_bytes((db_dir / "registry.db.sig").read_bytes())

    registry = DbRegistryLoader(trusted_keys, isolated_db_dir, verify_boundaries=False).load()
    assert len(registry) == 2
    assert "TS" in registry
    assert "TX" in registry


def test_load_without_boundary_verification_ignores_tampered_boundary_file(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (source / "boundaries" / "TS.geojson").unlink()  # even missing entirely is fine
    registry = DbRegistryLoader(trusted_keys, db_dir, verify_boundaries=False).load()
    assert len(registry) == 2


def test_directory_with_only_legacy_files_raises_manifest_validation_error(tmp_path):
    source = _build_source(tmp_path)
    with pytest.raises(ManifestValidationError):
        DbRegistryLoader({}, source, boundary_root=source).load()


def test_malformed_signature_sidecar_raises_manifest_validation_error(tmp_path):
    source = _build_source(tmp_path)
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (db_dir / "registry.db.sig").write_text("not json")
    with pytest.raises(ManifestValidationError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


def test_schema_consistency_gap_raises_manifest_validation_error(tmp_path):
    import sqlite3

    source = _build_source(tmp_path)
    db_dir, trusted_keys, keypair = build_signed_registry_db(tmp_path, source_root=source)
    db_path = db_dir / "registry.db"
    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM profiles WHERE domain_id = 1")
        connection.commit()
    finally:
        connection.close()
    # Re-sign since the db bytes changed after the row deletion.
    sign_database(db_path, db_dir / "registry.db.sig", keypair)
    with pytest.raises(ManifestValidationError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@settings(max_examples=15)
@given(
    scenario=st.sampled_from(["missing_sig", "untrusted_key", "tampered_db", "tampered_sig"]),
)
def test_property_verification_fails_closed(tmp_path_factory, scenario):
    """Property 6: Verification fails closed on any tampering, wrong key, or missing signature.

    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
    """
    tmp_path = tmp_path_factory.mktemp("prop6")
    source = build_legacy_json_registry(tmp_path / "source")
    db_dir, trusted_keys, keypair = build_signed_registry_db(tmp_path, source_root=source)

    if scenario == "missing_sig":
        (db_dir / "registry.db.sig").unlink()
        expected_exc = ManifestValidationError
        keys = trusted_keys
    elif scenario == "untrusted_key":
        expected_exc = ManifestSignatureError
        keys = {}
    elif scenario == "tampered_db":
        db_path = db_dir / "registry.db"
        data = bytearray(db_path.read_bytes())
        data[0] ^= 0xFF
        db_path.write_bytes(bytes(data))
        expected_exc = ManifestSignatureError
        keys = trusted_keys
    else:
        sig_path = db_dir / "registry.db.sig"
        sidecar = json.loads(sig_path.read_text())
        tampered = bytearray(base64.b64decode(sidecar["value"]))
        tampered[-1] ^= 0xFF
        sidecar["value"] = base64.b64encode(bytes(tampered)).decode("ascii")
        sig_path.write_text(json.dumps(sidecar))
        expected_exc = ManifestSignatureError
        keys = trusted_keys

    with pytest.raises(expected_exc):
        DbRegistryLoader(keys, db_dir, boundary_root=source).load()


@settings(max_examples=10)
@given(domain_code=st.sampled_from(["TS", "TX"]))
def test_property_boundary_hash_gates_construction(tmp_path_factory, domain_code):
    """Property 8: Boundary hash verification gates registry construction.

    Validates: Requirements 4.7, 4.8
    """
    tmp_path = tmp_path_factory.mktemp("prop8")
    source = build_legacy_json_registry(tmp_path / "source")
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    (source / "boundaries" / f"{domain_code}.geojson").write_bytes(b"tampered bytes")
    with pytest.raises(ArtifactHashMismatchError):
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source, verify_boundaries=True).load()


def test_property_proj_verification_parity(tmp_path):
    """Property 9: PROJ resource verification behaves identically to the JSON-backed loader.

    Validates: Requirements 4.9
    """
    import pyproj

    source = build_legacy_json_registry(tmp_path / "source")
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    manifest = json.loads((source / "registry.v2.json").read_text())
    installed_version_matches = pyproj.proj_version_str == manifest["proj_version_exact"]

    if installed_version_matches:
        # Same PROJ version as the signed manifest: loading should succeed (no PROJ error).
        DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()
    else:
        from geosquare_v2.errors import ProjResourceVerificationError

        with pytest.raises(ProjResourceVerificationError):
            DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()


def test_property_missing_database_fails_validation(tmp_path):
    """Property 10: Loading a directory without a database fails validation.

    Validates: Requirements 7.4
    """
    source = build_legacy_json_registry(tmp_path / "source")
    with pytest.raises(ManifestValidationError):
        DbRegistryLoader({}, source, boundary_root=source).load()
