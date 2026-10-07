#!/usr/bin/env python3
"""Evaluate first-pass ASEAN grid CRS candidates from simplified boundaries.

This creates planning metadata only. It does not create signed ReleaseProfiles and does
not approve a boundary or projection for production use.
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
BOUNDARIES = ROOT / "release" / "boundaries"
OUTPUT = ROOT / "release" / "scale" / "ASEAN_PROJECTION_CANDIDATES.json"


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
            yield [(float(position[0]), float(position[1])) for position in ring]


def boundary_rings(path: Path) -> list[list[tuple[float, float]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") == "FeatureCollection":
        geometries = [feature["geometry"] for feature in document.get("features", [])]
    elif document.get("type") == "Feature":
        geometries = [document["geometry"]]
    else:
        geometries = [document]
    rings = [ring for geometry in geometries for ring in rings_from_geometry(geometry)]
    if not rings:
        raise ValueError(f"boundary contains no polygon rings: {path}")
    return rings


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


def densified_boundary(
    rings: list[list[tuple[float, float]]],
    max_samples: int = 20_000,
) -> list[tuple[float, float]]:
    total_vertices = sum(len(ring) for ring in rings)
    stride = max(1, math.ceil(total_vertices / max_samples))
    result: list[tuple[float, float]] = []
    for ring in rings:
        sampled_ring = ring[::stride]
        if ring and sampled_ring[-1] != ring[-1]:
            sampled_ring.append(ring[-1])
        for index, first in enumerate(sampled_ring):
            second = sampled_ring[(index + 1) % len(sampled_ring)]
            result.extend(densify_segment(first, second))
    return result


def bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    longitudes = [point[0] for point in points]
    latitudes = [point[1] for point in points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def candidate_proj4(domain_code: str, bounds: tuple[float, float, float, float], family: str) -> str:
    min_lon, min_lat, max_lon, max_lat = bounds
    lon_0 = (min_lon + max_lon) / 2
    lat_0 = (min_lat + max_lat) / 2
    if family in {"EQC_OR_BROAD_LCC", "EXISTING_SRGI2013_EQC"}:
        return (
            f"+proj=eqc +lat_ts=0 +lat_0=0 +lon_0={lon_0} "
            "+datum=WGS84 +units=m +type=crs"
        )
    if family == "LOCAL_PROJECTED":
        return (
            f"+proj=tmerc +lat_0={lat_0} +lon_0={lon_0} +k=1 "
            "+x_0=0 +y_0=0 +datum=WGS84 +units=m +type=crs"
        )
    span = max_lat - min_lat
    first_parallel = min_lat + span / 6
    second_parallel = max_lat - span / 6
    if first_parallel == second_parallel:
        first_parallel -= 0.1
        second_parallel += 0.1
    return (
        f"+proj=lcc +lat_1={first_parallel} +lat_2={second_parallel} "
        f"+lat_0={lat_0} +lon_0={lon_0} +x_0=0 +y_0=0 "
        "+datum=WGS84 +units=m +type=crs"
    )


def scale_record(
    domain: dict,
    boundary_file: Path,
    points: list[tuple[float, float]],
    boundary_hash: str,
    crs: CRS,
    proj4: str,
) -> dict:
    projection = pyproj.Proj(crs)
    transformer = Transformer.from_crs("OGC:CRS84", crs, always_xy=True)
    maximum = (-1.0, None, None, None)
    projected = []
    for longitude, latitude in points:
        factors = projection.get_factors(longitude, latitude)
        error = 100 * max(abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1))
        if error > maximum[0]:
            maximum = (error, longitude, latitude, factors)
        projected.append(transformer.transform(longitude, latitude))

    error, lon, lat, factors = maximum
    min_x = min(point[0] for point in projected)
    min_y = min(point[1] for point in projected)
    max_x = max(point[0] for point in projected)
    max_y = max(point[1] for point in projected)
    root_min = -25_000_000.0
    root_max = 25_000_000.0
    return {
        "domain_id_candidate": domain["domain_id_candidate"],
        "domain_code": domain["domain_code"],
        "name": domain["name"],
        "iso3": domain["iso3"],
        "status": "candidate-unverified",
        "boundary_file": str(boundary_file.relative_to(ROOT)),
        "boundary_sha256": boundary_hash,
        "boundary_sample_count": len(points),
        "projection_family": domain["grid_candidate"],
        "proj4": proj4,
        "crs_wkt2": crs.to_wkt("WKT2_2019"),
        "root_side_m": 50_000_000.0,
        "boundary_projected_bounds_m": [min_x, min_y, max_x, max_y],
        "root_covers_sampled_boundary": root_min <= min_x and max_x <= root_max and root_min <= min_y and max_y <= root_max,
        "scale_error_method": "densified_simplified_boundary_vertices_v1",
        "sample_count": len(points),
        "max_error_pct": error,
        "max_error_coordinate_crs84": [lon, lat],
        "meridional_scale": factors.meridional_scale,
        "parallel_scale": factors.parallel_scale,
        "equal_area_candidate": "EPSG:8857",
        "review_note": "Candidate only. Re-evaluate with final boundary, interior samples, legal scope, and profile review.",
    }


def main() -> None:
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    records = []
    for domain in candidates["domains"]:
        boundary_file = ROOT / domain["boundary_file"]
        rings = boundary_rings(boundary_file)
        raw_points = [point for ring in rings for point in ring]
        points = densified_boundary(rings, max_samples=10_000)
        bounds = bbox(raw_points)

        if domain["grid_candidate"].startswith("EXISTING_"):
            profile = json.loads((ROOT / "release" / "profiles" / f"{domain['domain_code']}.v2.json").read_text(encoding="utf-8"))
            crs = CRS.from_wkt(profile["crs_wkt2"])
            proj4 = crs.to_proj4()
        else:
            proj4 = candidate_proj4(domain["domain_code"], bounds, domain["grid_candidate"])
            crs = CRS.from_proj4(proj4)

        records.append(
            scale_record(
                domain,
                boundary_file,
                points,
                hashlib.sha256(boundary_file.read_bytes()).hexdigest(),
                crs,
                proj4,
            )
        )

    OUTPUT.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} ASEAN projection candidates: {OUTPUT}")


if __name__ == "__main__":
    main()
