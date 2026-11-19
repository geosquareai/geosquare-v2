"""Geographic QA for the released domains.

test_profile_crs_qa.py checks forward parity with pinned PROJ. These tests use the explicit
datum pipeline written in each signed profile. They check that the inverse returns the input
(within 1 mm without a datum shift, within 10% of the stated accuracy with one), that a point and
its cell centre keep the same cell after a WGS 84 round trip, and that the real ground size of
level-12 cells stays within the scale error the profile declares.
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path

import pytest
from pyproj import Geod
from pyproj.enums import TransformDirection

from geosquare_v2.crs import wgs84_to_grid_transformer
from geosquare_v2.db import DbRegistryLoader
from geosquare_v2.geometry import projected_cell_geometry
from geosquare_v2.grid import GeosquareGrid

from test_profile_crs_qa import _sample_points

RELEASED = ("BN", "ID", "LA", "MY", "PH", "SG")
LEVEL = 12
EXACT_LIMIT_M = 0.001  # no datum shift: the projection must invert to float precision, 1 mm is generous
ACCURACY_SHARE = 0.10  # with a datum shift: the inverse may add at most 10% of the operation's stated accuracy
GEOD = Geod(ellps="WGS84")
INVERSE = TransformDirection.INVERSE


def _round_trip_limit_m(profile) -> float:
    datum = profile.datum_transformation
    if datum.mode == "none":
        return EXACT_LIMIT_M
    return ACCURACY_SHARE * datum.stated_accuracy_m


@pytest.fixture(scope="session")
def released_profiles():
    project_root = Path(__file__).parents[1]
    encoded_keys = json.loads((project_root / "release/registry-trust.json").read_text(encoding="utf-8"))
    trust = {key_id: base64.b64decode(value, validate=True) for key_id, value in encoded_keys.items()}
    registry = DbRegistryLoader(
        trust,
        project_root / "src/geosquare_v2/db",
        boundary_root=project_root / "src/geosquare_v2/data/registry",
    ).load()
    return {code: registry.get(code) for code in RELEASED}


def _ground_distance_m(longitude_a: float, latitude_a: float, longitude_b: float, latitude_b: float) -> float:
    _, _, distance = GEOD.inv(longitude_a, latitude_a, longitude_b, latitude_b)
    return abs(distance)


@pytest.mark.parametrize("code", RELEASED)
def test_wgs84_round_trip_returns_input_within_declared_limit(released_profiles, code):
    profile = released_profiles[code]
    forward = wgs84_to_grid_transformer(profile)
    points = _sample_points(code)
    longitudes, latitudes = zip(*points)

    x, y = forward.transform(list(longitudes), list(latitudes))
    back_lon, back_lat = forward.transform(list(x), list(y), direction=INVERSE)

    worst = max(
        _ground_distance_m(lon, lat, back_lon_i, back_lat_i)
        for lon, lat, back_lon_i, back_lat_i in zip(longitudes, latitudes, back_lon, back_lat)
    )
    limit = _round_trip_limit_m(profile)
    assert worst < limit, f"{code}: round trip moved a point by {worst:.6f} m, limit {limit:.6f} m"


@pytest.mark.parametrize("code", RELEASED)
def test_point_and_cell_centre_keep_their_cell_after_round_trip(released_profiles, code):
    profile = released_profiles[code]
    grid = GeosquareGrid(profile)
    forward = wgs84_to_grid_transformer(profile)

    moved = []
    for longitude, latitude in _sample_points(code):
        cell = grid.canonical_from_lonlat(longitude, latitude, LEVEL, forward)

        x, y = forward.transform(longitude, latitude)
        back_lon, back_lat = forward.transform(x, y, direction=INVERSE)
        if grid.canonical_from_lonlat(back_lon, back_lat, LEVEL, forward) != cell:
            moved.append(("point", longitude, latitude))

        bounds = grid.projected_bounds(cell)
        centre_x = (bounds.min_x + bounds.max_x) / 2
        centre_y = (bounds.min_y + bounds.max_y) / 2
        centre_lon, centre_lat = forward.transform(centre_x, centre_y, direction=INVERSE)
        if grid.canonical_from_lonlat(centre_lon, centre_lat, LEVEL, forward) != cell:
            moved.append(("centre", longitude, latitude))

    assert not moved, f"{code}: {len(moved)} cell changes after round trip, first: {moved[:3]}"


@pytest.mark.parametrize("code", RELEASED)
def test_cell_ground_sides_stay_within_declared_scale_error(released_profiles, code):
    profile = released_profiles[code]
    grid = GeosquareGrid(profile)
    forward = wgs84_to_grid_transformer(profile)

    cells = {grid.canonical_from_lonlat(lon, lat, LEVEL, forward) for lon, lat in _sample_points(code)}
    limit_pct = profile.scale_error_max_pct
    worst_pct = 0.0
    worst_length = None

    for cell in cells:
        corners = list(projected_cell_geometry(grid, cell).exterior.coords)[:4]
        grid_side = math.dist(corners[0], corners[1])
        ground_corners = [forward.transform(x, y, direction=INVERSE) for x, y in corners]
        ring = zip(ground_corners, ground_corners[1:] + ground_corners[:1])
        for (lon0, lat0), (lon1, lat1) in ring:
            length = _ground_distance_m(lon0, lat0, lon1, lat1)
            deviation_pct = abs(length / grid_side - 1) * 100
            if deviation_pct > worst_pct:
                worst_pct, worst_length = deviation_pct, length

    assert worst_pct <= limit_pct, (
        f"{code}: ground side deviates {worst_pct:.4f}% from grid side (declared {limit_pct:.4f}%), "
        f"worst ground side {worst_length:.3f} m"
    )
