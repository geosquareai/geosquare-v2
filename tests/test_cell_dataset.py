"""Tests for local GeoSquare cell-dataset Parquet storage."""

from __future__ import annotations

import json

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
    write_cell_dataset,
)
from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.packing import pack_int64
from test_cell_manifest import _manifest_document


_MANIFEST_METADATA_KEY = b"geosquare.manifest"


def _registry(profile):
    return DomainRegistry([profile])


def _table_rows():
    first_gid = canonical_to_gid(12, 0, 0)
    second_gid = canonical_to_gid(12, 1, 0)
    return first_gid, second_gid


def _manifest(profile, *, dataset_type="cell_values", queryable=False):
    document = _manifest_document(profile, dataset_type=dataset_type)
    if queryable:
        document["identity"].update(
            {
                "packed_id_column": "packed_id",
                "x_idx_column": "x_idx",
                "y_idx_column": "y_idx",
            }
        )
        document["storage"]["sorted_by"] = ["x_idx", "y_idx"]
    return CellDatasetManifest.from_dict(document, registry=_registry(profile))


def test_compact_dataset_round_trip_writes_sidecar_and_embedded_manifest(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    table = pa.table(
        {
            "gid": pa.array([first_gid, second_gid], type=pa.string()),
            "population": pa.array([10, 20], type=pa.int64()),
        }
    )
    manifest = _manifest(profile)
    destination = tmp_path / "compact"

    dataset = CellDataset.from_table(table, manifest, registry=_registry(profile))
    assert dataset.num_rows == 2
    assert dataset.column_names == ("gid", "population")
    dataset.write(destination)

    sidecar = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert sidecar == manifest.to_dict()
    parquet_path = destination / "data" / "part-00000.parquet"
    metadata = pq.read_metadata(parquet_path).metadata
    assert json.loads(metadata[_MANIFEST_METADATA_KEY]) == manifest.to_dict()

    loaded = read_cell_dataset(destination, registry=_registry(profile))
    assert loaded.manifest.to_dict() == manifest.to_dict()
    assert loaded.table.to_pydict() == table.to_pydict()


def test_queryable_dataset_round_trip_validates_packed_and_xy_columns(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    table = pa.table(
        {
            "gid": pa.array([first_gid, second_gid], type=pa.string()),
            "packed_id": pa.array([pack_int64(7, 12, 0, 0), pack_int64(7, 12, 1, 0)], type=pa.int64()),
            "x_idx": pa.array([0, 1], type=pa.int64()),
            "y_idx": pa.array([0, 0], type=pa.int64()),
            "population": pa.array([10, 20], type=pa.int64()),
        }
    )
    dataset = CellDataset.from_table(table, _manifest(profile, queryable=True), registry=_registry(profile))
    destination = dataset.write(tmp_path / "queryable")

    loaded = CellDataset.read(destination, registry=_registry(profile))
    assert loaded.manifest.is_queryable is True
    assert loaded.table.to_pydict() == table.to_pydict()


def test_contribution_dataset_allows_repeated_gids_and_validates_ratios(tmp_path, profile):
    first_gid, _ = _table_rows()
    table = pa.table(
        {
            "source_id": pa.array(["parcel-1", "parcel-1"], type=pa.string()),
            "gid": pa.array([first_gid, first_gid], type=pa.string()),
            "coverage_ratio": pa.array([0.25, 0.75], type=pa.float64()),
            "population": pa.array([100, 100], type=pa.int64()),
        }
    )
    dataset = CellDataset.from_table(
        table,
        _manifest(profile, dataset_type="cell_contributions"),
        registry=_registry(profile),
    )
    dataset.write(tmp_path / "contributions")
    assert read_cell_dataset(tmp_path / "contributions", registry=_registry(profile)).num_rows == 2


def test_raw_table_convenience_writer_requires_manifest_and_reads_back(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    table = pa.table(
        {
            "gid": [first_gid, second_gid],
            "population": pa.array([10, 20], type=pa.int64()),
        }
    )
    destination = tmp_path / "raw"

    with pytest.raises(ValueError, match="manifest is required"):
        write_cell_dataset(table, destination)
    write_cell_dataset(table, destination, manifest=_manifest(profile), registry=_registry(profile))
    assert read_cell_dataset(destination, registry=_registry(profile)).num_rows == 2


def test_sidecar_and_embedded_manifests_must_match(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    table = pa.table({"gid": [first_gid, second_gid], "population": pa.array([10, 20], type=pa.int64())})
    destination = CellDataset.from_table(table, _manifest(profile), registry=_registry(profile)).write(tmp_path / "mismatch")
    sidecar_path = destination / "manifest.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar["provenance"]["notes"] = "changed after writing"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

    with pytest.raises(CellDatasetError, match="does not match"):
        CellDataset.read(destination, registry=_registry(profile))


def test_missing_embedded_manifest_is_rejected(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    destination = tmp_path / "missing-metadata"
    destination.mkdir()
    (destination / "data").mkdir()
    _manifest(profile).write(destination / "manifest.json")
    pq.write_table(pa.table({"gid": [first_gid, second_gid], "population": [10, 20]}), destination / "data" / "part-00000.parquet")

    with pytest.raises(CellDatasetError, match="missing geosquare.manifest"):
        CellDataset.read(destination, registry=_registry(profile))


def test_schema_rejects_undeclared_columns_and_wrong_value_types(profile):
    first_gid, second_gid = _table_rows()
    manifest = _manifest(profile)
    with pytest.raises(CellDatasetError, match="undeclared column"):
        CellDataset.from_table(
            pa.table(
                {
                    "gid": [first_gid, second_gid],
                    "population": pa.array([10, 20], type=pa.int64()),
                    "unexpected": [True, False],
                }
            ),
            manifest,
            registry=_registry(profile),
        )

    with pytest.raises(CellDatasetError, match="does not match declared type"):
        CellDataset.from_table(
            pa.table({"gid": [first_gid, second_gid], "population": ["ten", "twenty"]}),
            manifest,
            registry=_registry(profile),
        )


def test_invalid_gid_level_and_duplicate_values_are_rejected(profile):
    manifest = _manifest(profile)
    with pytest.raises(CellDatasetError, match=r"gid\[0\].*invalid"):
        CellDataset.from_table(
            pa.table({"gid": ["not-a-gid", "not-a-gid"], "population": pa.array([10, 20], type=pa.int64())}),
            manifest,
            registry=_registry(profile),
        )

    first_gid, _ = _table_rows()
    with pytest.raises(CellDatasetError, match="duplicate"):
        CellDataset.from_table(
            pa.table({"gid": [first_gid, first_gid], "population": pa.array([10, 20], type=pa.int64())}),
            manifest,
            registry=_registry(profile),
        )


def test_mismatched_packed_identity_is_rejected(profile):
    first_gid, second_gid = _table_rows()
    table = pa.table(
        {
            "gid": [first_gid, second_gid],
            "packed_id": pa.array([pack_int64(7, 12, 0, 0), pack_int64(7, 12, 2, 0)], type=pa.int64()),
            "x_idx": pa.array([0, 1], type=pa.int64()),
            "y_idx": pa.array([0, 0], type=pa.int64()),
            "population": pa.array([10, 20], type=pa.int64()),
        }
    )
    with pytest.raises(CellDatasetError, match=r"packed_id\[1\].*does not match"):
        CellDataset.from_table(table, _manifest(profile, queryable=True), registry=_registry(profile))


def test_ratio_bounds_and_non_nullable_values_are_rejected(profile):
    first_gid, _ = _table_rows()
    contribution_manifest = _manifest(profile, dataset_type="cell_contributions")
    contribution_document = contribution_manifest.to_dict()
    contribution_document["storage"]["row_count"] = 1
    contribution_document["storage"]["unique_cell_count"] = 1
    contribution_manifest = CellDatasetManifest.from_dict(contribution_document, registry=_registry(profile))
    with pytest.raises(CellDatasetError, match=r"coverage_ratio\[0\].*\[0, 1\]"):
        CellDataset.from_table(
            pa.table(
                {
                    "source_id": ["source-1"],
                    "gid": [first_gid],
                    "coverage_ratio": pa.array([1.1], type=pa.float64()),
                    "population": pa.array([10], type=pa.int64()),
                }
            ),
            contribution_manifest,
            registry=_registry(profile),
        )

    with pytest.raises(CellDatasetError, match="contains 1 null"):
        CellDataset.from_table(
            pa.table(
                {
                    "gid": [first_gid, None],
                    "population": pa.array([10, 20], type=pa.int64()),
                }
            ),
            _manifest(profile),
            registry=_registry(profile),
        )


def test_destination_must_not_already_exist(tmp_path, profile):
    first_gid, second_gid = _table_rows()
    dataset = CellDataset.from_table(
        pa.table({"gid": [first_gid, second_gid], "population": pa.array([10, 20], type=pa.int64())}),
        _manifest(profile),
        registry=_registry(profile),
    )
    destination = dataset.write(tmp_path / "existing")

    with pytest.raises(CellDatasetError, match="already exists"):
        dataset.write(destination)
