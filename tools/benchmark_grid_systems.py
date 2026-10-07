#!/usr/bin/env python3
"""Measure GeoSquare ground-cell consistency and record comparison metadata.

The other systems are not forced into a fake one-to-one resolution match here. Their
shape and hierarchy facts are recorded in GRID_SYSTEM_COMPARISON.md from their official
documentation. GeoSquare metrics use the actual signed candidate profiles.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, median

from pyproj import CRS, Geod, Transformer

from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.codec import cell_side_m
from geosquare_v2.release import ReleaseProfile

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "release" / "scale" / "GRID_SYSTEM_COMPARISON_BENCHMARK.json"
LEVEL = 12
PROFILE_CODES = ("ID", "VN")


def geometry_objects(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return [feature["geometry"] for feature in document.get("features", [])]
    if document.get("type") == "Feature":
        return [document["geometry"]]
    return [document]


def positions(document: dict) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for geometry in geometry_objects(document):
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        polygons = [coordinates] if geometry_type == "Polygon" else coordinates
        for polygon in polygons:
            for ring in polygon:
                result.extend((float(point[0]), float(point[1])) for point in ring)
    return result


def sample_positions(path: Path, maximum: int = 500) -> list[tuple[float, float]]:
    values = positions(json.loads(path.read_text(encoding="utf-8")))
    stride = max(1, math.ceil(len(values) / maximum))
    return values[::stride]


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def measure_profile(profile_code: str) -> dict:
    profile = ReleaseProfile(
        **json.loads((ROOT / "release" / "profiles" / f"{profile_code}.v2.json").read_text(encoding="utf-8"))
    )
    boundary_path = ROOT / "release" / "boundaries" / f"{profile_code}_full.geojson"
    if not boundary_path.is_file():
        boundary_path = ROOT / "release" / "boundaries" / f"{profile_code}.geojson"
    to_grid = Transformer.from_crs(
        CRS.from_epsg(4326),
        CRS.from_user_input(profile.crs_wkt2),
        always_xy=True,
    )
    to_wgs84 = Transformer.from_crs(
        CRS.from_user_input(profile.crs_wkt2),
        CRS.from_epsg(4326),
        always_xy=True,
    )
    geod = Geod(ellps="WGS84")
    grid = GeosquareGrid(profile)
    side_m = cell_side_m(LEVEL)
    side_ratios: list[float] = []
    area_ratios: list[float] = []
    seen: set[tuple[int, int]] = set()
    skipped = 0

    for longitude, latitude in sample_positions(boundary_path):
        try:
            cell = grid.canonical_from_lonlat(longitude, latitude, LEVEL, to_grid)
        except Exception:
            skipped += 1
            continue
        key = (cell.x_idx, cell.y_idx)
        if key in seen:
            continue
        seen.add(key)
        bounds = grid.projected_bounds(cell)
        projected_corners = (
            (bounds.min_x, bounds.min_y),
            (bounds.min_x, bounds.max_y),
            (bounds.max_x, bounds.max_y),
            (bounds.max_x, bounds.min_y),
        )
        corners = [to_wgs84.transform(x, y) for x, y in projected_corners]
        lengths = []
        for first, second in zip(corners, corners[1:] + corners[:1]):
            _, _, distance = geod.inv(first[0], first[1], second[0], second[1])
            lengths.append(abs(distance))
        polygon_area, _ = geod.polygon_area_perimeter(
            [point[0] for point in corners],
            [point[1] for point in corners],
        )
        side_ratios.append(max(lengths) / min(lengths))
        area_ratios.append(abs(polygon_area) / (side_m * side_m))

    return {
        "profile": profile_code,
        "level": LEVEL,
        "nominal_grid_edge_m": side_m,
        "sample_count": len(side_ratios),
        "skipped_points": skipped,
        "published_scale_error_max_pct": profile.scale_error_max_pct,
        "ground_side_ratio": {
            "median": median(side_ratios),
            "p95": percentile(side_ratios, 0.95),
            "max": max(side_ratios),
        },
        "ground_area_ratio": {
            "median": median(area_ratios),
            "p05": percentile(area_ratios, 0.05),
            "p95": percentile(area_ratios, 0.95),
            "min": min(area_ratios),
            "max": max(area_ratios),
        },
        "mean_side_ratio": mean(side_ratios),
    }


def main() -> None:
    document = {
        "metric_definition": {
            "level": LEVEL,
            "ground_side_ratio": "maximum geodesic corner-to-corner side / minimum side",
            "ground_area_ratio": "geodesic cell area / nominal grid-CRS square area",
            "note": "These are GeoSquare profile measurements. Other systems are compared by documented design because resolutions and cell models are not directly equivalent.",
        },
        "geosquare": [measure_profile(code) for code in PROFILE_CODES],
        "optional_dependencies": {
            "h3": _available("h3"),
            "s2sphere": _available("s2sphere"),
        },
    }
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote GeoSquare benchmark: {OUTPUT}")


def _available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


if __name__ == "__main__":
    main()
