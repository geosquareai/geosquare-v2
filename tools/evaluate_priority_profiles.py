#!/usr/bin/env python3
"""Compare projection candidates for the six priority ASEAN profiles.

This produces review artifacts only. It does not mutate signed profiles or the registry
 database.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterator

import pyproj
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "release" / "profiles" / "ASEAN_DOMAIN_CANDIDATES.json"
OUTPUT = ROOT / "release" / "scale" / "ASEAN_PRIORITY_PROFILE_REVIEW.json"
MARKDOWN_OUTPUT = ROOT / "internal" / "research" / "ASEAN_PRIORITY_PROFILE_REVIEW.md"
PRIORITY_CODES = ("ID", "PH", "VN", "MM", "TH", "MY")


def geometry_objects(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return [feature["geometry"] for feature in document.get("features", [])]
    if document.get("type") == "Feature":
        return [document["geometry"]]
    return [document]


def rings_from_geometry(geometry: dict) -> Iterator[list[tuple[float, float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        polygons = [coordinates]
    elif geometry_type == "MultiPolygon":
        polygons = coordinates
    else:
        raise ValueError(f"unsupported geometry type: {geometry_type!r}")
    for polygon in polygons:
        for ring in polygon:
            yield [(float(point[0]), float(point[1])) for point in ring]


def load_boundary(path: Path):
    try:
        from shapely.geometry import Point, shape
        from shapely.ops import unary_union
    except ImportError as exc:
        raise RuntimeError("profile evaluation requires Shapely") from exc
    document = json.loads(path.read_text(encoding="utf-8"))
    geometries = [shape(geometry) for geometry in geometry_objects(document)]
    return unary_union(geometries)


def boundary_rings(path: Path) -> list[list[tuple[float, float]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return [ring for geometry in geometry_objects(document) for ring in rings_from_geometry(geometry)]


def densify_segment(first: tuple[float, float], second: tuple[float, float]) -> Iterator[tuple[float, float]]:
    lon1, lat1 = first
    lon2, lat2 = second
    delta_lon = lon2 - lon1
    if delta_lon > 180:
        lon2 -= 360
    elif delta_lon < -180:
        lon2 += 360
    steps = max(1, min(25, math.ceil(max(abs(lon2 - lon1), abs(lat2 - lat1)) / 0.5)))
    for index in range(steps):
        fraction = index / steps
        longitude = lon1 + (lon2 - lon1) * fraction
        if longitude > 180:
            longitude -= 360
        if longitude < -180:
            longitude += 360
        yield longitude, lat1 + (lat2 - lat1) * fraction


def sampled_boundary(rings: list[list[tuple[float, float]]], max_vertices: int = 20_000) -> list[tuple[float, float]]:
    total = sum(len(ring) for ring in rings)
    stride = max(1, math.ceil(total / max_vertices))
    result: list[tuple[float, float]] = []
    for ring in rings:
        sampled = ring[::stride]
        if ring and sampled[-1] != ring[-1]:
            sampled.append(ring[-1])
        for index, first in enumerate(sampled):
            result.extend(densify_segment(first, sampled[(index + 1) % len(sampled)]))
    return result


def interior_samples(geometry, bounds: tuple[float, float, float, float], divisions: int = 8):
    Point, _ = load_boundary_from_geometry_tools()
    min_lon, min_lat, max_lon, max_lat = bounds
    result = []
    for row in range(divisions + 1):
        latitude = min_lat + (max_lat - min_lat) * row / divisions
        for column in range(divisions + 1):
            longitude = min_lon + (max_lon - min_lon) * column / divisions
            if geometry.covers(Point(longitude, latitude)):
                result.append((longitude, latitude))
    return result


def load_boundary_from_geometry_tools():
    try:
        from shapely.geometry import Point
    except ImportError as exc:
        raise RuntimeError("profile evaluation requires Shapely") from exc
    return Point, None


def bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def lcc_proj4(box: tuple[float, float, float, float], fraction: float) -> str:
    min_lon, min_lat, max_lon, max_lat = box
    lat_span = max_lat - min_lat
    return (
        f"+proj=lcc +lat_1={min_lat + lat_span * fraction} "
        f"+lat_2={max_lat - lat_span * fraction} "
        f"+lat_0={(min_lat + max_lat) / 2} +lon_0={(min_lon + max_lon) / 2} "
        "+x_0=0 +y_0=0 +datum=WGS84 +units=m +type=crs"
    )


def eqc_proj4(box: tuple[float, float, float, float], latitude_of_true_scale: float) -> str:
    min_lon, _, max_lon, _ = box
    return (
        f"+proj=eqc +lat_ts={latitude_of_true_scale} +lat_0=0 "
        f"+lon_0={(min_lon + max_lon) / 2} +datum=WGS84 +units=m +type=crs"
    )


def candidate_specs(code: str, box: tuple[float, float, float, float]) -> list[tuple[str, CRS, str]]:
    min_lon, min_lat, max_lon, max_lat = box
    center_lat = (min_lat + max_lat) / 2
    specs: list[tuple[str, CRS, str]] = []
    if code in {"ID", "VN"}:
        profile = json.loads((ROOT / "release" / "profiles" / f"{code}.v2.json").read_text(encoding="utf-8"))
        specs.append(("existing_profile", CRS.from_wkt(profile["crs_wkt2"]), "existing profile CRS"))
    specs.append(("eqc_centered", CRS.from_proj4(eqc_proj4(box, center_lat)), "EQC with centered true-scale latitude"))
    specs.append(("lcc_fraction_1_6", CRS.from_proj4(lcc_proj4(box, 1 / 6)), "LCC with 1/6 and 5/6 parallels"))
    specs.append(("lcc_fraction_1_4", CRS.from_proj4(lcc_proj4(box, 1 / 4)), "LCC with 1/4 and 3/4 parallels"))
    if code in {"ID", "PH", "MY"}:
        specs.append(("lcc_fraction_1_3", CRS.from_proj4(lcc_proj4(box, 1 / 3)), "LCC with 1/3 and 2/3 parallels"))
    return specs


def evaluate_candidate(
    code: str,
    name: str,
    boundary_file: Path,
    boundary_geometry,
    points: list[tuple[float, float]],
    box: tuple[float, float, float, float],
    candidate_name: str,
    crs: CRS,
    note: str,
) -> dict:
    projection = pyproj.Proj(crs)
    transformer = Transformer.from_crs("OGC:CRS84", crs, always_xy=True)
    maximum = (-1.0, None, None, None)
    projected_boundary = []
    for longitude, latitude in points:
        factors = projection.get_factors(longitude, latitude)
        error = 100 * max(abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1))
        if error > maximum[0]:
            maximum = (error, longitude, latitude, factors)
        projected_boundary.append(transformer.transform(longitude, latitude))

    interior = interior_samples(boundary_geometry, box)
    for longitude, latitude in interior:
        factors = projection.get_factors(longitude, latitude)
        error = 100 * max(abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1))
        if error > maximum[0]:
            maximum = (error, longitude, latitude, factors)

    error, lon, lat, factors = maximum
    min_x = min(point[0] for point in projected_boundary)
    min_y = min(point[1] for point in projected_boundary)
    max_x = max(point[0] for point in projected_boundary)
    max_y = max(point[1] for point in projected_boundary)
    root_min = -25_000_000.0
    root_max = 25_000_000.0
    bbox_area = max(0.0, (max_x - min_x) * (max_y - min_y))
    root_area = 50_000_000.0**2
    approval_band = "preferred" if error <= 1 else "conditional" if error <= 2.5 else "reject"
    return {
        "domain_code": code,
        "name": name,
        "status": "candidate-unverified",
        "boundary_file": str(boundary_file.relative_to(ROOT)),
        "boundary_sha256": hashlib.sha256(boundary_file.read_bytes()).hexdigest(),
        "candidate": candidate_name,
        "candidate_note": note,
        "crs_wkt2": crs.to_wkt("WKT2_2019"),
        "proj4": crs.to_proj4(),
        "boundary_sample_count": len(points),
        "interior_sample_count": len(interior),
        "boundary_projected_bounds_m": [min_x, min_y, max_x, max_y],
        "root_covers_boundary": root_min <= min_x and max_x <= root_max and root_min <= min_y and max_y <= root_max,
        "root_bbox_occupancy_pct": 100 * bbox_area / root_area,
        "scale_error_method": "densified_full_boundary_plus_bbox_interior_v2",
        "max_error_pct": error,
        "max_error_coordinate_crs84": [lon, lat],
        "meridional_scale": factors.meridional_scale,
        "parallel_scale": factors.parallel_scale,
        "approval_band": approval_band,
        "equal_area_candidate": "EPSG:8857",
    }


def main() -> None:
    candidate_document = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    records = []
    for domain in candidate_document["domains"]:
        code = domain["domain_code"]
        if code not in PRIORITY_CODES:
            continue
        boundary_file = ROOT / "release" / "boundaries" / f"{code}_full.geojson"
        if not boundary_file.is_file():
            raise FileNotFoundError(boundary_file)
        rings = boundary_rings(boundary_file)
        raw_points = [point for ring in rings for point in ring]
        sampled = sampled_boundary(rings)
        boundary_geometry = load_boundary(boundary_file)
        box = bounds(raw_points)
        for candidate_name, crs, note in candidate_specs(code, box):
            records.append(evaluate_candidate(code, domain["name"], boundary_file, boundary_geometry, sampled, box, candidate_name, crs, note))

    OUTPUT.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# ASEAN priority profile review",
        "",
        "This is a candidate comparison. It is not a signed release.",
        "",
        "| Domain | Candidate | Max sampled scale error | Band | Root covers boundary |",
        "|---|---|---:|---|---|",
    ]
    for record in records:
        lines.append(
            f"| `{record['domain_code']}` | `{record['candidate']}` | "
            f"{record['max_error_pct']:.4f}% | {record['approval_band']} | "
            f"{str(record['root_covers_boundary']).lower()} |"
        )
    lines.extend(
        [
            "",
            "The final profile choice must also review datum, boundary authority, islands, "
            "empty-root ratio, legal scope, and application accuracy requirements.",
            "",
            f"Detailed JSON: [`{OUTPUT.relative_to(ROOT)}`]({OUTPUT.relative_to(ROOT)})",
        ]
    )
    MARKDOWN_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} priority-country candidates: {OUTPUT}")
    print(f"Wrote review table: {MARKDOWN_OUTPUT}")


if __name__ == "__main__":
    main()
