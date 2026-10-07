from __future__ import annotations

import pytest
from shapely.geometry import LineString, box

from geosquare_v2.conversion import (
    cell_to_geometry,
    cells_to_geometry,
    line_to_cells,
    point_to_cell,
    polygon_to_cell,
    polygon_to_cells,
)
from geosquare_v2.model import CanonicalCell


class IdentityTransformer:
    def transform(self, x: float, y: float) -> tuple[float, float]:
        return x, y


def test_point_to_cell_returns_common_cell_record(grid):
    result = point_to_cell(grid, 0.0, 0.0, 9, IdentityTransformer())

    assert result.cell.domain_code == "TS"
    assert result.gid == result.uri.rsplit(":", 1)[-1]
    assert result.projected_bounds.width == result.projected_bounds.height


def test_polygon_to_cells_returns_area_ratios_and_optional_geometry(grid, profile):
    geometry = box(0, 0, 2_000_000, 1_000_000)
    records = polygon_to_cells(
        grid,
        geometry,
        profile.crs_wkt2,
        3,
        output_geometry=True,
        geometry_format="wkt",
    )

    assert len(records) == 2
    assert all(record.coverage_ratio == pytest.approx(1.0) for record in records)
    assert all(record.geometry.startswith("POLYGON") for record in records)
    assert all(record.length_ratio is None for record in records)


def test_polygon_to_cell_supports_centroid_and_largest_overlap(grid, profile):
    geometry = box(100_000, 100_000, 900_000, 900_000)

    centroid = polygon_to_cell(grid, geometry, profile.crs_wkt2, 3, selection="centroid")
    largest = polygon_to_cell(grid, geometry, profile.crs_wkt2, 3, selection="largest_overlap")

    expected = grid.gid_from_canonical(CanonicalCell("TS", 3, 25, 25))
    assert centroid.gid == expected
    assert largest.gid == expected


def test_line_to_cells_returns_positive_length_ratios(grid, profile):
    line = LineString([(100_000, 500_000), (1_900_000, 500_000)])
    records = line_to_cells(grid, line, profile.crs_wkt2, 3)

    assert len(records) == 2
    assert sum(record.length_ratio for record in records) == pytest.approx(1.0)
    assert all(record.coverage_ratio is None for record in records)


def test_cell_geometry_helpers_support_wkt_and_batches(grid):
    cells = (CanonicalCell("TS", 3, 25, 25), CanonicalCell("TS", 3, 26, 25))

    wkt = cell_to_geometry(grid, cells[0], geometry_format="wkt")
    batch = cells_to_geometry(grid, cells, geometry_format="wkb")

    assert wkt.startswith("POLYGON")
    assert len(batch) == 2
    assert all(isinstance(value, bytes) for value in batch)
