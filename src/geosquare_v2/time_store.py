"""Write and read `cell_time_values` datasets: one manifest and one Parquet file.

The rules come from `geosquare_v2.timecube`. Every write and read checks the
manifest, the rows and the Parquet columns. A stored dataset that breaks a rule
is rejected. It is never repaired.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import CellDatasetError
from .timecube import TimeCubeError, validate_manifest, validate_rows

MANIFEST_NAME = "manifest.json"
DATA_NAME = "time_values.parquet"
NUMERIC_SEMANTICS = ("COUNT", "TOTAL", "MEASUREMENT")


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise CellDatasetError("pyarrow is required for time-value storage; install geosquare-v2[table]") from exc
    return pa, pq


def _value_fields(fields: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for field in fields:
        semantics = field.get("semantics")
        if semantics not in (*NUMERIC_SEMANTICS, "CATEGORICAL"):
            raise CellDatasetError(f"unknown semantics {semantics!r} for {field.get('name')!r}")
        result.append(
            {
                "name": field["name"],
                "semantics": semantics,
                "logical_type": "categorical" if semantics == "CATEGORICAL" else "numeric",
                "unit": field.get("unit"),
                "time_aggregation": field.get("time_aggregation"),
            }
        )
    return result


def write_time_values(
    path: str | Path,
    rows: Iterable[Mapping[str, Any]],
    *,
    domain_code: str,
    domain_id: int,
    level: int,
    period_type: str,
    period_start: str,
    period_end: str,
    value_fields: Sequence[Mapping[str, Any]],
    bucket_hours: int | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Check the manifest and rows, then write the dataset under `path`. `path` must not exist."""
    pa, pq = _require_pyarrow()
    destination = Path(path)
    if destination.exists():
        raise CellDatasetError(f"{destination} already exists")
    fields = _value_fields(value_fields)
    manifest = {
        "manifest_version": "1.0",
        "dataset_type": "cell_time_values",
        "grid_system": "geosquare",
        "grid_version": "v2",
        "domain_code": domain_code,
        "domain_id": domain_id,
        "level": level,
        "period_type": period_type,
        "bucket_hours": bucket_hours,
        "timezone": "UTC",
        "period_start": period_start,
        "period_end": period_end,
        "identity": {
            "gid_column": "gid",
            "period_column": "period",
            "unique_gid": False,
            "unique_key": ["gid", "period"],
        },
        "storage": {
            "parquet_compression": "zstd",
            "sorted_by": ["gid", "period"],
            "partitioning": [],
        },
        "value_fields": fields,
        "provenance": {
            "created_at": created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generator": "geosquare_v2.time_store",
        },
    }
    ordered = sorted(rows, key=lambda row: (row["gid"], row["period"]))
    try:
        validate_manifest(manifest)
        validate_rows(ordered, manifest)
    except TimeCubeError as exc:
        raise CellDatasetError(f"time values rejected: {exc}") from exc
    manifest["storage"]["row_count"] = len(ordered)

    arrays: dict[str, Any] = {
        "gid": pa.array([row["gid"] for row in ordered], type=pa.string()),
        "period": pa.array([row["period"] for row in ordered], type=pa.string()),
    }
    for field in fields:
        values = [row.get(field["name"]) for row in ordered]
        if field["logical_type"] == "numeric":
            arrays[field["name"]] = pa.array(values, type=pa.float64())
        else:
            arrays[field["name"]] = pa.array(values, type=pa.string())
    table = pa.table(arrays)

    staging = destination.with_name(destination.name + ".tmp")
    (staging / "data").mkdir(parents=True, exist_ok=False)
    pq.write_table(table, staging / "data" / DATA_NAME, compression="zstd")
    (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    staging.rename(destination)
    return manifest


def read_time_values(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read and check a stored dataset. Return its manifest and its rows."""
    _, pq = _require_pyarrow()
    root = Path(path)
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CellDatasetError("manifest is missing or not JSON") from exc
    table = pq.read_table(root / "data" / DATA_NAME)
    expected = ["gid", "period"] + [field["name"] for field in manifest.get("value_fields", [])]
    if table.column_names != expected:
        raise CellDatasetError(f"columns must be exactly {expected}")
    rows = table.to_pylist()
    if len(rows) != manifest.get("storage", {}).get("row_count"):
        raise CellDatasetError("row count does not match the manifest")
    try:
        validate_manifest(manifest)
        validate_rows(rows, manifest)
    except TimeCubeError as exc:
        raise CellDatasetError(f"stored time values rejected: {exc}") from exc
    return manifest, rows

