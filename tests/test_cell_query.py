"""Tests for local queryable cell-dataset filtering."""

from __future__ import annotations

import pyarrow as pa
import pytest

from geosquare_v2 import CellDataset, CellDatasetError, CellDatasetManifest, query_cell_dataset
from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.packing import pack_int64
from test_cell_dataset import _manifest, _registry


_MANIFEST_METADATA_KEY = b"geosquare.manifest"


def _queryable_dataset(tmp_path, profile, rows):
    table = pa.table(
        {
            "gid": pa.array([row[0] for row in rows], type=pa.string()),
            "packed_id": pa.array([pack_int64(7, 12, row[1], row[2]) for row in rows], type=pa.int64()),
            "x_idx": pa.array([row[1] for row in rows], type=pa.int64()),
            "y_idx": pa.array([row[2] for row in rows], type=pa.int64()),
            "population": pa.array([row[3] for row in rows], type=pa.int64()),
        }
    )
    document = _manifest(profile, queryable=True).to_dict()
    document["storage"]["row_count"] = len(rows)
    document["storage"]["unique_cell_count"] = len({(row[1], row[2]) for row in rows})
    manifest = CellDatasetManifest.from_dict(document, registry=_registry(profile))
    return CellDataset.from_table(table, manifest, registry=_registry(profile)).write(tmp_path / "queryable")


def test_bbox_query_filters_queryable_dataset_and_preserves_manifest_metadata(tmp_path, profile):
    rows = [
        (canonical_to_gid(12, 500000, 500000), 500000, 500000, 10),
        (canonical_to_gid(12, 0, 0), 0, 0, 99),
    ]
    destination = _queryable_dataset(tmp_path, profile, rows)

    result = query_cell_dataset(
        destination,
        bbox=(0.0, -0.001, 0.003, 0.001),
        domain="TS",
        level=12,
        registry=_registry(profile),
    )

    assert result.to_pydict()["population"] == [10]
    assert result.schema.metadata[_MANIFEST_METADATA_KEY]
    assert result.schema.metadata[_MANIFEST_METADATA_KEY].startswith(b"{")


def test_query_rejects_domain_level_and_compact_mismatches(tmp_path, profile):
    rows = [(canonical_to_gid(12, 500000, 500000), 500000, 500000, 10)]
    destination = _queryable_dataset(tmp_path, profile, rows)

    with pytest.raises(CellDatasetError, match="requested 'XX'"):
        query_cell_dataset(destination, bbox=(0, -0.001, 0.001, 0.001), domain="XX", registry=_registry(profile))
    with pytest.raises(CellDatasetError, match="requested 11"):
        query_cell_dataset(destination, bbox=(0, -0.001, 0.001, 0.001), level=11, registry=_registry(profile))

    compact_document = _manifest(profile).to_dict()
    compact_document["storage"]["row_count"] = 1
    compact_document["storage"]["unique_cell_count"] = 1
    compact_manifest = CellDatasetManifest.from_dict(compact_document, registry=_registry(profile))
    compact = CellDataset.from_table(
        pa.table(
            {
                "gid": [canonical_to_gid(12, 500000, 500000)],
                "population": pa.array([10], type=pa.int64()),
            }
        ),
        compact_manifest,
        registry=_registry(profile),
    ).write(tmp_path / "compact")
    with pytest.raises(CellDatasetError, match="compact"):
        query_cell_dataset(compact, bbox=(0, -0.001, 0.001, 0.001), registry=_registry(profile))


def test_invalid_bboxes_are_rejected(tmp_path, profile):
    rows = [(canonical_to_gid(12, 500000, 500000), 500000, 500000, 10)]
    destination = _queryable_dataset(tmp_path, profile, rows)
    invalid_bboxes = [
        (0, 0, 0, 1),
        (0, 1, 1, 0),
        (-181, 0, 1, 1),
        (0, -91, 1, 1),
        (0, 0, 1),
    ]

    for bbox in invalid_bboxes:
        with pytest.raises(CellDatasetError, match="bbox"):
            query_cell_dataset(destination, bbox=bbox, registry=_registry(profile))


def test_bbox_without_matching_cells_returns_empty_table(tmp_path, profile):
    rows = [(canonical_to_gid(12, 500000, 500000), 500000, 500000, 10)]
    destination = _queryable_dataset(tmp_path, profile, rows)

    result = query_cell_dataset(
        destination,
        bbox=(0.0, 89.9, 0.1, 89.91),
        registry=_registry(profile),
    )

    assert result.num_rows == 0
    assert result.column_names == ["gid", "packed_id", "x_idx", "y_idx", "population"]


def test_antimeridian_bbox_is_split_into_two_query_windows(tmp_path, profile):
    rows = [
        (canonical_to_gid(12, 121513, 500000), 121513, 500000, 10),
        (canonical_to_gid(12, 878486, 500000), 878486, 500000, 20),
        (canonical_to_gid(12, 500000, 500000), 500000, 500000, 99),
    ]
    destination = _queryable_dataset(tmp_path, profile, rows)

    result = query_cell_dataset(
        destination,
        bbox=(170.0, -1.0, -170.0, 1.0),
        registry=_registry(profile),
    )

    assert sorted(result.to_pydict()["population"]) == [10, 20]
