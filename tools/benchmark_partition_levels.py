#!/usr/bin/env python3
"""Benchmark partition levels for GeoSquare cell Parquet datasets.

Measured on a real cell table:
  * GID, packed ID, and row-position checks against the reference codec;
  * Parquet bytes per row, for the full table and for a thin two-column table;
  * partition count and file sizes for each partition level, written to --out;
  * row-group pruning for a level-9 range query on a file sorted by packed_id.

Derived from the signed ID boundary:
  * land cell counts per partition level, using the grid CRS and the equal-area CRS.

Scratch files are written only under --out. Pass a path under $KIROCREW_SCRATCH.

Usage:
    python tools/benchmark_partition_levels.py \
        --cells /path/to/cell_features.parquet \
        --out "$KIROCREW_SCRATCH/partition-benchmark"
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform as shapely_transform

from geosquare_v2 import DbRegistryLoader
from geosquare_v2.codec import SUBDIVISIONS, cell_side_m, gid_to_indices
from geosquare_v2.packing import pack_int64

REPO_ROOT = Path(__file__).resolve().parents[1]
TRUST_FILE = REPO_ROOT / "release" / "registry-trust.json"
DB_DIR = REPO_ROOT / "src" / "geosquare_v2" / "db"
REGISTRY_DIR = REPO_ROOT / "src" / "geosquare_v2" / "data" / "registry"
DOMAIN_CODE = "ID"
DATA_LEVEL = 12
PARTITION_LEVELS = (3, 4, 5, 6, 7, 8, 9)
MAX_LAND_COUNT_LEVEL = 8
TARGET_MAX_BYTES = 512 * 1024 * 1024
TARGET_MIN_BYTES = 64 * 1024 * 1024
ROW_GROUP_ROWS = 8192
PRUNE_PARENT_LEVEL = 9
MB = 1024 * 1024


def _load_profile():
    trust_values = json.loads(TRUST_FILE.read_text(encoding="utf-8"))
    trust = {key: base64.b64decode(value, validate=True) for key, value in trust_values.items()}
    registry = DbRegistryLoader(trust, DB_DIR, boundary_root=REGISTRY_DIR, verify_boundaries=True).load()
    return registry.get(DOMAIN_CODE)


def _read_cells(path: Path) -> tuple[pa.Table, np.ndarray, np.ndarray]:
    """Read the cell table and decode every GID with the reference codec."""
    table = pq.read_table(path)
    gids = table.column("gid").to_pylist()
    xs = np.empty(len(gids), dtype=np.int64)
    ys = np.empty(len(gids), dtype=np.int64)
    for row, gid in enumerate(gids):
        level, x_idx, y_idx = gid_to_indices(gid)
        if level != DATA_LEVEL:
            raise SystemExit(f"row {row}: GID {gid} is level {level}, expected {DATA_LEVEL}")
        xs[row], ys[row] = x_idx, y_idx
    if len(set(gids)) != len(gids):
        raise SystemExit("gid is not unique; a cell_values dataset must have unique GIDs")
    packed = np.array([pack_int64(1, DATA_LEVEL, int(x), int(y)) for x, y in zip(xs, ys)], dtype=np.int64)
    table = table.append_column("packed_id", pa.array(packed, type=pa.int64()))
    return table, xs, ys


def _check_points_against_gids(table: pa.Table, xs: np.ndarray, ys: np.ndarray, profile) -> dict[str, Any]:
    """Re-index each row's lon/lat with the spec's formula (vectorised) and compare to the stored GID."""
    if "lon" not in table.column_names or "lat" not in table.column_names:
        return {"checked": 0, "note": "no lon/lat columns"}
    lon = table.column("lon").to_numpy()
    lat = table.column("lat").to_numpy()
    transformer = Transformer.from_crs(4326, profile.crs_wkt2, always_xy=True)
    x_m, y_m = transformer.transform(lon, lat)
    side = cell_side_m(DATA_LEVEL)
    x_idx = np.floor((np.asarray(x_m) - profile.origin_x_m) / side).astype(np.int64)
    y_idx = np.floor((np.asarray(y_m) - profile.origin_y_m) / side).astype(np.int64)
    mismatch = int(np.count_nonzero((x_idx != xs) | (y_idx != ys)))
    return {
        "checked": int(len(xs)),
        "mismatches": mismatch,
        "note": "lon/lat from the file, re-indexed with the spec formula in the grid CRS",
    }


def _bytes_per_row(table: pa.Table, out: Path, label: str) -> dict[str, Any]:
    ordered = table.sort_by("packed_id")
    path = out / f"bytes_{label}.parquet"
    pq.write_table(ordered, path, compression="zstd", row_group_size=ROW_GROUP_ROWS)
    size = path.stat().st_size
    return {"columns": ordered.num_columns, "rows": ordered.num_rows, "bytes": size, "bytes_per_row": size / ordered.num_rows}


def _partition_stats(table: pa.Table, out: Path, level: int) -> dict[str, Any]:
    gids = table.column("gid").to_pylist()
    groups: dict[str, list[int]] = defaultdict(list)
    for row, gid in enumerate(gids):
        groups[gid[:level]].append(row)
    directory = out / f"partitions_L{level}"
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)
    rows, sizes = [], []
    for prefix, indices in sorted(groups.items()):
        part = table.take(indices).sort_by("packed_id")
        path = directory / f"gid_prefix={prefix}.parquet"
        pq.write_table(part, path, compression="zstd", row_group_size=ROW_GROUP_ROWS)
        rows.append(part.num_rows)
        sizes.append(path.stat().st_size)
    return {
        "partitions_in_sample": len(groups),
        "rows_min": min(rows),
        "rows_median": statistics.median(rows),
        "rows_max": max(rows),
        "file_bytes_min": min(sizes),
        "file_bytes_median": statistics.median(sizes),
        "file_bytes_max": max(sizes),
    }


def _path_bits(level: int) -> int:
    return sum(5 if step == 5 else 2 for step in SUBDIVISIONS[:level])


def _row_group_pruning(table: pa.Table, out: Path) -> dict[str, Any]:
    """Count row groups a level-9 parent range can touch in a packed_id-sorted file."""
    ordered = table.sort_by("packed_id")
    path = out / "pruning.parquet"
    pq.write_table(ordered, path, compression="zstd", row_group_size=ROW_GROUP_ROWS)
    packed = ordered.column("packed_id").to_numpy()
    prefixes = Counter(gid[:PRUNE_PARENT_LEVEL] for gid in ordered.column("gid").to_pylist())
    parent_gid, _ = prefixes.most_common(1)[0]
    _, px, py = gid_to_indices(parent_gid)

    domain_id = 1
    parent_path = (pack_int64(domain_id, PRUNE_PARENT_LEVEL, px, py) >> 1) & ((1 << _path_bits(PRUNE_PARENT_LEVEL)) - 1)
    shift = _path_bits(DATA_LEVEL) - _path_bits(PRUNE_PARENT_LEVEL)
    lo_path = parent_path << shift
    hi_path = lo_path + (1 << shift) - 1
    base = (domain_id << 54) | (DATA_LEVEL << 50)
    lo, hi = base | (lo_path << 1), base | (hi_path << 1)

    in_range = int(np.count_nonzero((packed >= lo) & (packed <= hi)))
    meta = pq.ParquetFile(path).metadata
    column = meta.schema.names.index("packed_id")
    touched = 0
    for group in range(meta.num_row_groups):
        stats = meta.row_group(group).column(column).statistics
        if stats is None or (stats.max >= lo and stats.min <= hi):
            touched += 1
    return {
        "parent_gid": parent_gid,
        "parent_level": PRUNE_PARENT_LEVEL,
        "rows_in_range": in_range,
        "row_groups_total": meta.num_row_groups,
        "row_groups_touched": touched,
        "row_group_rows": ROW_GROUP_ROWS,
    }



def _national_land_cells(profile) -> dict[str, Any]:
    """Count grid cells at each level that touch the ID boundary, and its land area."""
    source = json.loads((REGISTRY_DIR / "boundaries" / Path(profile.boundary_file).name).read_text(encoding="utf-8"))
    union = shapely.union_all([shape(f["geometry"]) for f in source["features"]])
    to_grid = Transformer.from_crs(4326, profile.crs_wkt2, always_xy=True).transform
    to_equal_area = Transformer.from_crs(4326, profile.equal_area_crs_wkt2, always_xy=True).transform
    land_km2 = shapely_transform(to_equal_area, union).area / 1e6
    grid_boundary = shapely_transform(to_grid, union)
    minx, miny, maxx, maxy = grid_boundary.bounds
    counts: dict[str, Any] = {"land_km2": land_km2, "levels": {}}
    for level in PARTITION_LEVELS:
        side = cell_side_m(level)
        if level > MAX_LAND_COUNT_LEVEL:
            counts["levels"][str(level)] = {
                "cells": land_km2 * 1e6 / (side * side),
                "method": "area estimate (land_km2 / cell area)",
            }
            continue
        i0 = int(np.floor((minx - profile.origin_x_m) / side))
        i1 = int(np.floor((maxx - profile.origin_x_m) / side))
        j0 = int(np.floor((miny - profile.origin_y_m) / side))
        j1 = int(np.floor((maxy - profile.origin_y_m) / side))
        xs, ys = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1), indexing="ij")
        x_min = profile.origin_x_m + xs.ravel() * side
        y_min = profile.origin_y_m + ys.ravel() * side
        boxes = shapely.box(x_min, y_min, x_min + side, y_min + side)
        hits = shapely.intersects(boxes, grid_boundary)
        counts["levels"][str(level)] = {
            "cells": int(np.count_nonzero(hits)),
            "candidates": int(len(boxes)),
            "method": "exact intersection with the ID boundary",
        }
    return counts


def _estimate_partition_choice(bytes_per_row: float) -> dict[str, Any]:
    """For 50 m data, show rows and bytes per full partition at each partition level."""
    rows = {}
    for level in PARTITION_LEVELS:
        per_partition_rows = (cell_side_m(level) / cell_side_m(DATA_LEVEL)) ** 2
        per_partition_bytes = per_partition_rows * bytes_per_row
        rows[str(level)] = {
            "rows_per_full_partition": per_partition_rows,
            "bytes_per_full_partition": per_partition_bytes,
            "within_target": TARGET_MIN_BYTES <= per_partition_bytes <= TARGET_MAX_BYTES,
            "under_max": per_partition_bytes <= TARGET_MAX_BYTES,
        }
    return rows


def _fmt_mb(value: float) -> str:
    return f"{value / MB:,.1f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cells", type=Path, required=True, help="cell_values Parquet with a gid column")
    parser.add_argument("--out", type=Path, required=True, help="scratch directory for benchmark output")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    profile = _load_profile()
    table, xs, ys = _read_cells(args.cells)
    results: dict[str, Any] = {
        "input": {"path": str(args.cells), "rows": table.num_rows, "columns": table.column_names},
        "domain_code": DOMAIN_CODE,
        "data_level": DATA_LEVEL,
        "profile_version": profile.profile_version,
    }
    results["point_check"] = _check_points_against_gids(table, xs, ys, profile)

    thin = table.select(["gid", "packed_id", "coverage_ratio"]) if "coverage_ratio" in table.column_names else table.select(["gid", "packed_id"])
    results["bytes_per_row"] = {
        "full_table": _bytes_per_row(table, args.out, "full"),
        "thin_table": _bytes_per_row(thin, args.out, "thin"),
    }
    per_row = results["bytes_per_row"]["full_table"]["bytes_per_row"]
    thin_per_row = results["bytes_per_row"]["thin_table"]["bytes_per_row"]
    results["partition_samples"] = {str(level): _partition_stats(table, args.out, level) for level in PARTITION_LEVELS}
    results["row_group_pruning"] = _row_group_pruning(table, args.out)
    results["national_land_cells"] = _national_land_cells(profile)
    results["partition_choice_for_50m_data"] = {
        "full_table": _estimate_partition_choice(per_row),
        "thin_table": _estimate_partition_choice(thin_per_row),
    }

    (args.out / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    _print_summary(results)
    return 0


def _print_summary(results: dict[str, Any]) -> None:
    print("point check:", results["point_check"])
    print("bytes per row:", {k: round(v["bytes_per_row"], 1) for k, v in results["bytes_per_row"].items()})
    print("row group pruning:", results["row_group_pruning"])
    print("land area km2:", round(results["national_land_cells"]["land_km2"], 1))
    print(f"{'level':>5} {'cells_nat':>14} {'MB_full_50m':>12} {'in':>5} {'MB_thin_50m':>12} {'in':>5}")
    for level in PARTITION_LEVELS:
        land = results["national_land_cells"]["levels"][str(level)]["cells"]
        full = results["partition_choice_for_50m_data"]["full_table"][str(level)]
        thin = results["partition_choice_for_50m_data"]["thin_table"][str(level)]
        print(
            f"{level:>5} {land:>14,.0f} {_fmt_mb(full['bytes_per_full_partition']):>12} "
            f"{str(full['within_target']):>5} {_fmt_mb(thin['bytes_per_full_partition']):>12} "
            f"{str(thin['within_target']):>5}"
        )
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
