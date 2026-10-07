"""End-to-end migration -> sign -> load round-trip test."""

from __future__ import annotations

from dataclasses import fields

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from geosquare_v2.db import DbRegistryLoader
from geosquare_v2.errors import UnknownDomainError
from registry_db_helpers import build_legacy_json_registry, build_signed_registry_db


@settings(max_examples=5, deadline=None)
@given(domain_code=st.sampled_from(["TS", "TX"]))
def test_property_migration_then_load_round_trip_preserves_profile_data(tmp_path_factory, domain_code):
    """Property 7: End-to-end migration-then-load round-trip preserves profile data and the
    DomainRegistry API.

    Validates: Requirements 4.6, 7.1, 7.2
    """
    tmp_path = tmp_path_factory.mktemp("prop7")
    source = build_legacy_json_registry(tmp_path / "source")
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    registry = DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()

    profile = registry.get(domain_code)
    assert registry.get_by_id(profile.domain_id).domain_code == domain_code

    # Cross-check every persisted field round-trips against the synthetic JSON source,
    # except the two fields whose semantics intentionally change per design.md:
    #   - scale_metadata_sha256: now hashes a canonical row re-serialization, not a file.
    #   - scale_error_evaluation_metadata: now a synthesized "db:scale_metadata:<code>"
    #     descriptor, since there is no longer a scale/*.json file to point at.
    import json

    profile_document = json.loads((source / "profiles" / f"{domain_code}.v2.json").read_text())
    for field in fields(profile):
        if field.name in {"scale_metadata_sha256", "scale_error_evaluation_metadata", "boundary_file"}:
            continue
        if field.name in profile_document:
            assert getattr(profile, field.name) == profile_document[field.name], field.name


def test_domain_registry_api_surface_unchanged(tmp_path):
    source = build_legacy_json_registry(tmp_path / "source")
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source)
    registry = DbRegistryLoader(trusted_keys, db_dir, boundary_root=source).load()

    assert len(registry) == 2
    assert "TS" in registry
    assert "NOPE" not in registry
    assert isinstance(registry.profiles(), tuple)
    assert len(registry.profiles()) == 2

    with pytest.raises(UnknownDomainError):
        registry.get("NOPE")
    with pytest.raises(UnknownDomainError):
        registry.get_by_id(9999)
