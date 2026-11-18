from __future__ import annotations

import json
from pathlib import Path
import random

import pytest
from pyproj import CRS, Transformer
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from geosquare_v2.crs import wgs84_to_grid_transformer
from geosquare_v2.release import ReleaseProfile

ROOT = Path(__file__).parents[1]
PROFILE_ROOT = ROOT / "release" / "profiles"
BOUNDARY_ROOT = ROOT / "release" / "boundaries"


def _profile(code: str) -> ReleaseProfile:
    document = json.loads((PROFILE_ROOT / f"{code}.v2.json").read_text(encoding="utf-8"))
    return ReleaseProfile(**document)


def _boundary(code: str):
    document = json.loads((BOUNDARY_ROOT / f"{code}_full.geojson").read_text(encoding="utf-8"))
    return unary_union(tuple(shape(feature["geometry"]) for feature in document["features"]))


def _sample_points(code: str, count: int = 300) -> list[tuple[float, float]]:
    geometry = _boundary(code)
    min_x, min_y, max_x, max_y = geometry.bounds
    points: list[tuple[float, float]] = []

    for row in range(25):
        for column in range(25):
            longitude = min_x + (column + 0.5) * (max_x - min_x) / 25
            latitude = min_y + (row + 0.5) * (max_y - min_y) / 25
            if geometry.covers(Point(longitude, latitude)):
                points.append((longitude, latitude))

    representative = geometry.representative_point()
    points.append((representative.x, representative.y))
    random_points = random.Random(f"geosquare-crs-qa:{code}")
    while len(points) < count:
        longitude = random_points.uniform(min_x, max_x)
        latitude = random_points.uniform(min_y, max_y)
        if geometry.covers(Point(longitude, latitude)):
            points.append((longitude, latitude))
    return points[:count]


@pytest.mark.parametrize(
    "code",
    ("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL"),
)
def test_explicit_profile_pipeline_matches_pinned_proj(code: str):
    profile = _profile(code)
    points = _sample_points(code)
    longitudes, latitudes = zip(*points)

    explicit = wgs84_to_grid_transformer(profile)
    expected = Transformer.from_crs(
        CRS.from_epsg(4326),
        CRS.from_wkt(profile.crs_wkt2),
        always_xy=True,
    )
    actual_x, actual_y = explicit.transform(list(longitudes), list(latitudes))
    expected_x, expected_y = expected.transform(list(longitudes), list(latitudes))

    max_error_m = max(
        max(abs(actual - reference) for actual, reference in zip(actual_x, expected_x)),
        max(abs(actual - reference) for actual, reference in zip(actual_y, expected_y)),
    )
    assert max_error_m < 0.001


def test_selected_support_statuses():
    assert _profile("ID").support_status == "candidate"
    assert _profile("LA").support_status == "candidate"
    assert _profile("PH").support_status == "candidate"
    assert _profile("VN").support_status == "blocked"
