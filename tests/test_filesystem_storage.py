"""Tests for optional fsspec-backed dataset storage."""

from __future__ import annotations

import json

import fsspec
import pyarrow as pa
import pytest

from geosquare_v2 import (
    CellDataset,
    CellDatasetError,
    CellDatasetManifest,
    query_cell_dataset_filesystem,
    read_cell_dataset_filesystem,
    write_cell_dataset_filesystem,
)
from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.packing import pack_int64
from test_cell_dataset import _manifest, _registry


_MANIFEST_METADATA_KEY = b"geosquare.manifest"


def _compact_dataset(profile):
    gids = [canonical_to_gid(12, 0, 0), canonical_to_gid(12, 1, 0)]
    table = pa.table(
        {
            "gid": pa.array(gids, type=pa.string()),
            "population": pa.array([10, 20], type=pa.int64()),
        }
    )
    return CellDataset.from_table(table, _manifest(profile), registry=_registry(profile))


def _queryable_dataset(profile):
    gid = canonical_to_gid(12, 500000, 500000)
    table = pa.table(
        {
            "gid": pa.array([gid], type=pa.string()),
            "packed_id": pa.array([pack_int64(7, 12, 500000, 500000)], type=pa.int64()),
            "x_idx": pa.array([500000], type=pa.int64()),
            "y_idx": pa.array([500000], type=pa.int64()),
            "population": pa.array([10], type=pa.int64()),
        }
    )
    document = _manifest(profile, queryable=True).to_dict()
    document["storage"]["row_count"] = 1
    document["storage"]["unique_cell_count"] = 1
    manifest = CellDatasetManifest.from_dict(document, registry=_registry(profile))
    return CellDataset.from_table(table, manifest, registry=_registry(profile))


def test_memory_filesystem_round_trip_preserves_dataset_contract(profile):
    dataset = _compact_dataset(profile)
    url = "memory://geosquare-tests/compact"

    write_cell_dataset_filesystem(dataset, url)
    loaded = read_cell_dataset_filesystem(url, registry=_registry(profile))

    assert loaded.table.to_pydict() == dataset.table.to_pydict()
    assert loaded.manifest.to_json() == dataset.manifest.to_json()


def test_s3_compatible_url_works_with_injected_memory_filesystem(profile):
    filesystem = fsspec.filesystem("memory")
    dataset = _compact_dataset(profile)
    url = "s3://fake-bucket/geosquare/compact"

    write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)
    loaded = read_cell_dataset_filesystem(url, filesystem=filesystem, registry=_registry(profile))

    assert loaded.num_rows == 2
    assert filesystem.exists("fake-bucket/geosquare/compact/data/part-00000.parquet")


def test_filesystem_query_preserves_local_query_semantics(profile):
    filesystem = fsspec.filesystem("memory")
    dataset = _queryable_dataset(profile)
    url = "memory://geosquare-tests/queryable"
    write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)

    result = query_cell_dataset_filesystem(
        url,
        bbox=(0.0, -0.001, 0.001, 0.001),
        domain="TS",
        level=12,
        registry=_registry(profile),
        filesystem=filesystem,
    )

    assert result.to_pydict()["population"] == [10]
    assert result.schema.metadata[_MANIFEST_METADATA_KEY]


def test_missing_sidecar_and_mismatched_manifest_are_rejected(profile):
    filesystem = fsspec.filesystem("memory")
    dataset = _compact_dataset(profile)
    url = "memory://geosquare-tests/invalid"
    write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)

    filesystem.rm("geosquare-tests/invalid/manifest.json")
    with pytest.raises(CellDatasetError, match="manifest sidecar"):
        read_cell_dataset_filesystem(url, filesystem=filesystem, registry=_registry(profile))
    filesystem.rm("geosquare-tests/invalid", recursive=True)
    write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)
    sidecar_path = "geosquare-tests/invalid/manifest.json"
    sidecar = json.loads(filesystem.open(sidecar_path, "rb").read())
    sidecar["provenance"]["notes"] = "changed"
    with filesystem.open(sidecar_path, "wb") as stream:
        stream.write(json.dumps(sidecar).encode("utf-8"))

    with pytest.raises(CellDatasetError, match="does not match"):
        read_cell_dataset_filesystem(url, filesystem=filesystem, registry=_registry(profile))


def test_filesystem_destination_must_not_exist(profile):
    filesystem = fsspec.filesystem("memory")
    dataset = _compact_dataset(profile)
    url = "memory://geosquare-tests/collision"
    write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)

    with pytest.raises(CellDatasetError, match="already exists"):
        write_cell_dataset_filesystem(dataset, url, filesystem=filesystem)
