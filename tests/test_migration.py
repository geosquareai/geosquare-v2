"""Tests for geosquare_v2.db.MigrationTool."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosquare_v2.db import MigrationTool
from geosquare_v2.errors import ArtifactHashMismatchError, ManifestValidationError
from registry_db_helpers import build_legacy_json_registry


def _build_source(destination: Path) -> Path:
    return build_legacy_json_registry(destination)


def _file_bytes_snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_migrate_writes_expected_domain_count(tmp_path):
    source = _build_source(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    domain_count = MigrationTool(source).migrate(db_path)
    assert domain_count == 2
    assert db_path.is_file()


def test_migrate_creates_destination_parent_directory(tmp_path):
    source = _build_source(tmp_path / "source")
    db_path = tmp_path / "nested" / "dir" / "registry.db"
    MigrationTool(source).migrate(db_path)
    assert db_path.is_file()


def test_migrate_row_counts_match_manifest(tmp_path):
    import sqlite3

    source = _build_source(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    MigrationTool(source).migrate(db_path)
    connection = sqlite3.connect(str(db_path))
    try:
        (domain_count,) = connection.execute("SELECT COUNT(*) FROM domains").fetchone()
        (profile_count,) = connection.execute("SELECT COUNT(*) FROM profiles").fetchone()
        (scale_count,) = connection.execute("SELECT COUNT(*) FROM scale_metadata").fetchone()
        (manifest_count,) = connection.execute("SELECT COUNT(*) FROM manifest").fetchone()
    finally:
        connection.close()
    assert domain_count == 2
    assert profile_count == 2
    assert scale_count == 2
    assert manifest_count == 1


def test_migrate_does_not_mutate_source_files(tmp_path):
    source = _build_source(tmp_path / "source")
    before = _file_bytes_snapshot(source)
    MigrationTool(source).migrate(tmp_path / "registry.db")
    after = _file_bytes_snapshot(source)
    assert before == after


def test_migrate_aborts_without_writing_db_on_missing_profile_file(tmp_path):
    source = _build_source(tmp_path / "source")
    (source / "profiles" / "TS.v2.json").unlink()
    destination = tmp_path / "out" / "registry.db"
    with pytest.raises(ManifestValidationError):
        MigrationTool(source).migrate(destination)
    assert not destination.exists()
    assert not destination.parent.exists() or list(destination.parent.iterdir()) == []


def test_migrate_aborts_without_writing_db_on_hash_mismatch(tmp_path):
    source = _build_source(tmp_path / "source")
    profile_path = source / "profiles" / "TS.v2.json"
    document = json.loads(profile_path.read_text())
    document["name"] = "Tampered"
    profile_path.write_text(json.dumps(document))
    destination = tmp_path / "out" / "registry.db"
    with pytest.raises(ArtifactHashMismatchError):
        MigrationTool(source).migrate(destination)
    assert not destination.exists()


def test_migrate_aborts_on_empty_domains_manifest(tmp_path):
    source = _build_source(tmp_path / "source")
    manifest_path = source / "registry.v2.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["domains"] = []
    manifest_path.write_text(json.dumps(manifest))
    destination = tmp_path / "out" / "registry.db"
    with pytest.raises(ManifestValidationError):
        MigrationTool(source).migrate(destination)
    assert not destination.exists()


def test_migrate_source_left_untouched_after_failed_migration(tmp_path):
    source = _build_source(tmp_path / "source")
    before = _file_bytes_snapshot(source)
    (source / "scale" / "TS_GRID_V2.json").write_bytes(b"not json")
    with pytest.raises(ManifestValidationError):
        MigrationTool(source).migrate(tmp_path / "registry.db")
    after = _file_bytes_snapshot(source)
    before["scale/TS_GRID_V2.json"] = b"not json"
    assert before == after


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(mutated_field=st.sampled_from(["name", "origin_x_m", "reference_epoch"]))
def test_property_migration_preserves_domain_data(tmp_path_factory, mutated_field):
    """Property 1: Migration preserves manifest and domain data.

    Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.7, 2.1, 2.2
    """
    import sqlite3

    tmp_path = tmp_path_factory.mktemp("prop1")
    source = _build_source(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    MigrationTool(source).migrate(db_path)

    manifest = json.loads((source / "registry.v2.json").read_text())
    connection = sqlite3.connect(str(db_path))
    try:
        row = connection.execute(
            "SELECT registry_version, release_status, proj_version_exact, proj_db_sha256 FROM manifest"
        ).fetchone()
        assert row == (
            manifest["registry_version"],
            manifest["release_status"],
            manifest["proj_version_exact"],
            manifest["proj_db_sha256"],
        )
        for entry in manifest["domains"]:
            profile = json.loads((source / entry["profile_file"]).read_text())
            db_row = connection.execute(
                "SELECT name, origin_x_m FROM domains WHERE domain_id = ?", (entry["domain_id"],)
            ).fetchone()
            assert db_row == (profile["name"], profile["origin_x_m"])
    finally:
        connection.close()


@settings(max_examples=10)
@given(st.integers(min_value=1, max_value=1))
def test_property_uniqueness_and_referential_integrity(tmp_path_factory, _unused):
    """Property 2: Domain and profile/scale uniqueness and referential integrity are enforced.

    Validates: Requirements 1.5, 1.6
    """
    import sqlite3

    tmp_path = tmp_path_factory.mktemp("prop2")
    source = _build_source(tmp_path / "source")
    db_path = tmp_path / "registry.db"
    MigrationTool(source).migrate(db_path)

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        codes = [row[0] for row in connection.execute("SELECT domain_code FROM domains")]
        assert len(codes) == len(set(codes))
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO profiles (domain_id, profile_version, crs_authority, crs_wkt2, "
                "equal_area_crs_authority, equal_area_crs_wkt2, min_level, max_level, scale_error_max_pct, "
                "scale_error_method, scale_metadata_sha256, boundary_source_crs, boundary_file, "
                "boundary_sha256, boundary_source) VALUES (999999, 'x','x','x','x','x',0,14,0.0,'x', "
                "'0'||replace(hex(randomblob(31)),'','') ,'x','x','0'||replace(hex(randomblob(31)),'','') ,'x')"
            )
    finally:
        connection.close()


@settings(max_examples=10)
@given(st.integers(min_value=1, max_value=1))
def test_property_migration_never_mutates_source(tmp_path_factory, _unused):
    """Property 3: Migration never mutates its source artifacts.

    Validates: Requirements 2.5
    """
    tmp_path = tmp_path_factory.mktemp("prop3")
    source = _build_source(tmp_path / "source")
    before = _file_bytes_snapshot(source)
    MigrationTool(source).migrate(tmp_path / "registry.db")
    after = _file_bytes_snapshot(source)
    assert before == after


@settings(max_examples=10)
@given(
    scenario=st.sampled_from(["missing_profile", "hash_mismatch", "empty_domains"]),
)
def test_property_migration_aborts_atomically(tmp_path_factory, scenario):
    """Property 4: Migration aborts atomically on invalid or missing input.

    Validates: Requirements 2.3, 2.4, 2.7
    """
    tmp_path = tmp_path_factory.mktemp("prop4")
    source = _build_source(tmp_path / "source")
    destination = tmp_path / "out" / "registry.db"

    if scenario == "missing_profile":
        (source / "profiles" / "TS.v2.json").unlink()
    elif scenario == "hash_mismatch":
        profile_path = source / "profiles" / "TS.v2.json"
        document = json.loads(profile_path.read_text())
        document["name"] = "Tampered"
        profile_path.write_text(json.dumps(document))
    else:
        manifest_path = source / "registry.v2.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["domains"] = []
        manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ManifestValidationError):
        MigrationTool(source).migrate(destination)
    assert not destination.exists()
