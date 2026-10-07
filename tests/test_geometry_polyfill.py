from __future__ import annotations

import pytest
from shapely.geometry import LineString, box

from geosquare_v2.errors import CandidateLimitExceededError, ValidationError
from geosquare_v2.geometry import projected_cell_geometry, wgs84_cell_geometry
from geosquare_v2.model import CanonicalCell
from geosquare_v2.polyfill import CoverageMode, polyfill, polyfill_stream


def test_projected_geometry_is_the_exact_authoritative_square(grid):
    cell = CanonicalCell("TS", 4, 50, 50)
    bounds = grid.projected_bounds(cell)
    geometry = projected_cell_geometry(grid, cell)

    assert geometry.bounds == (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)
    assert geometry.area == pytest.approx(bounds.width * bounds.height)
    assert tuple(geometry.exterior.coords) == bounds.ring()


def test_wgs84_geometry_is_valid_and_densified(grid):
    geometry = wgs84_cell_geometry(grid, CanonicalCell("TS", 1, 2, 2), max_segment_length_m=250_000)

    assert geometry.is_valid
    assert len(geometry.exterior.coords) > 5
    assert all(-180 <= x <= 180 and -90 <= y <= 90 for x, y in geometry.exterior.coords)


def test_planar_and_equal_area_fractional_polyfill(grid, profile):
    cell = CanonicalCell("TS", 4, 50, 50)
    bounds = grid.projected_bounds(cell)
    left_half = box(bounds.min_x, bounds.min_y, (bounds.min_x + bounds.max_x) / 2, bounds.max_y)

    planar = polyfill(grid, left_half, profile.crs_wkt2, 4, coverage_mode=CoverageMode.GRID_PLANAR)
    equal_area = polyfill(grid, left_half, profile.crs_wkt2, 4, coverage_mode=CoverageMode.EQUAL_AREA)

    assert planar == ((grid.gid_from_canonical(cell), pytest.approx(0.5)),)
    assert len(equal_area) == 1
    assert equal_area[0][0] == grid.gid_from_canonical(cell)
    assert equal_area[0][1] == pytest.approx(0.5, abs=0.02)


def test_polyfill_enforces_limit_before_enumeration(grid, profile):
    root = grid.profile.root_bounds
    with pytest.raises(CandidateLimitExceededError):
        tuple(polyfill_stream(grid, box(root.min_x, root.min_y, root.max_x, root.max_y), profile.crs_wkt2, 5, max_candidate_limit=10))


def test_polyfill_rejects_non_polygonal_inputs(grid, profile):
    with pytest.raises(ValidationError):
        tuple(polyfill_stream(grid, LineString([(0, 0), (1, 1)]), profile.crs_wkt2, 4))
