"""Tests for the manifest 1.1 cross-field checks (spec S8)."""

from __future__ import annotations

from copy import deepcopy

import pytest

from geosquare_v2.cell_metadata import check_dataset_metadata, check_row_counts, check_space_weights
from geosquare_v2.errors import CellDatasetManifestError


def _manifest() -> dict:
    return {
        "value_fields": [
            {"name": "population", "semantics": "COUNT", "space_weight": None},
            {"name": "unemployment_rate", "semantics": "RATE", "space_weight": "population"},
            {"name": "density", "semantics": "DENSITY", "space_weight": "area"},
            {"name": "flood_depth_m", "semantics": "MEASUREMENT", "space_weight": None},
        ],
        "storage": {
            "row_count": 3,
            "data_files": [
                {"path": "data/part-00000.parquet", "row_count": 2},
                {"path": "data/part-00001.parquet", "row_count": 1},
            ],
        },
    }


def test_valid_manifest_passes() -> None:
    check_dataset_metadata(_manifest())


def test_weight_must_name_an_existing_value_field() -> None:
    manifest = _manifest()
    manifest["value_fields"][1]["space_weight"] = "households"

    with pytest.raises(CellDatasetManifestError, match="not a value field"):
        check_space_weights(manifest)


def test_weight_must_be_a_count_or_total_field() -> None:
    manifest = _manifest()
    manifest["value_fields"][1]["space_weight"] = "flood_depth_m"

    with pytest.raises(CellDatasetManifestError, match="must have semantics COUNT or TOTAL"):
        check_space_weights(manifest)


def test_value_field_cannot_weight_itself() -> None:
    manifest = _manifest()
    manifest["value_fields"][0]["space_weight"] = "population"

    with pytest.raises(CellDatasetManifestError, match="cannot weight itself"):
        check_space_weights(manifest)


def test_area_is_ambiguous_when_a_field_has_that_name() -> None:
    manifest = _manifest()
    manifest["value_fields"].append({"name": "area", "semantics": "COUNT", "space_weight": None})

    with pytest.raises(CellDatasetManifestError, match="ambiguous"):
        check_space_weights(manifest)


def test_non_string_weight_is_rejected() -> None:
    manifest = _manifest()
    manifest["value_fields"][1]["space_weight"] = 3

    with pytest.raises(CellDatasetManifestError, match="null or a non-empty string"):
        check_space_weights(manifest)


def test_row_count_must_match_data_files() -> None:
    manifest = deepcopy(_manifest())
    manifest["storage"]["row_count"] = 4

    with pytest.raises(CellDatasetManifestError, match="hold 3 rows"):
        check_row_counts(manifest)


def test_data_files_must_be_non_empty() -> None:
    manifest = deepcopy(_manifest())
    manifest["storage"]["data_files"] = []

    with pytest.raises(CellDatasetManifestError, match="non-empty list"):
        check_row_counts(manifest)


def test_boolean_row_count_is_rejected() -> None:
    manifest = deepcopy(_manifest())
    manifest["storage"]["data_files"][0]["row_count"] = True

    with pytest.raises(CellDatasetManifestError, match="must be an integer"):
        check_row_counts(manifest)
