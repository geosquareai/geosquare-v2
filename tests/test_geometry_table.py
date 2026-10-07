"""Tests for auditable geometry-table to cell-contribution conversion."""

from __future__ import annotations

import pandas as pd
import pyarrow as pa
import pytest
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, box

from geosquare_v2 import CellDataset, CellDatasetManifest, DomainRegistry, GeosquareService, geometry_table_to_cells
from geosquare_v2.boundary import BoundaryPredicate, OperationalBoundary
from geosquare_v2.errors import ValidationError
from test_cell_dataset import _manifest, _registry


def _service(profile):
    return GeosquareService(DomainRegistry([profile]))


def test_point_and_multipoint_rows_preserve_source_provenance(profile):
    frame = pd.DataFrame(
        {
            "asset_id": [101, 102],
            "value": [5, 7],
            "geometry": [Point(0.5, 0.5), MultiPoint([(0.5, 0.5), (1.5, 0.5)])],
        }
    )

    result = geometry_table_to_cells(
        frame,
        _service(profile),
        "TS",
        3,
        geometry_column="geometry",
        source_id_column="asset_id",
        source_crs=profile.crs_wkt2,
        keep_columns=["asset_id", "value"],
    )

    assert len(result) == 3
    assert result["source_id"].tolist() == ["101", "102", "102"]
    assert result["value"].tolist() == [5, 7, 7]
    assert set(result["assignment_method"]) == {"point_to_cell"}
    assert result["coverage_ratio"].isna().all()
    assert result["length_ratio"].isna().all()
    assert result["boundary_policy"].isna().all()
    assert result["gid"].str.len().eq(3).all()


def test_line_polygon_and_multipart_geometries_emit_auditable_ratios(profile):
    frame = pd.DataFrame(
        {
            "feature_id": ["line", "polygon", "multi"],
            "geometry": [
                LineString([(100_000, 500_000), (1_900_000, 500_000)]),
                box(0, 0, 2_000_000, 1_000_000),
                MultiLineString([[(100_000, 500_000), (900_000, 500_000)], [(1_100_000, 500_000), (1_900_000, 500_000)]]),
            ],
        }
    )

    result = geometry_table_to_cells(
        frame,
        _service(profile),
        "TS",
        3,
        geometry_column="geometry",
        source_id_column="feature_id",
        source_crs=profile.crs_wkt2,
    )

    assert set(result["assignment_method"]) == {"line_to_cells", "polygon_to_cells"}
    line = result.loc[result.source_id == "line"]
    polygon = result.loc[result.source_id == "polygon"]
    multi = result.loc[result.source_id == "multi"]
    assert len(line) == 2
    assert line["length_ratio"].sum() == pytest.approx(1.0)
    assert line["coverage_ratio"].isna().all()
    assert len(polygon) == 2
    assert polygon["coverage_ratio"].sum() == pytest.approx(1.0)
    assert polygon["length_ratio"].isna().all()
    assert len(multi) == 2
    assert multi["length_ratio"].sum() == pytest.approx(1.0)


def test_boundary_policy_is_preserved_and_filters_points(profile):
    boundary = OperationalBoundary.from_geometry(
        box(0, 0, 1, 1),
        source_crs=profile.crs_wkt2,
        grid_crs=profile.crs_wkt2,
    )
    frame = pd.DataFrame(
        {
            "asset_id": ["inside", "outside"],
            "geometry": [Point(0.5, 0.5), Point(2.5, 0.5)],
        }
    )

    result = geometry_table_to_cells(
        frame,
        _service(profile),
        "TS",
        3,
        geometry_column="geometry",
        source_id_column="asset_id",
        source_crs=profile.crs_wkt2,
        boundary=boundary,
        boundary_policy=BoundaryPredicate.COVERS_POINT,
    )

    assert result["source_id"].tolist() == ["inside"]
    assert result["boundary_policy"].tolist() == [BoundaryPredicate.COVERS_POINT.value]


def test_source_row_provenance_is_used_when_source_id_is_not_selected(profile):
    frame = pd.DataFrame({"value": [1, 2], "geometry": [Point(0.5, 0.5), Point(1.5, 0.5)]})

    result = geometry_table_to_cells(
        frame,
        _service(profile),
        "TS",
        3,
        geometry_column="geometry",
        source_crs=profile.crs_wkt2,
    )

    assert "source_row" in result.columns
    assert result["source_row"].tolist() == [0, 1]


def test_invalid_geometry_table_inputs_are_rejected(profile):
    service = _service(profile)
    with pytest.raises(ValidationError, match="missing table columns"):
        geometry_table_to_cells(pd.DataFrame({"value": [1]}), service, "TS", 3)

    with pytest.raises(ValidationError, match="unsupported geometry type"):
        geometry_table_to_cells(
            pd.DataFrame({"geometry": [GeometryCollection([Point(0, 0)])]}),
            service,
            "TS",
            3,
            source_crs=profile.crs_wkt2,
        )

    with pytest.raises(ValidationError, match="COVERS_POINT"):
        geometry_table_to_cells(
            pd.DataFrame({"geometry": [box(0, 0, 1, 1)]}),
            service,
            "TS",
            3,
            source_crs=profile.crs_wkt2,
            boundary_policy=BoundaryPredicate.COVERS_POINT,
            boundary=OperationalBoundary.from_geometry(
                box(0, 0, 1, 1),
                source_crs=profile.crs_wkt2,
                grid_crs=profile.crs_wkt2,
            ),
        )

    with pytest.raises(ValidationError, match="must not be null"):
        geometry_table_to_cells(
            pd.DataFrame({"asset_id": [None], "geometry": [Point(0.5, 0.5)]}),
            service,
            "TS",
            3,
            source_id_column="asset_id",
            source_crs=profile.crs_wkt2,
        )


def test_contribution_output_can_be_validated_by_cell_dataset(profile):
    frame = pd.DataFrame(
        {
            "asset_id": ["parcel-1"],
            "population": [100],
            "geometry": [box(0, 0, 2_000_000, 1_000_000)],
        }
    )
    result = geometry_table_to_cells(
        frame,
        _service(profile),
        "TS",
        3,
        geometry_column="geometry",
        source_id_column="asset_id",
        source_crs=profile.crs_wkt2,
        keep_columns=["population"],
    )
    document = _manifest(profile, dataset_type="cell_contributions").to_dict()
    document["level"] = 3
    document["storage"]["row_count"] = len(result)
    document["storage"]["unique_cell_count"] = result["gid"].nunique()
    manifest = CellDatasetManifest.from_dict(document, registry=_registry(profile))

    dataset = CellDataset.from_table(
        pa.Table.from_pandas(result, preserve_index=False),
        manifest,
        registry=_registry(profile),
    )

    assert dataset.num_rows == 2
    assert dataset.manifest.dataset_type == "cell_contributions"
