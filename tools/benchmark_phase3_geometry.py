#!/usr/bin/env python3
"""Run the reproducible Phase 3 GeoSquare geometry benchmark.

Phase 3 deliberately writes new artifacts under ``release/scale/phase3``. It
uses every full ASEAN boundary, deterministic boundary densification, and a
seeded interior rejection sampler. The Phase 2 benchmark artifacts remain
unchanged and provide the raw-vertex baseline for comparison.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable

import pyproj
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from geosquare_v2.codec import cell_side_m
from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.release import ReleaseProfile

ROOT = Path(__file__).resolve().parents[1]
PHASE3_DIR = ROOT / "release" / "scale" / "phase3"
REPORT_PATH = ROOT / "internal" / "research" / "PHASE3_SCALE_AND_SQUARENESS.md"
MANIFEST_PATH = PHASE3_DIR / "PHASE3_RUN_MANIFEST.json"
OUTPUT_PATH = PHASE3_DIR / "ASEAN_LEVEL12_BENCHMARK.json"
BOUNDARY_METADATA_PATH = ROOT / "release" / "boundaries" / "ASEAN_BOUNDARY_METADATA.json"
DOMAIN_CANDIDATES_PATH = ROOT / "release" / "profiles" / "ASEAN_DOMAIN_CANDIDATES.json"
PRIORITY_DECISIONS_PATH = ROOT / "release" / "profiles" / "ASEAN_PRIORITY_PROFILE_DECISIONS.json"
LEVEL = 12
INTERIOR_COUNT = 2_048
BASE_SEED = 2_026_0301
MAX_SOURCE_VERTICES = 20_000
MAX_SEGMENT_DEGREES = 0.5
MAX_SEGMENT_PARTS = 25
DOMAIN_CODES = ("BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN")
GEOD = Geod(ellps="WGS84")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def geometry_objects(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return [feature["geometry"] for feature in document.get("features", [])]
    if document.get("type") == "Feature":
        return [document["geometry"]]
    return [document]


def rings_from_geometry(geometry: dict) -> Iterable[list[tuple[float, float]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        for ring in coordinates:
            yield [(float(point[0]), float(point[1])) for point in ring]
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                yield [(float(point[0]), float(point[1])) for point in ring]


def load_boundary(path: Path) -> tuple[object, list[list[tuple[float, float]]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    geometries = geometry_objects(document)
    polygons = [shape(geometry) for geometry in geometries]
    boundary_geometry = unary_union(polygons)
    rings: list[list[tuple[float, float]]] = []
    for geometry in geometries:
        rings.extend(rings_from_geometry(geometry))
    if not rings or boundary_geometry.is_empty:
        raise ValueError(f"boundary contains no usable geometry: {path}")
    return boundary_geometry, rings


def sampled_source_rings(
    rings: list[list[tuple[float, float]]],
) -> tuple[list[list[tuple[float, float]]], int, int]:
    source_vertex_count = sum(max(0, len(ring) - 1) for ring in rings)
    cores = [
        ring[:-1] if ring and ring[0] == ring[-1] else ring
        for ring in rings
    ]
    cores = [core for core in cores if len(core) >= 3]
    stride = max(1, (source_vertex_count + MAX_SOURCE_VERTICES - 1) // MAX_SOURCE_VERTICES)

    def selected_count(core: list[tuple[float, float]], current_stride: int) -> int:
        return min(len(core), max(3, len(core[::current_stride])))

    while (
        sum(selected_count(core, stride) for core in cores) > MAX_SOURCE_VERTICES
        and stride < max((len(core) for core in cores), default=1)
    ):
        stride += 1

    sampled: list[list[tuple[float, float]]] = []
    sampled_vertex_count = 0
    for core in cores:
        selected = core[::stride]
        if len(selected) < 3:
            selected = core[:3]
        selected_ring = selected + [selected[0]]
        sampled.append(selected_ring)
        sampled_vertex_count += len(selected)
    return sampled, source_vertex_count, sampled_vertex_count


def densify_ring(
    ring: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    core = ring[:-1] if ring and ring[0] == ring[-1] else ring
    output: list[tuple[float, float]] = []
    for index, start in enumerate(core):
        end = core[(index + 1) % len(core)]
        delta = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
        parts = max(1, min(MAX_SEGMENT_PARTS, int(delta / MAX_SEGMENT_DEGREES) + (delta % MAX_SEGMENT_DEGREES > 0)))
        for part in range(parts):
            fraction = part / parts
            point = (
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            )
            if not output or point != output[-1]:
                output.append(point)
    if output and output[0] != output[-1]:
        output.append(output[0])
    return output


def densified_boundary_points(
    rings: list[list[tuple[float, float]]],
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for ring in rings:
        points.extend(densify_ring(ring))
    return points


def interior_points(
    geometry: object,
    seed: int,
    count: int = INTERIOR_COUNT,
) -> tuple[list[tuple[float, float]], int]:
    min_x, min_y, max_x, max_y = geometry.bounds
    rng = random.Random(seed)
    points: list[tuple[float, float]] = []
    attempts = 0
    max_attempts = max(1_000_000, count * 5_000)
    while len(points) < count and attempts < max_attempts:
        attempts += 1
        longitude = rng.uniform(min_x, max_x)
        latitude = rng.uniform(min_y, max_y)
        if geometry.covers(Point(longitude, latitude)):
            points.append((longitude, latitude))
    if len(points) != count:
        raise RuntimeError(
            f"interior sampler accepted {len(points)} of {count} points after {attempts} attempts"
        )
    return points, attempts


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def point_hash(points: list[tuple[float, float]]) -> str:
    return canonical_hash([[longitude, latitude] for longitude, latitude in points])


def panel_boundary_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    if len(points) <= INTERIOR_COUNT:
        return points
    return [
        points[round(index * (len(points) - 1) / (INTERIOR_COUNT - 1))]
        for index in range(INTERIOR_COUNT)
    ]


def boundary_metadata() -> dict[str, dict]:
    records = json.loads(BOUNDARY_METADATA_PATH.read_text(encoding="utf-8"))
    return {record["domain_code"]: record for record in records}


def candidate_statuses() -> dict[str, dict]:
    result: dict[str, dict] = {}
    candidates = json.loads(DOMAIN_CANDIDATES_PATH.read_text(encoding="utf-8"))
    for domain in candidates.get("domains", []):
        result[domain["domain_code"]] = {
            "candidate_status": candidates.get("status", "candidate-unverified"),
            "name": domain["name"],
        }
    if PRIORITY_DECISIONS_PATH.is_file():
        for decision in json.loads(PRIORITY_DECISIONS_PATH.read_text(encoding="utf-8")).get("profiles", []):
            code = decision.get("domain_code")
            if code in result:
                result[code]["approval_status"] = decision.get("approval_status", decision.get("status", "review-required"))
                result[code]["recommended_candidate"] = decision.get("recommended_candidate")
    return result


def metric_summary(
    profile: ReleaseProfile,
    points: list[tuple[float, float]],
    transformer: Transformer,
) -> dict:
    grid = GeosquareGrid(profile)
    to_wgs84 = Transformer.from_crs(
        CRS.from_user_input(profile.crs_wkt2), CRS.from_epsg(4326), always_xy=True
    )
    nominal_edge_m = cell_side_m(LEVEL)
    seen: set[tuple[int, int]] = set()
    side_lengths: list[float] = []
    side_ratios: list[float] = []
    area_ratios: list[float] = []
    projected_points: list[tuple[float, float]] = []
    skipped = 0

    for longitude, latitude in points:
        try:
            cell = grid.canonical_from_lonlat(longitude, latitude, LEVEL, transformer)
        except Exception:
            skipped += 1
            continue
        projected_x, projected_y = transformer.transform(longitude, latitude)
        projected_points.append((projected_x, projected_y))
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
        lengths: list[float] = []
        for first, second in zip(corners, corners[1:] + corners[:1]):
            _, _, distance = GEOD.inv(first[0], first[1], second[0], second[1])
            lengths.append(abs(distance))
        area, perimeter = GEOD.polygon_area_perimeter(
            [point[0] for point in corners], [point[1] for point in corners]
        )
        area = abs(area)
        side_lengths.extend(lengths)
        side_ratios.append(max(lengths) / min(lengths))
        area_ratios.append(area / (nominal_edge_m * nominal_edge_m))

    root_min = profile.origin_x_m
    root_max = profile.origin_x_m + profile.root_side_m
    root_covered = bool(projected_points) and all(
        root_min <= coordinate <= root_max
        for point in projected_points
        for coordinate in point
    )
    if not side_ratios:
        raise RuntimeError(f"no valid cells produced for {profile.domain_code}")

    return {
        "raw_point_count": len(points),
        "unique_cell_count": len(seen),
        "skipped_points": skipped,
        "root_covers_sampled_points": root_covered,
        "ground_side_m": {
            "min": min(side_lengths),
            "p05": percentile(side_lengths, 0.05),
            "median": median(side_lengths),
            "p95": percentile(side_lengths, 0.95),
            "max": max(side_lengths),
        },
        "side_anisotropy": {
            "median": median(side_ratios),
            "p95": percentile(side_ratios, 0.95),
            "max": max(side_ratios),
            "max_error_pct": (max(side_ratios) - 1.0) * 100.0,
        },
        "ground_area_ratio": {
            "min": min(area_ratios),
            "p05": percentile(area_ratios, 0.05),
            "median": median(area_ratios),
            "p95": percentile(area_ratios, 0.95),
            "max": max(area_ratios),
            "max_absolute_error_pct": max(abs(value - 1.0) for value in area_ratios) * 100.0,
        },
    }


def software_metadata() -> dict:
    try:
        import shapely

        shapely_version = shapely.__version__
    except ImportError:
        shapely_version = "unavailable"
    try:
        import h3

        h3_version = getattr(h3, "__version__", "unknown")
    except ImportError:
        h3_version = "unavailable"
    try:
        import s2sphere

        s2_version = getattr(s2sphere, "__version__", "unknown")
    except ImportError:
        s2_version = "unavailable"
    proj_db = Path(pyproj.datadir.get_data_dir()) / "proj.db"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "proj_db_sha256": sha256_path(proj_db) if proj_db.is_file() else "unavailable",
        "shapely": shapely_version,
        "h3": h3_version,
        "s2sphere": s2_version,
    }


def run_domain(
    code: str,
    ordinal: int,
    boundary_info: dict[str, dict],
    statuses: dict[str, dict],
) -> dict:
    boundary_path = ROOT / "release" / "boundaries" / f"{code}_full.geojson"
    profile_path = ROOT / "release" / "profiles" / f"{code}.v2.json"
    if not boundary_path.is_file() or not profile_path.is_file():
        raise FileNotFoundError(f"missing Phase 3 input for {code}")

    geometry, source_rings = load_boundary(boundary_path)
    sampled_rings, source_vertex_count, sampled_vertex_count = sampled_source_rings(source_rings)
    boundary_points = densified_boundary_points(sampled_rings)
    seed = BASE_SEED + ordinal
    interior, attempts = interior_points(geometry, seed)
    combined_points = boundary_points + interior
    profile_data = json.loads(profile_path.read_text(encoding="utf-8"))
    profile = ReleaseProfile(**profile_data)
    to_grid = Transformer.from_crs(
        CRS.from_epsg(4326), CRS.from_user_input(profile.crs_wkt2), always_xy=True
    )
    metrics = metric_summary(profile, combined_points, to_grid)
    metadata = boundary_info[code]
    status = statuses.get(code, {})
    boundary_sha = sha256_path(boundary_path)
    profile_sha = sha256_path(profile_path)
    return {
        "domain_code": code,
        "name": profile.name,
        "iso3": metadata["iso3"],
        "candidate": profile.crs_authority,
        "candidate_status": status.get("candidate_status", "candidate-unverified"),
        "approval_status": status.get("approval_status", "review-required"),
        "recommended_candidate": status.get("recommended_candidate"),
        "profile_version": profile.profile_version,
        "profile_path": str(profile_path.relative_to(ROOT)),
        "profile_sha256": profile_sha,
        "wkt2_sha256": sha256_bytes(profile.crs_wkt2.encode("utf-8")),
        "reference_epoch": profile.reference_epoch,
        "grid_crs_authority": profile.crs_authority,
        "equal_area_crs_authority": profile.equal_area_crs_authority,
        "published_candidate_scale_error_pct": profile.scale_error_max_pct,
        "boundary_path": str(boundary_path.relative_to(ROOT)),
        "boundary_source_url": metadata["api_url"],
        "boundary_id": metadata["boundary_id"],
        "boundary_year": metadata["boundary_year"],
        "boundary_license": metadata["boundary_license"],
        "boundary_sha256": boundary_sha,
        "boundary_metadata_sha256": metadata.get("full_sha256"),
        "sampling": {
            "source_vertex_count": source_vertex_count,
            "source_vertex_cap": MAX_SOURCE_VERTICES,
            "source_stride": max(1, (source_vertex_count + MAX_SOURCE_VERTICES - 1) // MAX_SOURCE_VERTICES),
            "sampled_source_vertex_count": sampled_vertex_count,
            "densified_boundary_point_count": len(boundary_points),
            "densification_max_segment_degrees": MAX_SEGMENT_DEGREES,
            "densification_max_segment_parts": MAX_SEGMENT_PARTS,
            "interior_algorithm": "seeded_uniform_bbox_rejection_with_geometry_covers",
            "interior_seed": seed,
            "interior_requested_count": INTERIOR_COUNT,
            "interior_accepted_count": len(interior),
            "interior_attempt_count": attempts,
            "boundary_point_set_sha256": point_hash(boundary_points),
            "interior_point_set_sha256": point_hash(interior),
            "combined_point_set_sha256": point_hash(combined_points),
        },
        "level": LEVEL,
        "nominal_grid_edge_m": cell_side_m(LEVEL),
        "metrics": metrics,
    }


def write_report(output: dict) -> None:
    lines = [
        "# Phase 3 scale and squareness benchmark",
        "",
        "This benchmark uses full ASEAN boundaries, deterministic boundary densification, and seeded interior sampling. It is a candidate-profile measurement, not geodetic or boundary approval.",
        "",
        f"- Run ID: `{output['run_id']}`",
        f"- Repository commit: `{output['repository_commit']}`",
        f"- Level: `{LEVEL}` (nominal 50 m)",
        f"- Interior points per domain: `{INTERIOR_COUNT}`",
        f"- Base seed: `{BASE_SEED}`; domain seed is base plus the 1-based ASEAN ordinal",
        "",
        "| Domain | Boundary points | Interior points | Unique cells | Side error max | Area ratio p05–p95 | Max area error | Approval status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for record in output["domains"]:
        sampling = record["sampling"]
        metrics = record["metrics"]
        side = metrics["side_anisotropy"]
        area = metrics["ground_area_ratio"]
        lines.append(
            f"| `{record['domain_code']}` | {sampling['densified_boundary_point_count']} | {sampling['interior_accepted_count']} | "
            f"{metrics['unique_cell_count']} | {side['max_error_pct']:.6f}% | "
            f"{area['p05']:.6f}–{area['p95']:.6f} | {area['max_absolute_error_pct']:.4f}% | "
            f"{record['approval_status']} |"
        )
    lines.extend(
        [
            "",
            "Side error is `(longest geodesic edge / shortest geodesic edge - 1) × 100` over unique Level-12 cells reached by the combined point set.",
            "Area ratio is geodesic ground area divided by the nominal 50 m × 50 m grid area.",
            "The profile's published candidate scale error is retained separately from geodesic cell side anisotropy.",
            "",
            f"Detailed JSON: [`{OUTPUT_PATH.relative_to(ROOT)}`](../../release/scale/phase3/{OUTPUT_PATH.name})",
            f"Run manifest: [`{MANIFEST_PATH.relative_to(ROOT)}`](../../release/scale/phase3/{MANIFEST_PATH.name})",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    PHASE3_DIR.mkdir(parents=True, exist_ok=True)
    started = utc_now()
    boundary_info = boundary_metadata()
    statuses = candidate_statuses()
    domains = [
        run_domain(code, ordinal, boundary_info, statuses)
        for ordinal, code in enumerate(DOMAIN_CODES, start=1)
    ]
    output = {
        "schema_version": "phase3.geometry.v1",
        "phase": "phase3",
        "run_id": "phase3-" + started.replace("-", "").replace(":", "").replace("+00:00", "Z"),
        "generated_at_utc": started,
        "repository_commit": git_commit(),
        "software": software_metadata(),
        "sampling_protocol": {
            "boundary_source": "full bundled ASEAN GeoBoundaries files",
            "boundary_crs": "OGC:CRS84",
            "boundary_densification": "source rings sampled under a 20,000-vertex cap; each segment split at <=0.5 degrees and <=25 parts",
            "interior_sampling": "uniform bounding-box rejection sampling accepted with Shapely geometry.covers",
            "interior_count": INTERIOR_COUNT,
            "base_seed": BASE_SEED,
            "seed_rule": "base seed plus 1-based ASEAN domain ordinal",
            "metrics_use": "combined densified-boundary and interior points, deduplicated by canonical Level-12 cell",
        },
        "domains": domains,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(output)
    manifest = {
        "schema_version": "phase3.manifest.v1",
        "phase": "phase3",
        "run_id": output["run_id"],
        "generated_at_utc": started,
        "repository_commit": output["repository_commit"],
        "software": output["software"],
        "inputs": {
            "boundary_metadata": str(BOUNDARY_METADATA_PATH.relative_to(ROOT)),
            "domain_candidates": str(DOMAIN_CANDIDATES_PATH.relative_to(ROOT)),
            "priority_decisions": str(PRIORITY_DECISIONS_PATH.relative_to(ROOT)),
            "boundary_metadata_sha256": sha256_path(BOUNDARY_METADATA_PATH),
        },
        "outputs": {
            "benchmark_json": str(OUTPUT_PATH.relative_to(ROOT)),
            "benchmark_json_sha256": sha256_path(OUTPUT_PATH),
            "report_markdown": str(REPORT_PATH.relative_to(ROOT)),
            "report_markdown_sha256": sha256_path(REPORT_PATH),
        },
        "sampling_protocol": output["sampling_protocol"],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_report(output)
    print(f"Wrote Phase 3 benchmark: {OUTPUT_PATH}")
    print(f"Wrote Phase 3 manifest: {MANIFEST_PATH}")
    print(f"Wrote Phase 3 report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
