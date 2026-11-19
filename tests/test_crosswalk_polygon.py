from __future__ import annotations

import pytest
from shapely.geometry import box

from geosquare_v2.crosswalk import polygon_crosswalk_rows, validate_crosswalk
from geosquare_v2.errors import ValidationError

LEVEL = 3


def _manifest(level: int = LEVEL) -> dict[str, object]:
    return {
        "format_version": "1.0",
        "spec_version": "2.0",
        "domain_code": "ID",
        "level": level,
        "weight_kind": "luas",
        "source_description": "unit test polygons",
        "created_at": "2026-11-19T00:00:00Z",
        "registry_version": "2.0.0",
    }


def _cell_span(grid):
    bounds = grid.projected_bounds(grid.canonical_from_projected(500_000, 500_000, LEVEL))
    return bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y


def test_polygon_over_two_whole_cells_gets_equal_shares(grid):
    x0, y0, x1, y1 = _cell_span(grid)
    side = x1 - x0
    rows = polygon_crosswalk_rows([("A", box(x0, y0, x1 + side, y1))], grid, LEVEL)

    assert len(rows) == 2
    assert [row["bobot"] for row in rows] == pytest.approx([0.5, 0.5], abs=1e-12)


def test_polygon_split_across_a_cell_edge_gets_overlap_shares(grid):
    x0, y0, x1, y1 = _cell_span(grid)
    side = x1 - x0
    # Overlaps the left cell over 0.75 side and the right cell over 0.5 side, a total of 1.25 side.
    rows = polygon_crosswalk_rows([("A", box(x0 + side / 4, y0, x1 + side / 2, y1))], grid, LEVEL)

    weights = sorted(row["bobot"] for row in rows)
    assert weights == pytest.approx([0.4, 0.6], abs=1e-9)


def test_rows_pass_the_s6_crosswalk_validator(grid):
    x0, y0, x1, y1 = _cell_span(grid)
    side = x1 - x0
    rows = polygon_crosswalk_rows(
        [("A", box(x0 + side / 4, y0, x1 + side / 2, y1)), ("B", box(x0, y0, x1 + side, y1))],
        grid,
        LEVEL,
    )

    counts = validate_crosswalk(rows, _manifest())
    assert counts == {"sources": 2, "rows": len(rows), "cells": len({row["gid"] for row in rows})}


def test_duplicate_sumber_id_is_rejected(grid):
    x0, y0, x1, y1 = _cell_span(grid)
    with pytest.raises(ValidationError, match="duplicate sumber_id"):
        polygon_crosswalk_rows([("A", box(x0, y0, x1, y1)), ("A", box(x0, y0, x1, y1))], grid, LEVEL)


def test_zero_area_polygon_is_rejected(grid):
    with pytest.raises(ValidationError, match="has no area"):
        polygon_crosswalk_rows([("A", box(0, 0, 0, 0))], grid, LEVEL)
