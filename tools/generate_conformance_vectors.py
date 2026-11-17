#!/usr/bin/env python3
"""Generate the GeoSquare spec 2.0 conformance vectors.

Every expected value comes from the Python reference implementation (geosquare_v2).
The generator refuses to write a case that the reference does not agree with. The
detection cases are the one exception: they are written by hand, and
tests/test_conformance_vectors.py checks them against the reference detector.

Usage:
    python tools/generate_conformance_vectors.py          # rewrite conformance/spec-2.0/
    python tools/generate_conformance_vectors.py --check  # exit 1 if committed files drift
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import pyproj
import shapely
from pyproj import Transformer
from shapely.geometry import shape

import geosquare_v2
from geosquare_v2 import DbRegistryLoader, GeosquareService
from geosquare_v2.codec import SUBDIVISIONS, canonical_to_gid, cell_side_m, gid_to_indices, side_cell_count
from geosquare_v2.errors import GeosquareError, OutOfDomainError
from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.model import CanonicalCell
from geosquare_v2.packing import pack_int64, unpack_int64

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_VERSION = "2.0"
OUT_DIR = REPO_ROOT / "conformance" / f"spec-{SPEC_VERSION}"
TRUST_FILE = REPO_ROOT / "release" / "registry-trust.json"
RELEASE_MANIFEST = REPO_ROOT / "release" / "registry.v2.json"
SUPPORT_MATRIX = REPO_ROOT / "release" / "profiles" / "DOMAIN_SUPPORT_MATRIX.json"
DB_DIR = REPO_ROOT / "src" / "geosquare_v2" / "db"
REGISTRY_DIR = REPO_ROOT / "src" / "geosquare_v2" / "data" / "registry"
SEED = f"geosquare-spec-{SPEC_VERSION}"
RANDOM_CELLS_PER_LEVEL = 8
PARENT_SAMPLE_COUNT = 2
MIN_EDGE_DISTANCE_M = 1e-3


def _dumps(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _path_bits(level: int) -> int:
    """Number of hierarchical path bits used by a cell at ``level``."""
    return sum(5 if step == 5 else 2 for step in SUBDIVISIONS[:level])


def _sample_indices(level: int) -> list[tuple[int, int]]:
    """Corners, centre and a seeded random set of canonical indices for one level."""
    n = side_cell_count(level)
    rng = random.Random(f"{SEED}:{level}")
    chosen = {(0, 0), (n - 1, n - 1), (n - 1, 0), (0, n - 1), (n // 2, n // 3)}
    target = min(n * n, len(chosen) + RANDOM_CELLS_PER_LEVEL)
    while len(chosen) < target:
        chosen.add((rng.randrange(n), rng.randrange(n)))
    return sorted(chosen)


def _load_registry():
    trust_values = json.loads(TRUST_FILE.read_text(encoding="utf-8"))
    trust = {key: base64.b64decode(value, validate=True) for key, value in trust_values.items()}
    return DbRegistryLoader(trust, DB_DIR, boundary_root=REGISTRY_DIR, verify_boundaries=True).load()


def _load_boundary(profile) -> shapely.Geometry:
    path = REGISTRY_DIR / "boundaries" / Path(profile.boundary_file).name
    data = path.read_bytes()
    _require(hashlib.sha256(data).hexdigest() == profile.boundary_sha256, f"boundary hash mismatch: {path}")
    features = json.loads(data)["features"]
    return shapely.union_all([shape(feature["geometry"]) for feature in features])


def _codec_section(domain_code: str, domain_id: int) -> dict[str, Any]:
    cells = []
    for level in range(len(SUBDIVISIONS) + 1):
        for x_idx, y_idx in _sample_indices(level):
            gid = canonical_to_gid(level, x_idx, y_idx)
            _require(gid_to_indices(gid) == (level, x_idx, y_idx), f"codec round trip failed: {gid}")
            packed = pack_int64(domain_id, level, x_idx, y_idx)
            _require(unpack_int64(packed) == (domain_id, level, x_idx, y_idx), f"packing failed: {packed}")
            cells.append(
                {
                    "level": level,
                    "x_idx": x_idx,
                    "y_idx": y_idx,
                    "gid": gid,
                    "packed_id": str(packed),
                }
            )

    invalid_gids = [
        ("h2x545v39", "lowercase is not a V2 GID"),
        ("I2X545V39", "I is outside the base-5 alphabet"),
        ("J3N2M75", "v1 10 km style value; 7 is not valid at level 6 (base 2)"),
        ("H2X545V3Z", "Z is outside the base-5 alphabet at level 9"),
        (" H2X545V39", "leading space"),
        ("2" * 15, "level 15 is above the maximum of 14"),
    ]
    for value, _ in invalid_gids:
        try:
            gid_to_indices(value)
        except GeosquareError:
            continue
        raise AssertionError(f"reference accepted invalid GID {value!r}")

    valid_packed_bits = pack_int64(domain_id, 1, 0, 0)
    invalid_packed = [
        (str(1 << 63), "sign bit set"),
        (str(valid_packed_bits | 1), "reserved bit 0 set"),
        (str(1 << 50), "domain ID 0"),
        (str((domain_id << 54) | (15 << 50)), "level 15 is above the maximum of 14"),
        (str(valid_packed_bits | (1 << 20)), "unused path bits set at level 1"),
    ]
    for value, _ in invalid_packed:
        try:
            unpack_int64(int(value))
        except GeosquareError:
            continue
        raise AssertionError(f"reference accepted invalid packed ID {value}")

    return {
        "description": "Canonical, GID and Int64 round trips for every level 0..14, plus rejected inputs.",
        "domain_code": domain_code,
        "domain_id": domain_id,
        "cells": cells,
        "invalid_gids": [{"input": value, "reason": reason} for value, reason in invalid_gids],
        "invalid_packed_ids": [{"packed_id": value, "reason": reason} for value, reason in invalid_packed],
    }


def _descendants(grid: GeosquareGrid, cell: CanonicalCell, depth: int) -> list[CanonicalCell]:
    current = [cell]
    for _ in range(depth):
        current = [child for parent in current for child in grid.children(parent)]
    return current


def _topology_section(grid: GeosquareGrid, domain_code: str, domain_id: int) -> dict[str, Any]:
    parent_of, children_of, ranges, neighbours, distances = [], [], [], [], []
    max_level = len(SUBDIVISIONS)

    for level in range(1, max_level + 1):
        for x_idx, y_idx in _sample_indices(level)[:PARENT_SAMPLE_COUNT + 2]:
            cell = CanonicalCell(domain_code, level, x_idx, y_idx)
            parent = grid.parent(cell)
            parent_of.append(
                {
                    "gid": canonical_to_gid(level, x_idx, y_idx),
                    "level": level,
                    "parent_gid": canonical_to_gid(parent.level, parent.x_idx, parent.y_idx),
                }
            )

    for level in range(max_level):
        expected_children = 25 if SUBDIVISIONS[level] == 5 else 4
        for x_idx, y_idx in _sample_indices(level)[:PARENT_SAMPLE_COUNT + 2]:
            cell = CanonicalCell(domain_code, level, x_idx, y_idx)
            kids = grid.children(cell)
            _require(len(kids) == expected_children, f"child count at level {level} is {len(kids)}")
            child_gids = sorted(canonical_to_gid(c.level, c.x_idx, c.y_idx) for c in kids)
            children_of.append({"gid": canonical_to_gid(level, x_idx, y_idx), "level": level, "child_gids": child_gids})

    for level in range(max_level - 1):
        for x_idx, y_idx in _sample_indices(level)[:PARENT_SAMPLE_COUNT]:
            parent_cell = CanonicalCell(domain_code, level, x_idx, y_idx)
            parent_path = (pack_int64(domain_id, level, x_idx, y_idx) >> 1) & ((1 << _path_bits(level)) - 1)
            for child_level in (level + 1, level + 2):
                if child_level > max_level:
                    continue
                shift = _path_bits(child_level) - _path_bits(level)
                base = (domain_id << 54) | (child_level << 50)
                lo = base | ((parent_path << shift) << 1)
                hi = base | (((parent_path << shift) + (1 << shift) - 1) << 1)
                descendants = {
                    pack_int64(domain_id, d.level, d.x_idx, d.y_idx)
                    for d in _descendants(grid, parent_cell, child_level - level)
                }
                valid_in_range = set()
                for candidate in range(lo, hi + 1, 2):
                    try:
                        unpack_int64(candidate)
                    except GeosquareError:
                        continue
                    valid_in_range.add(candidate)
                _require(min(descendants) == lo, "range lower bound is not the first descendant")
                _require(valid_in_range == descendants, "range does not contain exactly the descendants")
                ranges.append(
                    {
                        "parent_gid": canonical_to_gid(level, x_idx, y_idx),
                        "parent_level": level,
                        "child_level": child_level,
                        "lo": str(lo),
                        "hi": str(hi),
                        "descendant_count": len(descendants),
                    }
                )

    for level in (1, 2, 3, 5, 9, 12):
        n = side_cell_count(level)
        step = SUBDIVISIONS[level - 1]
        x_boundary = (n // 2) - ((n // 2) % step)
        for x_idx, y_idx in sorted({(0, 0), (n - 1, n - 1), (n - 1, 0), (0, n - 1), (x_boundary, n // 3)}):
            cell = CanonicalCell(domain_code, level, x_idx, y_idx)
            neighbours.append(
                {
                    "gid": canonical_to_gid(level, x_idx, y_idx),
                    "level": level,
                    "x_idx": x_idx,
                    "y_idx": y_idx,
                    "k_ring_1": sorted(canonical_to_gid(c.level, c.x_idx, c.y_idx) for c in grid.k_ring(cell, 1)),
                    "k_ring_2": sorted(canonical_to_gid(c.level, c.x_idx, c.y_idx) for c in grid.k_ring(cell, 2)),
                    "k_disk_1": sorted(canonical_to_gid(c.level, c.x_idx, c.y_idx) for c in grid.k_disk(cell, 1)),
                }
            )

    for level in (9, 12):
        n = side_cell_count(level)
        origin = CanonicalCell(domain_code, level, n // 2, n // 3)
        for dx, dy in ((1, 0), (1, 1), (3, 4), (0, 7), (-5, 12)):
            other = CanonicalCell(domain_code, level, origin.x_idx + dx, origin.y_idx + dy)
            expected = math.sqrt(dx * dx + dy * dy) * cell_side_m(level)
            actual = grid.distance_m(origin, other)
            _require(math.isclose(actual, expected, rel_tol=1e-12), "distance does not match sqrt(dx^2+dy^2)*side")
            distances.append(
                {
                    "a_gid": canonical_to_gid(level, origin.x_idx, origin.y_idx),
                    "b_gid": canonical_to_gid(level, other.x_idx, other.y_idx),
                    "level": level,
                    "dx": dx,
                    "dy": dy,
                    "cell_side_m": cell_side_m(level),
                    "distance_m": expected,
                }
            )

    return {
        "description": "Parent/child topology, descendant packed ranges, neighbour sets and grid distances.",
        "domain_code": domain_code,
        "domain_id": domain_id,
        "parent_of": parent_of,
        "children_of": children_of,
        "descendant_ranges": ranges,
        "neighbours": neighbours,
        "distances": distances,
    }


def _projected_section(profiles) -> dict[str, Any]:
    domains, cases = [], []
    for profile in profiles:
        grid = GeosquareGrid(profile)
        ox, oy, root = profile.origin_x_m, profile.origin_y_m, profile.root_side_m
        domains.append(
            {
                "domain_code": profile.domain_code,
                "origin_x_m": ox,
                "origin_y_m": oy,
                "root_side_m": root,
            }
        )
        for level in (1, 2, 5, 9, 12, 14):
            n = side_cell_count(level)
            side = root / n
            pairs = [
                (ox, oy),
                (ox + side - 1, oy),
                (ox + side, oy),
                (ox + root, oy + root),
                (ox + side * (n - 1), oy + side * (n - 1)),
                (ox - 1, oy),
                (ox + root + 1, oy),
                (ox, oy + root + 1),
            ]
            for x_m, y_m in pairs:
                record: dict[str, Any] = {
                    "domain_code": profile.domain_code,
                    "level": level,
                    "x_m": x_m,
                    "y_m": y_m,
                }
                try:
                    cell = grid.canonical_from_projected(x_m, y_m, level)
                except OutOfDomainError:
                    record["expect"] = "reject"
                else:
                    record["expect"] = {
                        "x_idx": cell.x_idx,
                        "y_idx": cell.y_idx,
                        "gid": canonical_to_gid(level, cell.x_idx, cell.y_idx),
                    }
                cases.append(record)
    return {
        "description": (
            "Half-open cell rule in grid CRS. A coordinate on an internal edge belongs to the cell "
            "on its high side. The maximum root edge belongs to the last cell. Outside the root is rejected."
        ),
        "domains": domains,
        "cases": cases,
    }


def _points_section(service, profiles, support) -> dict[str, Any]:
    cases = []
    extra = {"ID": [(106.8456, -6.2088)]}
    for profile in profiles:
        boundary = _load_boundary(profile)
        point = boundary.representative_point()
        lon, lat = round(point.x, 6), round(point.y, 6)
        candidates = [(lon, lat)] + extra.get(profile.domain_code, [])
        transformer = Transformer.from_crs(4326, profile.crs_wkt2, always_xy=True)
        grid = GeosquareGrid(profile)
        for lon_value, lat_value in candidates:
            _require(
                boundary.covers(shapely.Point(lon_value, lat_value)),
                f"{profile.domain_code}: sample point is outside the boundary",
            )
            x_m, y_m = transformer.transform(lon_value, lat_value)
            side = cell_side_m(12)
            for axis in (x_m - profile.origin_x_m, y_m - profile.origin_y_m):
                remainder = axis % side
                _require(
                    min(remainder, side - remainder) > MIN_EDGE_DISTANCE_M,
                    f"{profile.domain_code}: sample point is on a cell edge",
                )
            levels: dict[str, str] = {}
            for level in (5, 7, 9, 12):
                gid = service.point_to_cell(profile.domain_code, lon_value, lat_value, level).gid
                cell = grid.canonical_from_projected(x_m, y_m, level)
                _require(canonical_to_gid(level, cell.x_idx, cell.y_idx) == gid, "service and grid disagree")
                levels[str(level)] = gid
            status = support[profile.domain_code]
            cases.append(
                {
                    "domain_code": profile.domain_code,
                    "lon": lon_value,
                    "lat": lat_value,
                    "production_ready": status["production_ready"],
                    "support_status": status["support_status"],
                    "gids": levels,
                }
            )
    return {
        "description": (
            "Lon/lat to GID at several levels. Points come from each boundary's representative point. "
            "Provisional domains are included and marked with their support status."
        ),
        "cases": cases,
    }


def _detect_cases() -> list[dict[str, Any]]:
    g9 = canonical_to_gid(9, 12345, 23456)
    g12 = canonical_to_gid(12, 475168, 491792)
    g12_b = canonical_to_gid(12, 475169, 491792)
    digit_gid = "23456"
    for value in (g9, g12, g12_b, digit_gid):
        gid_to_indices(value)
    for value in ("J3N2M75",):
        try:
            gid_to_indices(value)
        except GeosquareError:
            continue
        raise AssertionError(f"{value} should be invalid")
    _require(gid_to_indices(digit_gid)[0] == 5, "23456 must be a valid level-5 GID")

    packed_9 = str(pack_int64(1, 9, 12345, 23456))
    packed_12 = str(pack_int64(1, 12, 475168, 491792))
    packed_odd = str(int(packed_9) | 1)
    packed_domain_zero = str(1 << 50)
    n9 = side_cell_count(9)

    uri_ok = [f"geosquare:v2:ID:{g9}"] * 49 + [f"geosquare:v2:ID:{g12}"] * 50 + [f"geosquare:v2:ID:{g12_b}"]
    uri_bad_two_percent = [f"geosquare:v2:ID:{g9}"] * 98 + ["geosquare:v2:ID:J3N2M75"] * 2
    gid_ok = [g9, g12]

    return [
        {
            "name": "uri_column_certain",
            "columns": {"place_uri": {"dtype": "string", "values": uri_ok}},
            "expect": {"place_uri": {"kind": "uri", "status": "certain", "domain_codes": ["ID"], "levels": [9, 12]}},
        },
        {
            "name": "uri_column_two_domains",
            "columns": {
                "place_uri": {
                    "dtype": "string",
                    "values": [f"geosquare:v2:ID:{g9}", f"geosquare:v2:VN:{g9}"],
                }
            },
            "expect": {"place_uri": {"kind": "uri", "status": "certain", "domain_codes": ["ID", "VN"], "levels": [9]}},
        },
        {
            "name": "uri_domain_mismatch_with_hint_rejected",
            "domain_code": "VN",
            "columns": {"place_uri": {"dtype": "string", "values": [f"geosquare:v2:ID:{g9}"] * 3}},
            "expect": {"place_uri": {"kind": "uri", "status": "rejected"}},
        },
        {
            "name": "uri_two_percent_invalid_rejected",
            "columns": {"place_uri": {"dtype": "string", "values": uri_bad_two_percent}},
            "expect": {"place_uri": {"kind": "uri", "status": "rejected"}},
        },
        {
            "name": "bare_gid_with_domain_certain",
            "domain_code": "ID",
            "columns": {"gid": {"dtype": "string", "values": gid_ok}},
            "expect": {"gid": {"kind": "gid", "status": "certain", "domain_codes": ["ID"], "levels": [9, 12]}},
        },
        {
            "name": "bare_gid_without_domain_needs_domain",
            "columns": {"gid": {"dtype": "string", "values": gid_ok}},
            "expect": {"gid": {"kind": "gid", "status": "needs_domain", "levels": [9, 12]}},
        },
        {
            "name": "lowercase_gid_rejected",
            "domain_code": "ID",
            "columns": {"gid": {"dtype": "string", "values": [g9.lower()] * 3}},
            "expect": {"gid": {"kind": "gid", "status": "rejected"}},
        },
        {
            "name": "v1_gid10km_style_rejected",
            "domain_code": "ID",
            "columns": {"gid10km": {"dtype": "string", "values": ["J3N2M75"] * 4}},
            "expect": {"gid10km": {"kind": "gid", "status": "rejected"}},
        },
        {
            "name": "gid_below_min_length_rejected",
            "domain_code": "ID",
            "columns": {"code": {"dtype": "string", "values": ["2345", "2345"]}},
            "expect": {"code": {"kind": "gid", "status": "rejected"}},
        },
        {
            "name": "all_digit_gid_needs_confirmation",
            "domain_code": "ID",
            "columns": {"code": {"dtype": "string", "values": [digit_gid, digit_gid]}},
            "expect": {"code": {"kind": "gid", "status": "needs_confirmation", "levels": [5]}},
        },
        {
            "name": "digit_gid_in_int_column_rejected",
            "domain_code": "ID",
            "columns": {"code": {"dtype": "int64", "values": ["23456", "23456"]}},
            "expect": {"code": {"kind": "gid", "status": "rejected"}},
        },
        {
            "name": "packed_ids_certain",
            "columns": {"packed_id": {"dtype": "int64", "values": [packed_9, packed_12]}},
            "expect": {"packed_id": {"kind": "packed_id", "status": "certain", "domain_ids": [1], "levels": [9, 12]}},
        },
        {
            "name": "packed_odd_value_rejected",
            "columns": {"packed_id": {"dtype": "int64", "values": [packed_odd] * 3}},
            "expect": {"packed_id": {"kind": "packed_id", "status": "rejected"}},
        },
        {
            "name": "packed_domain_zero_rejected",
            "columns": {"packed_id": {"dtype": "int64", "values": [packed_domain_zero] * 3}},
            "expect": {"packed_id": {"kind": "packed_id", "status": "rejected"}},
        },
        {
            "name": "plain_int_column_rejected",
            "columns": {"population": {"dtype": "int64", "values": ["1", "2", "3"]}},
            "expect": {"population": {"kind": "packed_id", "status": "rejected"}},
        },
        {
            "name": "xy_indices_need_level",
            "columns": {
                "x_idx": {"dtype": "int64", "values": ["0", "49999"]},
                "y_idx": {"dtype": "int64", "values": ["0", "1"]},
            },
            "expect": {"x_idx+y_idx": {"kind": "xy_indices", "status": "needs_level"}},
        },
        {
            "name": "xy_indices_certain_at_level_9",
            "domain_code": "ID",
            "level": 9,
            "columns": {
                "x_idx": {"dtype": "int64", "values": ["0", str(n9 - 1)]},
                "y_idx": {"dtype": "int64", "values": ["0", "1"]},
            },
            "expect": {"x_idx+y_idx": {"kind": "xy_indices", "status": "certain", "domain_codes": ["ID"], "levels": [9]}},
        },
        {
            "name": "xy_indices_out_of_range_rejected",
            "domain_code": "ID",
            "level": 9,
            "columns": {
                "x_idx": {"dtype": "int64", "values": [str(n9)] * 3},
                "y_idx": {"dtype": "int64", "values": ["0"] * 3},
            },
            "expect": {"x_idx+y_idx": {"kind": "xy_indices", "status": "rejected"}},
        },
        {
            "name": "text_column_rejected",
            "domain_code": "ID",
            "columns": {"city": {"dtype": "string", "values": ["Jakarta", "Bandung"]}},
            "expect": {"city": {"kind": "gid", "status": "rejected"}},
        },
        {
            "name": "float_column_rejected",
            "columns": {"ratio": {"dtype": "float64", "values": ["0.5"]}},
            "expect": {"ratio": {"kind": "none", "status": "rejected"}},
        },
    ]


def _detect_section() -> dict[str, Any]:
    cases = _detect_cases()
    return {
        "description": (
            "Hand-written detection cases checked against geosquare_v2.detect. "
            "int64 values are decimal strings, so values above 2^53 stay exact in JSON."
        ),
        "cases": cases,
    }


def build_all() -> dict[str, bytes]:
    """Return every vector file as bytes, keyed by file name, including ``manifest.json``."""
    registry = _load_registry()
    profiles = tuple(sorted(registry.profiles(), key=lambda profile: profile.domain_id))
    id_profile = registry.get("ID")
    grid = GeosquareGrid(id_profile)
    service = GeosquareService(registry, boundary_root=REGISTRY_DIR)
    support = {entry["domain_code"]: entry for entry in json.loads(SUPPORT_MATRIX.read_text(encoding="utf-8"))["domains"]}
    release = json.loads(RELEASE_MANIFEST.read_text(encoding="utf-8"))

    files: dict[str, bytes] = {
        "codec.json": _dumps(_codec_section("ID", id_profile.domain_id)),
        "topology.json": _dumps(_topology_section(grid, "ID", id_profile.domain_id)),
        "projected.json": _dumps(_projected_section(profiles)),
        "points.json": _dumps(_points_section(service, profiles, support)),
        "detect.json": _dumps(_detect_section()),
    }

    manifest = {
        "spec_version": SPEC_VERSION,
        "vector_set": "geosquare-conformance",
        "generated_by": "tools/generate_conformance_vectors.py",
        "geosquare_v2_version": geosquare_v2.__version__,
        "registry_version": release["registry_version"],
        "proj_version_exact": release["proj_version_exact"],
        "proj_version": pyproj.proj_version_str,
        "domains": [
            {
                "domain_code": profile.domain_code,
                "domain_id": profile.domain_id,
                "profile_version": profile.profile_version,
                "support_status": support[profile.domain_code]["support_status"],
                "production_ready": support[profile.domain_code]["production_ready"],
            }
            for profile in profiles
        ],
        "files": {
            name: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
            for name, payload in sorted(files.items())
        },
    }
    files["manifest.json"] = _dumps(manifest)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail when committed files differ")
    args = parser.parse_args(argv)

    files = build_all()
    if args.check:
        drifted = [name for name, payload in files.items() if not (OUT_DIR / name).is_file() or (OUT_DIR / name).read_bytes() != payload]
        if drifted:
            print("conformance vectors differ from the generator:", ", ".join(drifted))
            return 1
        print(f"conformance vectors match the generator ({len(files)} files)")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (OUT_DIR / name).write_bytes(payload)
        print(f"wrote {OUT_DIR / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
