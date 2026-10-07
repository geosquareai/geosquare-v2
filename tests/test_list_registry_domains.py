"""Tests for geosquare_v2.db.list_registry_domains."""

from __future__ import annotations

import pytest

from geosquare_v2.db import MigrationTool, RegistryDomainSummary, list_registry_domains
from geosquare_v2.errors import ManifestValidationError
from registry_db_helpers import build_legacy_json_registry


def test_list_registry_domains_from_directory(tmp_path):
    source = build_legacy_json_registry(tmp_path / "source")
    db_path = tmp_path / "db" / "registry.db"
    MigrationTool(source).migrate(db_path)

    domains = list_registry_domains(db_path.parent)
    assert domains == (
        RegistryDomainSummary(
            domain_id=1, domain_code="TS", name="Test Domain TS", profile_version="test-1", min_level=0, max_level=14
        ),
        RegistryDomainSummary(
            domain_id=2, domain_code="TX", name="Test Domain TX", profile_version="test-1", min_level=0, max_level=14
        ),
    )


def test_list_registry_domains_from_explicit_file_path(tmp_path):
    source = build_legacy_json_registry(tmp_path / "source")
    db_path = tmp_path / "db" / "registry.db"
    MigrationTool(source).migrate(db_path)

    domains = list_registry_domains(db_path)
    assert [d.domain_code for d in domains] == ["TS", "TX"]


def test_list_registry_domains_does_not_require_a_signature(tmp_path):
    # Unlike DbRegistryLoader.load(), listing domains is metadata-only and works even
    # without a registry.db.sig sidecar file being present.
    source = build_legacy_json_registry(tmp_path / "source")
    db_path = tmp_path / "db" / "registry.db"
    MigrationTool(source).migrate(db_path)
    assert not (db_path.parent / "registry.db.sig").exists()

    domains = list_registry_domains(db_path.parent)
    assert len(domains) == 2


def test_list_registry_domains_missing_database_raises(tmp_path):
    with pytest.raises(ManifestValidationError):
        list_registry_domains(tmp_path)


def test_list_registry_domains_corrupt_file_raises(tmp_path):
    bogus = tmp_path / "registry.db"
    bogus.write_bytes(b"not a sqlite database")
    with pytest.raises(ManifestValidationError):
        list_registry_domains(tmp_path)
