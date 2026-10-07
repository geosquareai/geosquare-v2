from __future__ import annotations

import pytest
from shapely.geometry import box

from geosquare_v2.boundary import BoundaryPredicate, OperationalBoundary
from geosquare_v2.errors import ValidationError
from geosquare_v2.model import CanonicalCell
from geosquare_v2.polyfill import polyfill


def _boundary(grid):
    # At level 3, cell (25, 25) spans x/y = 0..1,000,000 in the test profile.
    return OperationalBoundary.from_geometry(
        box(250_000, 250_000, 1_250_000, 1_250_000),
        source_crs=grid.profile.crs_wkt2,
        grid_crs=grid.profile.crs_wkt2,
    )


def test_point_policy_covers_boundary_edges(grid):
    boundary = _boundary(grid)

    assert boundary.covers_projected(250_000, 250_000)
    assert boundary.covers_projected(750_000, 750_000)
    assert not boundary.covers_projected(1_500_000, 500_000)


def test_cell_policies_have_different_meanings(grid):
    boundary = _boundary(grid)
    inside = CanonicalCell("TS", 3, 25, 25)
    partial = CanonicalCell("TS", 3, 26, 25)

    assert boundary.cell_matches(grid, inside, BoundaryPredicate.CENTROID_COVERED)
    assert not boundary.cell_matches(grid, partial, BoundaryPredicate.CENTROID_COVERED)
    assert boundary.cell_matches(grid, partial, BoundaryPredicate.INTERSECTS)
    assert boundary.cell_matches(grid, inside, BoundaryPredicate.MIN_COVERAGE, min_coverage=0.5)
    assert not boundary.cell_matches(grid, partial, BoundaryPredicate.MIN_COVERAGE, min_coverage=0.5)
    assert boundary.coverage_ratio(grid, inside) == pytest.approx(0.5625)
    assert boundary.coverage_ratio(grid, partial) == pytest.approx(0.1875)


def test_boundary_filter_can_filter_neighbourhood_results(grid):
    boundary = _boundary(grid)
    source = CanonicalCell("TS", 3, 25, 25)

    result = boundary.k_ring(grid, source, 1, BoundaryPredicate.INTERSECTS)

    assert source not in result
    assert result
    assert all(boundary.cell_matches(grid, cell, BoundaryPredicate.INTERSECTS) for cell in result)


def test_polyfill_requires_an_explicit_boundary_predicate(grid, profile):
    boundary = _boundary(grid)
    geometry = box(0, 0, 2_000_000, 1_000_000)

    with pytest.raises(ValidationError):
        polyfill(grid, geometry, profile.crs_wkt2, 3, boundary=boundary)


def test_polyfill_applies_minimum_boundary_coverage(grid, profile):
    boundary = _boundary(grid)
    geometry = box(0, 0, 2_000_000, 1_000_000)

    records = polyfill(
        grid,
        geometry,
        profile.crs_wkt2,
        3,
        boundary=boundary,
        boundary_predicate=BoundaryPredicate.MIN_COVERAGE,
        boundary_min_coverage=0.5,
    )

    assert records == ((grid.gid_from_canonical(CanonicalCell("TS", 3, 25, 25)), pytest.approx(1.0)),)


def test_point_predicate_cannot_be_used_for_cells(grid):
    boundary = _boundary(grid)
    with pytest.raises(ValidationError):
        boundary.cell_matches(
            grid,
            CanonicalCell("TS", 3, 25, 25),
            BoundaryPredicate.COVERS_POINT,
        )
