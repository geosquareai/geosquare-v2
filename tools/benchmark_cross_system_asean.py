#!/usr/bin/env python3
"""Compare GeoSquare, S2, H3, geohash, and Web Mercator across ASEAN."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median

import h3
from pyproj import CRS, Geod, Transformer
from s2sphere import Cell, CellId, LatLng


ROOT = Path(__file__).resolve().parents[1]
DOMAIN_CANDIDATES = ROOT / "release" / "profiles" / "ASEAN_DOMAIN_CANDIDATES.json"
INITIAL_CANDIDATES = ROOT / "release" / "scale" / "ASEAN_PROJECTION_CANDIDATES.json"
PRIORITY_REVIEW = ROOT / "release" / "scale" / "ASEAN_PRIORITY_PROFILE_REVIEW.json"
PRIORITY_DECISIONS = ROOT / "release" / "profiles" / "ASEAN_PRIORITY_PROFILE_DECISIONS.json"
OUTPUT = ROOT / "release" / "scale" / "ASEAN_CROSS_SYSTEM_BENCHMARK.json"
MARKDOWN_OUTPUT = ROOT / "internal" / "research" / "ASEAN_CROSS_SYSTEM_BENCHMARK.md"
TARGET_AREA_M2 = 50.0 * 50.0
MAX_SAMPLES = 100
GEOD = Geod(ellps="WGS84")
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def geometry_objects(document: dict) -> list[dict]:
    if document.get("type") == "FeatureCollection":
        return [feature["geometry"] for feature in document.get("features", [])]
    if document.get("type") == "Feature":
        return [document["geometry"]]
    return [document]


def boundary_positions(path: Path) -> list[tuple[float, float]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    values: list[tuple[float, float]] = []
    for geometry in geometry_objects(document):
        geometry_type = geometry.get("type")
        polygons = [geometry.get("coordinates", [])] if geometry_type == "Polygon" else geometry.get("coordinates", [])
        for polygon in polygons:
            for ring in polygon:
                values.extend((float(point[0]), float(point[1])) for point in ring)
    return values


def sample_positions(path: Path) -> list[tuple[float, float]]:
    values = boundary_positions(path)
    stride = max(1, math.ceil(len(values) / MAX_SAMPLES))
    return values[::stride]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * fraction)))
    return ordered[index]


def polygon_metrics(corners: list[tuple[float, float]]) -> dict[str, float]:
    lengths = []
    for first, second in zip(corners, corners[1:] + corners[:1]):
        _, _, distance = GEOD.inv(first[0], first[1], second[0], second[1])
        lengths.append(abs(distance))
    area, perimeter = GEOD.polygon_area_perimeter(
        [point[0] for point in corners],
        [point[1] for point in corners],
    )
    area = abs(area)
    return {
        "area_m2": area,
        "side_min_m": min(lengths),
        "side_max_m": max(lengths),
        "side_ratio": max(lengths) / min(lengths),
        "compactness": 4 * math.pi * area / (perimeter * perimeter),
        "edge_count": float(len(corners)),
    }


def summarise(metrics: list[dict[str, float]], resolution: str | int) -> dict:
    areas = [item["area_m2"] for item in metrics]
    side_ratios = [item["side_ratio"] for item in metrics]
    compactions = [item["compactness"] for item in metrics]
    edges = [item["edge_count"] for item in metrics]
    return {
        "resolution": resolution,
        "sample_count": len(metrics),
        "area_m2": {
            "p05": percentile(areas, 0.05),
            "median": median(areas),
            "p95": percentile(areas, 0.95),
            "min": min(areas),
            "max": max(areas),
            "max_absolute_error_pct": max(abs(area / TARGET_AREA_M2 - 1) for area in areas) * 100,
        },
        "side_m": {
            "p05": percentile([item["side_min_m"] for item in metrics], 0.05),
            "median": median([item["side_min_m"] for item in metrics]),
            "p95": percentile([item["side_max_m"] for item in metrics], 0.95),
            "max": max(item["side_max_m"] for item in metrics),
        },
        "side_anisotropy": {
            "median": median(side_ratios),
            "p95": percentile(side_ratios, 0.95),
            "max": max(side_ratios),
            "max_error_pct": (max(side_ratios) - 1) * 100,
        },
        "compactness": {
            "median": median(compactions),
            "p05": percentile(compactions, 0.05),
            "p95": percentile(compactions, 0.95),
        },
        "edge_count": {"min": min(edges), "max": max(edges)},
    }


def geohash_encode(latitude: float, longitude: float, length: int) -> str:
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    even = True
    bits = 0
    characters: list[str] = []
    for _ in range(length * 5):
        if even:
            value = longitude
            interval = lon_range
        else:
            value = latitude
            interval = lat_range
        midpoint = (interval[0] + interval[1]) / 2
        bits = (bits << 1) | int(value >= midpoint)
        if value >= midpoint:
            interval[0] = midpoint
        else:
            interval[1] = midpoint
        even = not even
        if len(characters) * 5 + 5 == (_ + 1):
            characters.append(GEOHASH_ALPHABET[bits])
            bits = 0
    return "".join(characters)


def geohash_bounds(value: str) -> tuple[float, float, float, float]:
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    even = True
    for character in value:
        bits = GEOHASH_ALPHABET.index(character)
        for mask in (16, 8, 4, 2, 1):
            if even:
                interval = lon_range
            else:
                interval = lat_range
            midpoint = (interval[0] + interval[1]) / 2
            if bits & mask:
                interval[0] = midpoint
            else:
                interval[1] = midpoint
            even = not even
    return lon_range[0], lat_range[0], lon_range[1], lat_range[1]


def rectangle_corners(bounds: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = bounds
    return [(min_lon, min_lat), (max_lon, min_lat), (max_lon, max_lat), (min_lon, max_lat)]


def choose_geohash(latitude: float, longitude: float) -> tuple[int, str]:
    candidates = []
    for length in range(1, 13):
        value = geohash_encode(latitude, longitude, length)
        metrics = polygon_metrics(rectangle_corners(geohash_bounds(value)))
        candidates.append((abs(math.log(metrics["area_m2"] / TARGET_AREA_M2)), length, value))
    _, length, value = min(candidates)
    return length, value


def choose_h3(latitude: float, longitude: float) -> tuple[int, str]:
    choices = []
    for resolution in range(16):
        average_area = h3.average_hexagon_area(resolution, unit="m^2")
        choices.append((abs(math.log(average_area / TARGET_AREA_M2)), resolution))
    _, resolution = min(choices)
    return resolution, h3.latlng_to_cell(latitude, longitude, resolution)


def s2_corners(latitude: float, longitude: float, level: int) -> list[tuple[float, float]]:
    cell_id = CellId.from_lat_lng(LatLng.from_degrees(latitude, longitude)).parent(level)
    cell = Cell(cell_id)
    return [
        (
            LatLng.from_point(cell.get_vertex(index)).lng().degrees,
            LatLng.from_point(cell.get_vertex(index)).lat().degrees,
        )
        for index in range(4)
    ]


def choose_s2(latitude: float, longitude: float) -> tuple[int, list[tuple[float, float]]]:
    choices = []
    for level in range(31):
        metrics = polygon_metrics(s2_corners(latitude, longitude, level))
        choices.append((abs(math.log(metrics["area_m2"] / TARGET_AREA_M2)), level, metrics))
    _, level, _ = min(choices)
    return level, s2_corners(latitude, longitude, level)


def web_mercator_corners(latitude: float, longitude: float) -> list[tuple[float, float]]:
    to_mercator = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    x, y = to_mercator.transform(longitude, latitude)
    half = 25.0
    return [
        to_wgs84.transform(x - half, y - half),
        to_wgs84.transform(x + half, y - half),
        to_wgs84.transform(x + half, y + half),
        to_wgs84.transform(x - half, y + half),
    ]


def load_selected_candidates() -> list[dict]:
    domains = json.loads(DOMAIN_CANDIDATES.read_text(encoding="utf-8"))["domains"]
    initial = {item["domain_code"]: item for item in json.loads(INITIAL_CANDIDATES.read_text(encoding="utf-8"))}
    priority = json.loads(PRIORITY_REVIEW.read_text(encoding="utf-8"))
    decisions = json.loads(PRIORITY_DECISIONS.read_text(encoding="utf-8"))["profiles"]
    priority_by_key = {(item["domain_code"], item["candidate"]): item for item in priority}
    decisions_by_code = {item["domain_code"]: item for item in decisions}
    result = []
    for domain in domains:
        code = domain["domain_code"]
        decision = decisions_by_code.get(code)
        if decision:
            candidate = priority_by_key[(code, decision["recommended_candidate"])]
            boundary = ROOT / candidate["boundary_file"]
            if not boundary.is_file():
                boundary = ROOT / "release" / candidate["boundary_file"]
            source = "full"
        else:
            candidate = initial[code]
            boundary = ROOT / candidate["boundary_file"]
            if not boundary.is_file():
                boundary = ROOT / "release" / candidate["boundary_file"]
            source = "simplified"
        result.append((code, domain["name"], candidate, boundary, source))
    return result


def geosquare_metrics(candidate: dict, points: list[tuple[float, float]]) -> dict:
    from geosquare_v2.codec import cell_side_m
    from geosquare_v2.model import DomainProfile
    from geosquare_v2.grid import GeosquareGrid

    profile = DomainProfile(
        domain_id=int(candidate.get("domain_id_candidate", 1)),
        domain_code=candidate["domain_code"],
        name=candidate["name"],
        origin_x_m=-25_000_000.0,
        origin_y_m=-25_000_000.0,
        grid_crs=candidate["crs_wkt2"],
        equal_area_crs="EPSG:8857",
    )
    grid = GeosquareGrid(profile)
    to_grid = Transformer.from_crs("EPSG:4326", CRS.from_wkt(candidate["crs_wkt2"]), always_xy=True)
    to_wgs84 = Transformer.from_crs(CRS.from_wkt(candidate["crs_wkt2"]), "EPSG:4326", always_xy=True)
    seen: set[tuple[int, int]] = set()
    values = []
    for latitude, longitude in points:
        cell = grid.canonical_from_lonlat(longitude, latitude, 12, to_grid)
        if (cell.x_idx, cell.y_idx) in seen:
            continue
        seen.add((cell.x_idx, cell.y_idx))
        bounds = grid.projected_bounds(cell)
        projected = [(bounds.min_x, bounds.min_y), (bounds.max_x, bounds.min_y), (bounds.max_x, bounds.max_y), (bounds.min_x, bounds.max_y)]
        values.append(polygon_metrics([to_wgs84.transform(x, y) for x, y in projected]))
    return summarise(values, 12)


def main() -> None:
    systems = []
    records = []
    for code, name, candidate, boundary, boundary_source in load_selected_candidates():
        sample = sample_positions(boundary)
        points = [(latitude, longitude) for longitude, latitude in sample]
        systems_for_country = {
            "geosquare": geosquare_metrics(candidate, points),
        }

        h3_resolution, _ = choose_h3(points[0][0], points[0][1])
        h3_metrics = []
        for latitude, longitude in points:
            cell = h3.latlng_to_cell(latitude, longitude, h3_resolution)
            boundary = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
            h3_metrics.append(polygon_metrics(boundary))
        systems_for_country["h3"] = summarise(h3_metrics, h3_resolution)

        s2_level, _ = choose_s2(points[0][0], points[0][1])
        s2_metrics = [polygon_metrics(s2_corners(latitude, longitude, s2_level)) for latitude, longitude in points]
        systems_for_country["s2"] = summarise(s2_metrics, s2_level)

        geohash_length, _ = choose_geohash(points[0][0], points[0][1])
        geohash_metrics = [polygon_metrics(rectangle_corners(geohash_bounds(geohash_encode(latitude, longitude, geohash_length)))) for latitude, longitude in points]
        systems_for_country["geohash"] = summarise(geohash_metrics, geohash_length)

        web_metrics = [polygon_metrics(web_mercator_corners(latitude, longitude)) for latitude, longitude in points]
        systems_for_country["web_mercator_50m"] = summarise(web_metrics, "50m projected square")

        records.append(
            {
                "domain_code": code,
                "name": name,
                "boundary_source": boundary_source,
                "systems": systems_for_country,
            }
        )

    output = {
        "target_area_m2": TARGET_AREA_M2,
        "target_edge_m": 50.0,
        "sample_definition": "boundary vertices sampled up to 100 per ASEAN candidate boundary",
        "metrics": {
            "area_m2": "geodesic area of the cell polygon",
            "side_anisotropy": "longest side / shortest side; 1.0 is equal sides",
            "compactness": "4*pi*area/perimeter^2; shape indicator, not a square score",
            "area_ratio": "cell ground area / 2,500 m2 target",
        },
        "comparison_dependencies": {
            "h3": getattr(h3, "__version__", "unknown"),
            "s2sphere": "0.2.5",
        },
        "countries": records,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_output = Path("..") / ".." / OUTPUT.relative_to(ROOT)
    lines = [
        "# ASEAN cross-system 50 m benchmark",
        "",
        "This compares cells selected near a 50 m target. It is not a claim that the systems have identical resolutions.",
        "",
        "| Country | System | Resolution | Area p05–p95 m² | Side anisotropy max | Compactness median |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for country in records:
        for system, metrics in country["systems"].items():
            lines.append(
                f"| {country['domain_code']} | {system} | {metrics['resolution']} | "
                f"{metrics['area_m2']['p05']:.1f}–{metrics['area_m2']['p95']:.1f} | "
                f"{metrics['side_anisotropy']['max']:.6f} | "
                f"{metrics['compactness']['median']:.4f} |"
            )
    lines.extend(
        [
            "",
            "A square has compactness about 0.7854. A regular hexagon has compactness about 0.9069. Compactness is included to distinguish shape, not to declare hexagons worse.",
            "",
            f"Detailed JSON: [`{report_output}`]({report_output})",
        ]
    )
    MARKDOWN_OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote cross-system benchmark: {OUTPUT}")
    print(f"Wrote report: {MARKDOWN_OUTPUT}")


if __name__ == "__main__":
    main()
