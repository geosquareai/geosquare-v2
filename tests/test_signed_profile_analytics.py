from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest
from pyproj import CRS, Transformer
from shapely.geometry import box

from geosquare_v2.batch import encode_projected_numpy
from geosquare_v2.db import DbRegistryLoader
from geosquare_v2.geometry import projected_cell_geometry, wgs84_cell_geometry
from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.polyfill import CoverageMode, polyfill
from geosquare_v2.warehouse import (
    render_bigquery_projected_encoder,
    render_postgis_projected_encoder,
    render_snowflake_projected_encoder,
)


@pytest.fixture(scope="session")
def signed_profiles():
    project_root = Path(__file__).parents[1]
    encoded_keys = json.loads((project_root / "release/registry-trust.json").read_text(encoding="utf-8"))
    trust = {key_id: base64.b64decode(value, validate=True) for key_id, value in encoded_keys.items()}
    registry = DbRegistryLoader(
        trust,
        project_root / "src/geosquare_v2/db",
        boundary_root=project_root / "src/geosquare_v2/data/registry",
    ).load()
    return {code: registry.get(code) for code in ("ID", "VN")}


@pytest.mark.parametrize(("domain_code", "longitude", "latitude"), [("ID", 106.8456, -6.2088), ("VN", 105.8342, 21.0278)])
def test_verified_profiles_work_across_optional_analytics_layers(signed_profiles, domain_code, longitude, latitude):
    profile = signed_profiles[domain_code]
    grid = GeosquareGrid(profile)
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(profile.crs_wkt2), always_xy=True)
    cell = grid.canonical_from_lonlat(longitude, latitude, 9, transformer)
    bounds = grid.projected_bounds(cell)

    assert projected_cell_geometry(grid, cell).is_valid
    assert wgs84_cell_geometry(grid, cell).is_valid

    half_cell = box(bounds.min_x, bounds.min_y, (bounds.min_x + bounds.max_x) / 2, bounds.max_y)
    coverage = polyfill(grid, half_cell, profile.crs_wkt2, 9, coverage_mode=CoverageMode.EQUAL_AREA, max_candidate_limit=10)
    assert len(coverage) == 1
    assert coverage[0][0] == grid.gid_from_canonical(cell)
    assert coverage[0][1] == pytest.approx(0.5, abs=0.01)

    encoded = encode_projected_numpy(
        grid,
        np.array([(bounds.min_x + bounds.max_x) / 2]),
        np.array([(bounds.min_y + bounds.max_y) / 2]),
        9,
    )
    assert encoded.gid[0] == grid.gid_from_canonical(cell)
    assert int(encoded.packed_id[0]) == grid.pack(cell)

    assert "packed_id STRING" in render_bigquery_projected_encoder(profile)
    assert "RETURNS VARIANT" in render_snowflake_projected_encoder(profile)
    assert "packed_id bigint" in render_postgis_projected_encoder(profile)
