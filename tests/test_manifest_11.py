"""Tests for manifest 1.1: shape rules, rollup rules, content hashes, and dataset checks."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from geosquare_v2 import (
    CellDataset,
    CellDatasetError,
    CellDatasetManifest,
    CellDatasetManifestError,
    DomainRegistry,
    read_cell_dataset,
)
from geosquare_v2.cell_metadata import content_sha256, data_file_entry
from geosquare_v2.codec import canonical_to_gid
from test_cell_manifest import _manifest_document


POPULATION = [{"name": "population", "parquet_type": "int64"}]

def _table(profile, values, *, start=0):
    gids = [canonical_to_gid(12, start + index, 0) for index in range(len(values))]
    return pa.table({"gid": pa.array(gids, type=pa.string()), "population": pa.array(list(values), type=pa.int64())})


def _v11_document(profile, table):
    document = _manifest_document(profile)
    document["manifest_version"] = "1.1"
    document["value_fields"][0].update(
        space_aggregation="sum", space_weight=None, null_share=0.0, min_value=10, max_value=20
    )
    document["extent"] = {"bbox_wgs84": None, "compact_set_path": None}
    document["governance"] = {
        "title": "Test dataset",
        "owner": "data team",
        "source_name": "synthetic",
        "license": "internal-test",
        "share_policy": "internal",
        "refresh": "once",
    }
    document["storage"]["data_files"] = [
        data_file_entry(table, POPULATION, path="data/part-00000.parquet")
    ]
    document["provenance"].update(spec_version="2.0", derived_from=[])
    return document


def _registry(profile):
    return DomainRegistry([profile])


def test_v11_manifest_exposes_extent_and_governance(profile):
    table = _table(profile, (10, 20))
    manifest = CellDatasetManifest.from_dict(_v11_document(profile, table), registry=_registry(profile))

    assert manifest.manifest_version == "1.1"
    assert manifest.governance["share_policy"] == "internal"
    assert manifest.extent == {"bbox_wgs84": None, "compact_set_path": None}


def test_v10_manifest_has_no_extent_or_governance(profile):
    manifest = CellDatasetManifest.from_dict(_manifest_document(profile), registry=_registry(profile))

    assert manifest.manifest_version == "1.0"
    assert manifest.extent is None
    assert manifest.governance is None


def test_v11_dataset_round_trips_through_disk(tmp_path, profile):
    table = _table(profile, (10, 20))
    dataset = CellDataset.from_table(table, _v11_document(profile, table), registry=_registry(profile))

    path = dataset.write(tmp_path / "dataset")
    back = read_cell_dataset(path, registry=_registry(profile))

    assert back.manifest.manifest_version == "1.1"
    assert back.num_rows == 2


def test_wrong_content_hash_is_rejected(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["storage"]["data_files"][0]["content_sha256"] = "0" * 64

    with pytest.raises(CellDatasetError, match="content_sha256"):
        CellDataset.from_table(table, document, registry=_registry(profile))


def test_swapped_values_change_the_content_hash(profile):
    # Same multiset of values, so min, max and null share match. Only the row pairing differs.
    declared = _table(profile, (10, 20))
    swapped = _table(profile, (20, 10))
    document = _v11_document(profile, declared)

    with pytest.raises(CellDatasetError, match="content_sha256"):
        CellDataset.from_table(swapped, document, registry=_registry(profile))


def test_content_hash_ignores_row_order(profile):
    forward = _table(profile, (10, 20))
    reverse = forward.take([1, 0])

    assert content_sha256(forward, POPULATION) == content_sha256(reverse, POPULATION)


def test_declared_row_count_must_match_data_files(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["storage"]["data_files"][0]["row_count"] = 3

    with pytest.raises(CellDatasetManifestError, match="hold 3 rows"):
        CellDatasetManifest.from_dict(document, registry=_registry(profile))


def test_declared_null_share_must_match_data(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["value_fields"][0]["null_share"] = 0.5

    with pytest.raises(CellDatasetError, match="null_share"):
        CellDataset.from_table(table, document, registry=_registry(profile))


def test_declared_min_value_must_match_data(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["value_fields"][0]["min_value"] = 9

    with pytest.raises(CellDatasetError, match="min_value"):
        CellDataset.from_table(table, document, registry=_registry(profile))


def test_two_file_dataset_reads_when_each_hash_matches(tmp_path, profile):
    first = _table(profile, (10,), start=0)
    second = _table(profile, (20,), start=1)
    combined = _table(profile, (10, 20))
    document = _v11_document(profile, combined)
    document["storage"]["data_files"] = [
        data_file_entry(first, POPULATION, path="data/part-00000.parquet"),
        data_file_entry(second, POPULATION, path="data/part-00001.parquet"),
    ]
    _write_raw_dataset(tmp_path / "dataset", profile, document, [first, second])

    back = read_cell_dataset(tmp_path / "dataset", registry=_registry(profile))

    assert back.num_rows == 2


def test_two_file_dataset_rejects_a_wrong_file_hash(tmp_path, profile):
    first = _table(profile, (10,), start=0)
    second = _table(profile, (20,), start=1)
    combined = _table(profile, (10, 20))
    document = _v11_document(profile, combined)
    document["storage"]["data_files"] = [
        data_file_entry(first, POPULATION, path="data/part-00000.parquet"),
        {**data_file_entry(second, POPULATION, path="data/part-00001.parquet"), "content_sha256": "1" * 64},
    ]
    _write_raw_dataset(tmp_path / "dataset", profile, document, [first, second])

    with pytest.raises(CellDatasetError, match="content_sha256"):
        read_cell_dataset(tmp_path / "dataset", registry=_registry(profile))


def _write_raw_dataset(root, profile, document, tables):
    """Write a dataset directory with several files, bypassing CellDataset.write."""
    manifest = CellDatasetManifest.from_dict(document, registry=_registry(profile))
    (root / "data").mkdir(parents=True)
    payload = manifest.to_json().encode("utf-8")
    for index, table in enumerate(tables):
        metadata = dict(table.schema.metadata or {})
        metadata[b"geosquare.manifest"] = payload
        pq.write_table(table.replace_schema_metadata(metadata), root / "data" / f"part-{index:05d}.parquet")
    manifest.write(root / "manifest.json")


@pytest.mark.parametrize(
    ("field_update", "message"),
    [
        ({"semantics": "DENSITY", "space_aggregation": "sum", "space_weight": "area"}, "not allowed for semantics"),
        ({"semantics": "DENSITY", "space_aggregation": "weighted_mean", "space_weight": "population"}, "must be 'area'"),
        ({"semantics": "MEASUREMENT", "space_aggregation": "median", "space_weight": "population"}, "must be null"),
        ({"semantics": "RATE", "space_aggregation": "weighted_mean", "space_weight": None}, "is required"),
        ({"semantics": "TOTAL", "space_aggregation": "sum", "space_weight": "population"}, "must be null"),
        ({"logical_type": "range", "semantics": "RANGE", "space_aggregation": "max", "space_weight": None}, "not allowed for semantics"),
    ],
)
def test_space_rules_reject_wrong_combinations(profile, field_update, message):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["value_fields"][0].update(field_update)

    with pytest.raises(CellDatasetManifestError, match=message):
        CellDatasetManifest.from_dict(document, registry=_registry(profile))


def test_median_is_allowed_for_measurement_without_weight(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["value_fields"][0].update(semantics="MEASUREMENT", space_aggregation="median", space_weight=None)

    CellDatasetManifest.from_dict(document, registry=_registry(profile))


@pytest.mark.parametrize(
    ("section", "key", "value", "message"),
    [
        ("governance", "share_policy", "open", "share_policy"),
        ("governance", "refresh", "hourly", "refresh"),
        ("extent", "bbox_wgs84", [0, 0, 200, 1], "WGS84"),
        ("extent", "bbox_wgs84", [1, 0, 0, 1], "WGS84"),
        ("extent", "compact_set_path", "/abs/cells.parquet", "relative"),
    ],
)
def test_extent_and_governance_shape_is_checked(profile, section, key, value, message):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document[section][key] = value

    with pytest.raises(CellDatasetManifestError, match=message):
        CellDatasetManifest.from_dict(document, registry=_registry(profile))


def test_data_file_path_must_be_relative_under_data(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    document["storage"]["data_files"][0]["path"] = "/tmp/part-00000.parquet"

    with pytest.raises(CellDatasetManifestError, match="invalid format"):
        CellDatasetManifest.from_dict(document, registry=_registry(profile))


def test_v11_requires_extent_and_governance(profile):
    table = _table(profile, (10, 20))
    document = _v11_document(profile, table)
    del document["governance"]

    with pytest.raises(CellDatasetManifestError, match="governance"):
        CellDatasetManifest.from_dict(document, registry=_registry(profile))
