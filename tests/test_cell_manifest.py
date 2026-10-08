"""Tests for the cell-dataset manifest contract."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from geosquare_v2 import CellDatasetManifest, CellDatasetManifestError, DomainRegistry


def _manifest_document(profile, *, dataset_type: str = "cell_values") -> dict:
    return {
        "manifest_version": "1.0",
        "dataset_type": dataset_type,
        "grid_system": "geosquare",
        "grid_version": "v2",
        "domain_code": profile.domain_code,
        "domain_id": profile.domain_id,
        "level": 12,
        "profile_version": profile.profile_version,
        "registry_version": "2.0.0",
        "value_fields": [
            {
                "name": "population",
                "parquet_type": "int64",
                "logical_type": "numeric",
                "semantics": "TOTAL",
                "unit": "persons",
                "nullable": False,
                "aggregation_rule": "weighted_sum",
            }
        ],
        "identity": {
            "gid_column": "gid",
            "uri_prefix": f"geosquare:v2:{profile.domain_code}:",
            "packed_id_column": None,
            "x_idx_column": None,
            "y_idx_column": None,
            "unique_gid": dataset_type == "cell_values",
        },
        "coverage": {
            "assignment_method": "point_to_cell",
            "boundary_policy": "COVERS_POINT",
            "boundary_sha256": profile.boundary_sha256,
            "coverage_mode": None,
            "min_coverage": None,
            "length_mode": None,
        },
        "source": {
            "format": "parquet",
            "geometry_type": "Point",
            "source_crs": "EPSG:4326",
            "source_id_column": "asset_id",
            "source_dataset": None,
            "source_row_count": 2,
        },
        "storage": {
            "parquet_compression": "zstd",
            "geometry_column": None,
            "geometry_format": None,
            "geometry_crs": None,
            "partitioning": [],
            "sorted_by": ["gid"],
            "row_count": 2,
            "unique_cell_count": 2 if dataset_type == "cell_values" else 1,
        },
        "provenance": {
            "created_at": "2026-10-01T00:00:00Z",
            "created_by": "test",
            "generator": "test_manifest",
            "aggregation_rule": "weighted_sum",
            "value_semantics": "TOTAL",
            "notes": None,
        },
    }


def test_valid_manifest_round_trips_canonically(profile, tmp_path):
    document = _manifest_document(profile)
    registry = DomainRegistry([profile])

    manifest = CellDatasetManifest.from_dict(document, registry=registry, columns=["gid", "population"])

    assert manifest.domain_code == "TS"
    assert manifest.domain_id == 7
    assert manifest.level == 12
    assert manifest.value_field_names == ("population",)
    assert manifest.is_queryable is False
    assert manifest.reserved_columns >= {"domain", "level", "gid", "uri"}
    assert json.loads(manifest.to_json()) == document

    output = tmp_path / "manifest.json"
    manifest.write(output)
    assert CellDatasetManifest.from_file(output, registry=registry, columns=["gid", "population"]).to_dict() == document


def test_manifest_defensively_copies_input_and_output(profile):
    document = _manifest_document(profile)
    manifest = CellDatasetManifest.from_dict(document)

    document["domain_code"] = "XX"
    output = manifest.to_dict()
    output["domain_code"] = "YY"

    assert manifest.domain_code == "TS"
    assert manifest.to_dict()["domain_code"] == "TS"


def test_packaged_schema_is_available_and_strict():
    schema = CellDatasetManifest.schema()

    assert schema["$id"].endswith("cell-dataset-manifest-v1.schema.json")
    assert "domain" in schema["$defs"]["valueField"]["properties"]["name"]["not"]["enum"]
    assert "level" in schema["$defs"]["valueField"]["properties"]["name"]["not"]["enum"]


def test_queryable_identity_requires_all_query_columns(profile):
    document = _manifest_document(profile)
    document["identity"]["packed_id_column"] = "packed_id"

    with pytest.raises(CellDatasetManifestError, match="declared together"):
        CellDatasetManifest.from_dict(document)


def test_queryable_manifest_validates_declared_columns(profile):
    document = _manifest_document(profile)
    document["identity"].update(
        {
            "packed_id_column": "packed_id",
            "x_idx_column": "x_idx",
            "y_idx_column": "y_idx",
        }
    )
    manifest = CellDatasetManifest.from_dict(document)

    assert manifest.is_queryable is True
    with pytest.raises(CellDatasetManifestError, match="declared column is missing"):
        manifest.validate_columns(["gid", "population", "packed_id", "x_idx"])
    manifest.validate_columns(["gid", "population", "packed_id", "x_idx", "y_idx"])


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("manifest_version", "2.0", "manifest_version"),
        ("grid_system", "other", "grid_system"),
        ("domain_code", "ts", "domain_code"),
        ("domain_id", True, "domain_id"),
        ("level", 15, "level"),
    ],
)
def test_invalid_top_level_values_are_rejected(profile, path, value, message):
    document = _manifest_document(profile)
    document[path] = value

    with pytest.raises(CellDatasetManifestError, match=message):
        CellDatasetManifest.from_dict(document)


def test_missing_and_unknown_fields_are_rejected(profile):
    missing = _manifest_document(profile)
    del missing["provenance"]
    with pytest.raises(CellDatasetManifestError, match="missing required field"):
        CellDatasetManifest.from_dict(missing)

    unknown = _manifest_document(profile)
    unknown["unexpected"] = True
    with pytest.raises(CellDatasetManifestError, match="unknown field"):
        CellDatasetManifest.from_dict(unknown)


def test_reserved_and_duplicate_value_fields_are_rejected(profile):
    reserved = _manifest_document(profile)
    reserved["value_fields"][0]["name"] = "domain"
    with pytest.raises(CellDatasetManifestError, match="reserved column"):
        CellDatasetManifest.from_dict(reserved)

    duplicate = _manifest_document(profile)
    duplicate["value_fields"].append(deepcopy(duplicate["value_fields"][0]))
    with pytest.raises(CellDatasetManifestError, match="duplicates value field"):
        CellDatasetManifest.from_dict(duplicate)


def test_logical_type_and_semantics_must_agree(profile):
    document = _manifest_document(profile)
    document["value_fields"][0]["logical_type"] = "categorical"

    with pytest.raises(CellDatasetManifestError, match="incompatible"):
        CellDatasetManifest.from_dict(document)


def test_cell_values_must_declare_unique_gids(profile):
    document = _manifest_document(profile)
    document["identity"]["unique_gid"] = False

    with pytest.raises(CellDatasetManifestError, match="must be true"):
        CellDatasetManifest.from_dict(document)


def test_contributions_allow_repeated_gids_but_require_source_provenance(profile):
    document = _manifest_document(profile, dataset_type="cell_contributions")
    manifest = CellDatasetManifest.from_dict(document)

    with pytest.raises(CellDatasetManifestError, match="source_id or source_row"):
        manifest.validate_columns(["gid", "population"])
    manifest.validate_columns(["gid", "population", "source_id"])


def test_storage_geometry_and_count_rules_are_rejected(profile):
    geometry = _manifest_document(profile)
    geometry["storage"]["geometry_column"] = "geometry_wkb"
    with pytest.raises(CellDatasetManifestError, match="requires geometry_format"):
        CellDatasetManifest.from_dict(geometry)

    counts = _manifest_document(profile)
    counts["storage"]["unique_cell_count"] = 1
    with pytest.raises(CellDatasetManifestError, match="must equal"):
        CellDatasetManifest.from_dict(counts)


def test_registry_identity_and_boundary_hash_are_validated(profile):
    registry = DomainRegistry([profile])

    wrong_id = _manifest_document(profile)
    wrong_id["domain_id"] = 8
    with pytest.raises(CellDatasetManifestError, match="does not match trusted"):
        CellDatasetManifest.from_dict(wrong_id, registry=registry)

    wrong_version = _manifest_document(profile)
    wrong_version["profile_version"] = "other"
    with pytest.raises(CellDatasetManifestError, match="does not match trusted profile"):
        CellDatasetManifest.from_dict(wrong_version, registry=registry)

    wrong_boundary = _manifest_document(profile)
    wrong_boundary["coverage"]["boundary_sha256"] = "2" * 64
    with pytest.raises(CellDatasetManifestError, match="trusted profile boundary hash"):
        CellDatasetManifest.from_dict(wrong_boundary, registry=registry)


def test_unknown_domain_and_invalid_json_are_rejected(profile):
    document = _manifest_document(profile)
    document["domain_code"] = "ZZ"
    document["identity"]["uri_prefix"] = "geosquare:v2:ZZ:"

    with pytest.raises(CellDatasetManifestError, match="not present in the trusted registry"):
        CellDatasetManifest.from_dict(document, registry=DomainRegistry([profile]))

    with pytest.raises(CellDatasetManifestError, match="invalid JSON"):
        CellDatasetManifest.from_json("not-json")
