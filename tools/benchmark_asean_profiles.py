#!/usr/bin/env python3
"""Benchmark squareness and consistency for all ASEAN GeoSquare candidates."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median

from pyproj import CRS, Geod, Transformer

from geosquare_v2.codec import cell_side_m
from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.model import DomainProfile

ROOT = Path(__file__).resolve().parents[1]
DOMAIN_CANDIDATES = ROOT / "release" / "profiles" / "ASEAN_DOMAIN_CANDIDATES.json"
INITIAL_CANDIDATES = ROOT / "release" / "scale" / "ASEAN_PROJECTION_CANDIDATES.json"
PRIORITY_REVIEW = ROOT / "release" / "scale" / "ASEAN_PRIORITY_PROFILE_REVIEW.json"
PRIORITY_DECISIONS = ROOT / "release" / "profiles" / "ASEAN_PRIORITY_PROFILE_DECISIONS.json"
OUTPUT = ROOT / "release" / "scale" / "ASEAN_SQUARENESS_BENCHMARK.json"
MARKDOWN_OUTPUT = ROOT / "internal" / "research" / "ASEAN_SQUARENESS_BENCHMARK.md"
LEVEL = 12
MAX_BOUNDARY_SAMPLES = 2_000


def geometry_objects(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return [feature["geometry"] for feature in document.get("features", [])]
    if document.get("type") == "Feature":
        return [document["geometry"]]
    return [document]


def positions(path: Path) -> list[tuple[float, float]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    result: list[tuple[float, float]] = []
    for geometry in geometry_objects(document):
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])
        polygons = [coordinates] if geometry_type == "Polygon" else coordinates
        for polygon in polygons:
            for ring in polygon:
                result.extend((float(point[0]), float(point[1])) for point in ring)
    if not result:
        raise ValueError(f"boundary contains no coordinates: {path}")
    return result


def sample_positions(path: Path) -> list[tuple[float, float]]:
    values = positions(path)
    stride = max(1, math.ceil(len(values) / MAX_BOUNDARY_SAMPLES))
    return values[::stride]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def selected_candidates() -> list[dict]:
    domains = json.loads(DOMAIN_CANDIDATES.read_text(encoding="utf-8"))["domains"]
    initial = json.loads(INITIAL_CANDIDATES.read_text(encoding="utf-8"))
    priority_review = json.loads(PRIORITY_REVIEW.read_text(encoding="utf-8"))
    decisions = json.loads(PRIORITY_DECISIONS.read_text(encoding="utf-8"))["profiles"]
    decision_by_code = {item["domain_code"]: item for item in decisions}
    review_by_key = {
        (item["domain_code"], item["candidate"]): item for item in priority_review
    }
    initial_by_code = {item["domain_code"]: item for item in initial}

    result = []
    for domain in domains:
        code = domain["domain_code"]
        decision = decision_by_code.get(code)
        if decision is not None:
            candidate = review_by_key[(code, decision["recommended_candidate"])]
            boundary_file = ROOT / candidate["boundary_file"]
            result.append(
                {
                    "domain_code": code,
                    "name": domain["name"],
                    "candidate": candidate,
                    "boundary_file": boundary_file,
                    "boundary_resolution": "full",
                }
            )
        else:
            candidate = initial_by_code[code]
            result.append(
                {
                    "domain_code": code,
                    "name": domain["name"],
                    "candidate": candidate,
                    "boundary_file": ROOT / candidate["boundary_file"],
                    "boundary_resolution": "simplified",
                }
            )
    return result


def measure(selected: dict) -> dict:
    candidate = selected["candidate"]
    code = selected["domain_code"]
    profile = DomainProfile(
        domain_id=int(candidate.get("domain_id_candidate", 1)),
        domain_code=code,
        name=selected["name"],
        origin_x_m=-25_000_000.0,
        origin_y_m=-25_000_000.0,
        grid_crs=candidate["crs_wkt2"],
        equal_area_crs="EPSG:8857",
    )
    grid = GeosquareGrid(profile)
    to_grid = Transformer.from_crs("OGC:CRS84", CRS.from_wkt(candidate["crs_wkt2"]), always_xy=True)
    to_wgs84 = Transformer.from_crs(CRS.from_wkt(candidate["crs_wkt2"]), "EPSG:4326", always_xy=True)
    geod = Geod(ellps="WGS84")
    nominal_edge_m = cell_side_m(LEVEL)
    side_lengths: list[float] = []
    side_ratios: list[float] = []
    area_ratios: list[float] = []
    seen_cells: set[tuple[int, int]] = set()
    projected_boundary: list[tuple[float, float]] = []
    skipped = 0

    for longitude, latitude in sample_positions(selected["boundary_file"]):
        try:
            cell = grid.canonical_from_lonlat(longitude, latitude, LEVEL, to_grid)
        except Exception:
            skipped += 1
            continue
        key = (cell.x_idx, cell.y_idx)
        if key in seen_cells:
            continue
        seen_cells.add(key)
        bounds = grid.projected_bounds(cell)
        projected_corners = (
            (bounds.min_x, bounds.min_y),
            (bounds.min_x, bounds.max_y),
            (bounds.max_x, bounds.max_y),
            (bounds.max_x, bounds.min_y),
        )
        for x_m, y_m in projected_corners:
            projected_boundary.append((x_m, y_m))
        corners = [to_wgs84.transform(x_m, y_m) for x_m, y_m in projected_corners]
        lengths = []
        for first, second in zip(corners, corners[1:] + corners[:1]):
            _, _, distance_m = geod.inv(first[0], first[1], second[0], second[1])
            lengths.append(abs(distance_m))
        area_m2, _ = geod.polygon_area_perimeter(
            [point[0] for point in corners],
            [point[1] for point in corners],
        )
        side_lengths.extend(lengths)
        side_ratios.append(max(lengths) / min(lengths))
        area_ratios.append(abs(area_m2) / (nominal_edge_m * nominal_edge_m))

    min_x = min(point[0] for point in projected_boundary)
    min_y = min(point[1] for point in projected_boundary)
    max_x = max(point[0] for point in projected_boundary)
    max_y = max(point[1] for point in projected_boundary)
    root_min = -25_000_000.0
    root_max = 25_000_000.0
    occupancy = ((max_x - min_x) * (max_y - min_y)) / (50_000_000.0**2) * 100
    max_scale_error = float(candidate["max_error_pct"])
    candidate_name = candidate.get("candidate", candidate.get("projection_family", "unknown"))
    approval_band = (
        "preferred" if max_scale_error <= 1 else "conditional" if max_scale_error <= 2.5 else "reject"
    )

    return {
        "domain_code": code,
        "name": selected["name"],
        "candidate": candidate_name,
        "boundary_file": str(selected["boundary_file"].relative_to(ROOT)),
        "boundary_resolution": selected["boundary_resolution"],
        "level": LEVEL,
        "nominal_grid_edge_m": nominal_edge_m,
        "sampled_unique_cells": len(seen_cells),
        "skipped_boundary_points": skipped,
        "published_or_candidate_scale_error_pct": max_scale_error,
        "approval_band": approval_band,
        "root_covers_sampled_boundary": root_min <= min_x and max_x <= root_max and root_min <= min_y and max_y <= root_max,
        "root_bbox_occupancy_pct": occupancy,
        "ground_side_m": {
            "min": min(side_lengths),
            "p05": percentile(side_lengths, 0.05),
            "median": median(side_lengths),
            "p95": percentile(side_lengths, 0.95),
            "max": max(side_lengths),
        },
        "squareness_side_ratio": {
            "median": median(side_ratios),
            "p95": percentile(side_ratios, 0.95),
            "max": max(side_ratios),
            "max_error_pct": (max(side_ratios) - 1) * 100,
        },
        "ground_area_ratio": {
            "min": min(area_ratios),
            "p05": percentile(area_ratios, 0.05),
            "median": median(area_ratios),
            "p95": percentile(area_ratios, 0.95),
            "max": max(area_ratios),
            "max_absolute_error_pct": max(abs(value - 1) for value in area_ratios) * 100,
        },
    }


def main() -> None:
    records = [measure(item) for item in selected_candidates()]
    OUTPUT.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# ASEAN GeoSquare squareness benchmark",
        "",
        "Level 12 is the nominal 50 m cell. Results use sampled boundary points and the selected candidate CRS for each country.",
        "",
        "| Domain | Candidate | Boundary | Side error max | Ground side p05–p95 | Area ratio p05–p95 | Scale error | Band |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for record in records:
        sides = record["ground_side_m"]
        areas = record["ground_area_ratio"]
        lines.append(
            f"| `{record['domain_code']}` | `{record['candidate']}` | {record['boundary_resolution']} | "
            f"{record['squareness_side_ratio']['max_error_pct']:.4f}% | "
            f"{sides['p05']:.2f}–{sides['p95']:.2f} m | "
            f"{areas['p05']:.4f}–{areas['p95']:.4f} | "
            f"{record['published_or_candidate_scale_error_pct']:.4f}% | {record['approval_band']} |"
        )
    lines.extend(
        [
            "",
            "Side error is `(longest side / shortest side - 1) × 100`.",
            "Area ratio is geodesic ground area divided by the nominal 50 m × 50 m grid area.",
            "These are candidate measurements, not final profile approval.",
            "",
            f"Detailed JSON: [`{OUTPUT.relative_to(ROOT)}`]({OUTPUT.relative_to(ROOT)})",
        ]
    )
    MARKDOWN_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(records)} ASEAN benchmark records: {OUTPUT}")
    print(f"Wrote report: {MARKDOWN_OUTPUT}")


if __name__ == "__main__":
    main()
