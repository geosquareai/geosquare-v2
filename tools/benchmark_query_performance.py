#!/usr/bin/env python3
"""Run the reproducible Phase 4 GeoSquare query-performance benchmark.

The benchmark intentionally separates deterministic point generation, GeoSquare
encoding, DuckDB materialisation, and timed SQL workloads. It measures packed
BIGINT and GID text aggregations over the same one-million-row relation and a
separate DuckDB Spatial ``ST_Within`` polygon predicate. The workloads are
reported independently; the spatial predicate is not presented as an
algorithmically equivalent replacement for cell assignment.

DuckDB and its spatial extension are comparison-only research dependencies.
They are not package runtime dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyproj
from pyproj import CRS, Transformer

from geosquare_v2.batch import encode_projected_numpy
from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.release import ReleaseProfile

ROOT = Path(__file__).resolve().parents[1]
PHASE4_DIR = ROOT / "release" / "scale" / "phase4"
OUTPUT_PATH = PHASE4_DIR / "QUERY_PERFORMANCE_BENCHMARK.json"
REPORT_PATH = ROOT / "internal" / "research" / "QUERY_PERFORMANCE_BENCHMARK.md"
MANIFEST_PATH = PHASE4_DIR / "PHASE4_RUN_MANIFEST.json"
PROFILE_PATH = ROOT / "release" / "profiles" / "ID.v2.json"
LEVEL = 12
DEFAULT_POINTS = 1_000_000
DEFAULT_SEED = 2_026_0315
DEFAULT_WARMUPS = 2
DEFAULT_REPETITIONS = 10
CLUSTER_HALF_SIDE_M = 4_000.0
ZONE_HALF_SIDE_M = 4_500.0
CLUSTER_CENTERS_LONLAT = (
    (106.8456, -6.2088),  # Jakarta
    (112.7521, -7.2575),  # Surabaya
    (98.6722, 3.5952),  # Medan
    (119.4327, -5.1477),  # Makassar
    (107.6191, -6.9175),  # Bandung
    (115.2167, -8.6500),  # Denpasar
    (110.4262, -6.9667),  # Semarang
    (104.7458, -2.9909),  # Palembang
    (105.2667, -5.4292),  # Bandar Lampung
    (110.3695, -7.7956),  # Yogyakarta
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(payload)


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def git_dirty() -> bool:
    try:
        return bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return True


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # macOS reports bytes; Linux and most other Unix systems report KiB.
    return value if sys.platform == "darwin" else value * 1024


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of an empty sequence")
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def software_metadata() -> dict[str, Any]:
    try:
        import duckdb

        duckdb_version = duckdb.__version__
    except ImportError:
        duckdb_version = "unavailable"
    proj_db = Path(pyproj.datadir.get_data_dir()) / "proj.db"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
        "cpu_count": os.cpu_count(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyproj": pyproj.__version__,
        "proj": pyproj.proj_version_str,
        "proj_db_sha256": sha256_path(proj_db) if proj_db.is_file() else "unavailable",
        "duckdb": duckdb_version,
    }


def stable_array_hash(hasher: Any, name: str, values: Any, dtype: str) -> None:
    array = np.asarray(values, dtype=np.dtype(dtype), order="C")
    hasher.update(name.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(str(array.shape).encode("ascii"))
    hasher.update(b"\0")
    hasher.update(array.tobytes(order="C"))


def input_hash(
    longitude: Any,
    latitude: Any,
    x_m: Any,
    y_m: Any,
    packed_id: Any,
    gid: Any,
    value: Any,
) -> str:
    hasher = hashlib.sha256()
    stable_array_hash(hasher, "longitude", longitude, "<f8")
    stable_array_hash(hasher, "latitude", latitude, "<f8")
    stable_array_hash(hasher, "x_m", x_m, "<f8")
    stable_array_hash(hasher, "y_m", y_m, "<f8")
    stable_array_hash(hasher, "packed_id", packed_id, "<i8")
    stable_array_hash(hasher, "value", value, "<f8")
    hasher.update(b"gid\0")
    hasher.update("\0".join(str(item) for item in gid.tolist()).encode("utf-8"))
    return hasher.hexdigest()


def load_profile() -> ReleaseProfile:
    profile_data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    return ReleaseProfile(**profile_data)


def generate_points(
    profile: ReleaseProfile,
    point_count: int,
    seed: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if point_count < len(CLUSTER_CENTERS_LONLAT):
        raise ValueError(
            f"point_count must be at least {len(CLUSTER_CENTERS_LONLAT)} for the fixed cluster protocol"
        )
    rng = np.random.default_rng(seed)
    to_grid = Transformer.from_crs(
        CRS.from_epsg(4326), CRS.from_user_input(profile.crs_wkt2), always_xy=True
    )
    to_wgs84 = Transformer.from_crs(
        CRS.from_user_input(profile.crs_wkt2), CRS.from_epsg(4326), always_xy=True
    )
    center_lon = [point[0] for point in CLUSTER_CENTERS_LONLAT]
    center_lat = [point[1] for point in CLUSTER_CENTERS_LONLAT]
    center_x, center_y = to_grid.transform(center_lon, center_lat)
    center_x = np.asarray(center_x, dtype=np.float64)
    center_y = np.asarray(center_y, dtype=np.float64)

    base_count, remainder = divmod(point_count, len(CLUSTER_CENTERS_LONLAT))
    cluster_sizes = [base_count + (index < remainder) for index in range(len(center_x))]
    x_parts: list[np.ndarray] = []
    y_parts: list[np.ndarray] = []
    for index, count in enumerate(cluster_sizes):
        x_parts.append(
            center_x[index]
            + rng.uniform(-CLUSTER_HALF_SIDE_M, CLUSTER_HALF_SIDE_M, size=count)
        )
        y_parts.append(
            center_y[index]
            + rng.uniform(-CLUSTER_HALF_SIDE_M, CLUSTER_HALF_SIDE_M, size=count)
        )
    x_m = np.concatenate(x_parts).astype(np.float64, copy=False)
    y_m = np.concatenate(y_parts).astype(np.float64, copy=False)
    longitude, latitude = to_wgs84.transform(x_m.tolist(), y_m.tolist())
    longitude = np.asarray(longitude, dtype=np.float64)
    latitude = np.asarray(latitude, dtype=np.float64)
    value = rng.uniform(1.0, 100.0, size=point_count).astype(np.float64, copy=False)

    grid = GeosquareGrid(profile)
    encoded = encode_projected_numpy(grid, x_m, y_m, LEVEL)
    if not np.isfinite(longitude).all() or not np.isfinite(latitude).all():
        raise RuntimeError("point generator produced non-finite WGS84 coordinates")
    if not np.all((encoded.packed_id >= 0) & (encoded.packed_id <= np.iinfo(np.int64).max)):
        raise RuntimeError("packed IDs escaped the non-negative signed Int64 range")
    if len(np.unique(encoded.packed_id)) != len(np.unique(encoded.gid)):
        raise RuntimeError("packed and GID encodings have different unique-cell cardinalities")

    points = {
        "longitude": longitude,
        "latitude": latitude,
        "x_m": x_m,
        "y_m": y_m,
        "packed_id": np.asarray(encoded.packed_id, dtype=np.int64),
        "gid": np.asarray(encoded.gid, dtype=str),
        "value": value,
    }
    generation = {
        "generator": "seeded_uniform_projected_clusters",
        "seed": seed,
        "cluster_count": len(CLUSTER_CENTERS_LONLAT),
        "cluster_sizes": cluster_sizes,
        "cluster_centers_lonlat": [list(point) for point in CLUSTER_CENTERS_LONLAT],
        "cluster_half_side_m": CLUSTER_HALF_SIDE_M,
        "level": LEVEL,
        "unique_packed_cell_count": int(np.unique(points["packed_id"]).size),
        "unique_gid_count": int(np.unique(points["gid"]).size),
    }
    return points, generation


def projected_zone_wkt(
    center_x: float,
    center_y: float,
    to_wgs84: Transformer,
    half_side_m: float,
    segments_per_edge: int = 32,
) -> str:
    projected_ring: list[tuple[float, float]] = []
    corners = (
        (center_x - half_side_m, center_y - half_side_m),
        (center_x + half_side_m, center_y - half_side_m),
        (center_x + half_side_m, center_y + half_side_m),
        (center_x - half_side_m, center_y + half_side_m),
    )
    for index, start in enumerate(corners):
        end = corners[(index + 1) % len(corners)]
        for part in range(segments_per_edge):
            fraction = part / segments_per_edge
            projected_ring.append(
                (
                    start[0] + (end[0] - start[0]) * fraction,
                    start[1] + (end[1] - start[1]) * fraction,
                )
            )
    projected_ring.append(corners[0])
    lonlat = [to_wgs84.transform(x, y) for x, y in projected_ring]
    coordinates = ", ".join(f"{lon:.12f} {lat:.12f}" for lon, lat in lonlat)
    return f"POLYGON (({coordinates}))"


def import_duckdb() -> Any:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - environment setup failure
        raise RuntimeError(
            "DuckDB is required for this comparison benchmark; install duckdb==1.4.3 in the comparison environment"
        ) from exc
    return duckdb


def open_database(threads: int) -> Any:
    duckdb = import_duckdb()
    connection = duckdb.connect(database=":memory:")
    connection.execute(f"PRAGMA threads={int(threads)}")
    try:
        connection.execute("LOAD spatial")
    except Exception:
        try:
            connection.execute("INSTALL spatial")
            connection.execute("LOAD spatial")
        except Exception as exc:
            connection.close()
            raise RuntimeError(
                "DuckDB's spatial extension could not be loaded; the ST_Within workload cannot be measured"
            ) from exc
    return connection


def result_signature(rows: list[tuple[Any, ...]]) -> str:
    if not rows:
        return sha256_bytes(b"empty")
    normalized = sorted((str(row[0]), int(row[1]), float(row[2])) for row in rows)
    first = normalized[0]
    last = normalized[-1]
    payload = {
        "row_count": len(normalized),
        "first": [first[0], first[1], format(first[2], ".17g")],
        "last": [last[0], last[1], format(last[2], ".17g")],
        "count_total": sum(row[1] for row in normalized),
        "value_sum": format(sum(row[2] for row in normalized), ".17g"),
    }
    return canonical_hash(payload)


def summarize_rows(rows: list[tuple[Any, ...]]) -> dict[str, Any]:
    if not rows:
        return {"rows_returned": 0, "count_total": 0, "value_sum": 0.0}
    return {
        "rows_returned": len(rows),
        "count_total": sum(int(row[1]) for row in rows),
        "value_sum": sum(float(row[2]) for row in rows),
        "result_signature": result_signature(rows),
    }


def run_workload(
    connection: Any,
    name: str,
    sql: str,
    parameters: list[Any],
    warmups: int,
    repetitions: int,
    expected_count: int | None = None,
    expected_value_sum: float | None = None,
) -> dict[str, Any]:
    def execute() -> tuple[list[tuple[Any, ...]], float]:
        started = time.perf_counter_ns()
        rows = connection.execute(sql, parameters).fetchall()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
        return rows, elapsed_ms

    warmup_signatures: list[str] = []
    for _ in range(warmups):
        warmup_rows, _ = execute()
        warmup_summary = summarize_rows(warmup_rows)
        warmup_signatures.append(warmup_summary.get("result_signature", "empty"))

    timings_ms: list[float] = []
    measured_signatures: list[str] = []
    measured_summaries: list[dict[str, Any]] = []
    rss_before = peak_rss_bytes()
    for _ in range(repetitions):
        rows, elapsed_ms = execute()
        summary = summarize_rows(rows)
        timings_ms.append(elapsed_ms)
        measured_signatures.append(summary.get("result_signature", "empty"))
        measured_summaries.append(summary)
    rss_after = peak_rss_bytes()

    if len(set(warmup_signatures + measured_signatures)) != 1:
        raise RuntimeError(f"{name} returned inconsistent results across repetitions")
    summary = measured_summaries[0]
    if expected_count is not None and summary["count_total"] != expected_count:
        raise RuntimeError(
            f"{name} returned {summary['count_total']} rows, expected {expected_count}"
        )
    if expected_value_sum is not None and not math.isclose(
        summary["value_sum"], expected_value_sum, rel_tol=1e-10, abs_tol=1e-7
    ):
        raise RuntimeError(
            f"{name} returned value sum {summary['value_sum']}, expected {expected_value_sum}"
        )
    return {
        "sql": sql,
        "warmup_count": warmups,
        "repetition_count": repetitions,
        "timing_ms": {
            "min": min(timings_ms),
            "median": percentile(timings_ms, 0.50),
            "p95": percentile(timings_ms, 0.95),
            "max": max(timings_ms),
            "all": timings_ms,
        },
        "result": summary,
        "result_signature": measured_signatures[0],
        "peak_rss_before_bytes": rss_before,
        "peak_rss_after_bytes": rss_after,
        "peak_rss_delta_bytes": max(0, rss_after - rss_before),
    }


def write_report(output: dict[str, Any], output_sha256: str) -> None:
    workloads = output["workloads"]
    lines = [
        "# Phase 4 query-performance benchmark",
        "",
        "This benchmark measures the vectorized GeoSquare encoding path and DuckDB query workloads over a deterministic one-million-point Indonesia candidate dataset. Packed-Int64 and GID-text aggregation are measured separately from a DuckDB Spatial `ST_Within` polygon predicate; the workloads are not algorithmically equivalent and are not presented as a direct speedup claim.",
        "",
        f"- Run ID: `{output['run_id']}`",
        f"- Repository commit: `{output['repository_commit']}` (working tree dirty: `{output['repository_dirty']}`)",
        f"- Points: `{output['input']['point_count']:,}`; level: `{output['protocol']['level']}`; seed: `{output['protocol']['seed']}`",
        f"- DuckDB threads: `{output['protocol']['duckdb_threads']}`; warmups: `{output['protocol']['warmups']}`; measured repetitions: `{output['protocol']['repetitions']}`",
        f"- JSON artifact SHA-256: `{output_sha256}`",
        "",
        "## Preparation stages",
        "",
        "| Stage | Time (ms) |",
        "|---|---:|",
    ]
    for name, value in output["preparation_ms"].items():
        lines.append(f"| {name} | {value:.3f} |")
    lines.extend(
        [
            "",
            "Preparation and table materialisation are excluded from the SQL timings below.",
            "",
            "## Timed workloads",
            "",
            "| Workload | Rows returned | Median (ms) | p95 (ms) | Peak RSS delta (MiB) |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, workload in workloads.items():
        timing = workload["timing_ms"]
        result = workload["result"]
        memory_mib = workload["peak_rss_delta_bytes"] / (1024 * 1024)
        lines.append(
            f"| `{name}` | {result['rows_returned']:,} | {timing['median']:.3f} | {timing['p95']:.3f} | {memory_mib:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Correctness checks",
            "",
            f"- Every aggregation accounts for `{output['correctness']['expected_point_count']:,}` input rows.",
            f"- Packed and GID aggregations have matching group counts: `{output['correctness']['packed_gid_group_counts_match']}`.",
            f"- The spatial predicate returns the deterministic zone count `{output['correctness']['expected_spatial_zone_count']:,}`.",
            f"- Packed/GID total-value agreement: `{output['correctness']['packed_gid_value_sums_match']}`.",
            "",
            "## Reproducibility and interpretation",
            "",
            "The point population is generated in ten fixed 8 km by 8 km projected clusters centred on Indonesian cities. The spatial workload uses a transformed, densified projected square around the first cluster, not a national legal boundary. Timings include query execution and result materialisation (`fetchall`) but exclude point generation, CRS transformation, GeoSquare encoding, table loading, geometry construction, and serialization. Peak RSS is the process-level resource maximum; the per-workload delta is diagnostic rather than an allocator-isolated measurement.",
            "",
            f"- Input hash: `{output['input']['input_sha256']}`",
            f"- Profile SHA-256: `{output['provenance']['profile_sha256']}`",
            f"- Grid WKT2 SHA-256: `{output['provenance']['wkt2_sha256']}`",
            f"- Spatial-zone WKT SHA-256: `{output['provenance']['zone_wkt_sha256']}`",
            "",
            "The JSON artifact is the authoritative source for all values in this report.",
            "",
            "To reproduce the comparison environment without changing project runtime dependencies, install the exact benchmark-only package with `.venv/bin/python -m pip install duckdb==1.4.3`, then run `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/benchmark_query_performance.py` from the repository root.",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile()
    points_started = time.perf_counter_ns()
    points, generation = generate_points(profile, args.points, args.seed)
    point_generation_ms = (time.perf_counter_ns() - points_started) / 1_000_000.0

    to_wgs84 = Transformer.from_crs(
        CRS.from_user_input(profile.crs_wkt2), CRS.from_epsg(4326), always_xy=True
    )
    center_lon, center_lat = CLUSTER_CENTERS_LONLAT[0]
    to_grid = Transformer.from_crs(
        CRS.from_epsg(4326), CRS.from_user_input(profile.crs_wkt2), always_xy=True
    )
    center_x, center_y = to_grid.transform(center_lon, center_lat)
    zone_wkt = projected_zone_wkt(
        center_x, center_y, to_wgs84, ZONE_HALF_SIDE_M
    )
    zone_wkt_sha256 = sha256_bytes(zone_wkt.encode("utf-8"))
    input_sha256 = input_hash(
        points["longitude"],
        points["latitude"],
        points["x_m"],
        points["y_m"],
        points["packed_id"],
        points["gid"],
        points["value"],
    )
    value_sum = float(np.sum(points["value"], dtype=np.float64))
    expected_zone_mask = (
        (points["x_m"] > center_x - ZONE_HALF_SIDE_M)
        & (points["x_m"] < center_x + ZONE_HALF_SIDE_M)
        & (points["y_m"] > center_y - ZONE_HALF_SIDE_M)
        & (points["y_m"] < center_y + ZONE_HALF_SIDE_M)
    )
    expected_zone_count = int(expected_zone_mask.sum())
    expected_zone_value_sum = float(np.sum(points["value"][expected_zone_mask], dtype=np.float64))

    frame_started = time.perf_counter_ns()
    frame = pd.DataFrame(points)
    frame_ms = (time.perf_counter_ns() - frame_started) / 1_000_000.0

    connection = open_database(args.threads)
    try:
        load_started = time.perf_counter_ns()
        connection.register("input_points", frame)
        connection.execute(
            """
            CREATE TABLE points AS
            SELECT longitude, latitude, x_m, y_m, packed_id, gid, value,
                   ST_Point(longitude, latitude) AS geom
            FROM input_points
            """
        )
        connection.unregister("input_points")
        connection.execute(
            "CREATE TABLE benchmark_zone AS SELECT ST_GeomFromText(?) AS geom",
            [zone_wkt],
        )
        materialization_ms = (time.perf_counter_ns() - load_started) / 1_000_000.0

        workload_sql = {
            "packed_int64_groupby": """
                SELECT packed_id, COUNT(*)::BIGINT AS row_count, SUM(value) AS value_sum
                FROM points
                GROUP BY packed_id
            """,
            "gid_text_groupby": """
                SELECT gid, COUNT(*)::BIGINT AS row_count, SUM(value) AS value_sum
                FROM points
                GROUP BY gid
            """,
            "spatial_st_within_zone": """
                SELECT 'zone' AS result_key, COUNT(*)::BIGINT AS row_count, SUM(points.value) AS value_sum
                FROM points, benchmark_zone
                WHERE ST_Within(points.geom, benchmark_zone.geom)
            """,
        }
        workloads = {
            "packed_int64_groupby": run_workload(
                connection,
                "packed_int64_groupby",
                workload_sql["packed_int64_groupby"],
                [],
                args.warmups,
                args.repetitions,
                expected_count=args.points,
                expected_value_sum=value_sum,
            ),
            "gid_text_groupby": run_workload(
                connection,
                "gid_text_groupby",
                workload_sql["gid_text_groupby"],
                [],
                args.warmups,
                args.repetitions,
                expected_count=args.points,
                expected_value_sum=value_sum,
            ),
            "spatial_st_within_zone": run_workload(
                connection,
                "spatial_st_within_zone",
                workload_sql["spatial_st_within_zone"],
                [],
                args.warmups,
                args.repetitions,
                expected_count=expected_zone_count,
                expected_value_sum=expected_zone_value_sum,
            ),
        }
    finally:
        connection.close()

    packed_result = workloads["packed_int64_groupby"]["result"]
    gid_result = workloads["gid_text_groupby"]["result"]
    correctness = {
        "expected_point_count": args.points,
        "expected_spatial_zone_count": expected_zone_count,
        "expected_spatial_zone_value_sum": expected_zone_value_sum,
        "packed_gid_group_counts_match": generation["unique_packed_cell_count"]
        == generation["unique_gid_count"]
        == packed_result["rows_returned"]
        == gid_result["rows_returned"],
        "packed_gid_value_sums_match": math.isclose(
            packed_result["value_sum"], gid_result["value_sum"], rel_tol=1e-12, abs_tol=1e-7
        ),
        "spatial_zone_count_matches_projected_definition": workloads[
            "spatial_st_within_zone"
        ]["result"]["count_total"]
        == expected_zone_count,
    }
    if not all(correctness.values()):
        raise RuntimeError(f"benchmark correctness checks failed: {correctness}")

    protocol = {
        "benchmark": "GeoSquare v2 Phase 4 query performance",
        "schema_version": "geosquare-phase4-query-performance-v1",
        "domain_code": profile.domain_code,
        "profile_version": profile.profile_version,
        "level": LEVEL,
        "point_count": args.points,
        "seed": args.seed,
        "duckdb_threads": args.threads,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "timing_scope": "DuckDB execute plus fetchall; preparation and serialization excluded",
        "memory_scope": "process resource maximum RSS; per-workload delta is diagnostic",
        "point_distribution": generation,
        "spatial_workload": {
            "predicate": "ST_Within",
            "zone_definition": "densified projected square around the first fixed cluster centre",
            "zone_half_side_m": ZONE_HALF_SIDE_M,
            "segments_per_edge": 32,
        },
    }
    output = {
        "schema_version": "geosquare-phase4-query-performance-v1",
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "generated_at_utc": utc_now(),
        "repository_commit": git_commit(),
        "repository_dirty": git_dirty(),
        "protocol": protocol,
        "input": {
            "point_count": args.points,
            "columns": ["longitude", "latitude", "x_m", "y_m", "packed_id", "gid", "value", "geom"],
            "input_sha256": input_sha256,
            "value_sum": value_sum,
        },
        "preparation_ms": {
            "point_generation_and_encoding": point_generation_ms,
            "dataframe_materialization": frame_ms,
            "duckdb_table_and_geometry_materialization": materialization_ms,
        },
        "workloads": workloads,
        "correctness": correctness,
        "provenance": {
            "profile_path": str(PROFILE_PATH.relative_to(ROOT)),
            "profile_sha256": sha256_path(PROFILE_PATH),
            "wkt2_sha256": sha256_bytes(profile.crs_wkt2.encode("utf-8")),
            "grid_crs_authority": profile.crs_authority,
            "candidate_status": "candidate-unverified",
            "zone_wkt_sha256": zone_wkt_sha256,
            "zone_wkt": zone_wkt,
        },
        "software": software_metadata(),
        "hardware": {
            "platform_uname": platform.uname()._asdict(),
            "cpu_count": os.cpu_count(),
        },
    }
    PHASE4_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_sha256 = sha256_path(OUTPUT_PATH)
    write_report(output, output_sha256)
    report_sha256 = sha256_path(REPORT_PATH)
    manifest = {
        "schema_version": "geosquare-phase4-run-manifest-v1",
        "run_id": output["run_id"],
        "repository_commit": output["repository_commit"],
        "repository_dirty": output["repository_dirty"],
        "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
        "output_sha256": output_sha256,
        "report_path": str(REPORT_PATH.relative_to(ROOT)),
        "report_sha256": report_sha256,
        "input_sha256": input_sha256,
        "profile_sha256": output["provenance"]["profile_sha256"],
        "zone_wkt_sha256": zone_wkt_sha256,
        "software": output["software"],
        "protocol": protocol,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=DEFAULT_POINTS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    if args.points <= 0 or args.warmups < 0 or args.repetitions <= 0 or args.threads <= 0:
        parser.error("points and repetitions must be positive; warmups may be zero; threads must be positive")
    return args


def main() -> None:
    output = run(parse_args())
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")
    for name, workload in output["workloads"].items():
        print(
            f"{name}: median={workload['timing_ms']['median']:.3f} ms, "
            f"p95={workload['timing_ms']['p95']:.3f} ms, "
            f"rows={workload['result']['rows_returned']}"
        )


if __name__ == "__main__":
    main()
