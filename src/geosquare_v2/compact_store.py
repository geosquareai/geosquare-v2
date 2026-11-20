"""Write and read `cell_compact_set` datasets: one manifest and one Parquet file.

The rules come from `geosquare_v2.compact`. Every read checks the manifest, the
row count, the Parquet columns and the rules. A stored set that breaks a rule is
rejected. It is never repaired.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .codec import gid_to_indices
from .compact import CompactSetError, validate_compact_set
from .errors import CellDatasetError

MANIFEST_NAME = "manifest.json"
DATA_NAME = "compact.parquet"
COLUMNS = ("gid", "level")


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on installed extras
        raise CellDatasetError("pyarrow is required for compact set storage; install geosquare-v2[table]") from exc
    return pa, pq


def _check(rows: list[tuple[str, int]]) -> None:
    try:
        validate_compact_set(rows)
    except CompactSetError as exc:
        raise CellDatasetError(f"compact set rejected: {exc}") from exc


def write_compact_set(
    path: str | Path,
    rows: Iterable[tuple[str, int]],
    *,
    domain_code: str,
    domain_id: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Check `rows` and write a compact set under `path`. `path` must not exist."""
    pa, pq = _require_pyarrow()
    destination = Path(path)
    if destination.exists():
        raise CellDatasetError(f"{destination} already exists")
    stored = sorted((str(gid), int(level)) for gid, level in rows)
    _check(stored)
    manifest = {
        "manifest_version": "1.0",
        "dataset_type": "cell_compact_set",
        "grid_system": "geosquare",
        "grid_version": "v2",
        "domain_code": domain_code,
        "domain_id": domain_id,
        "levels_present": sorted({level for _, level in stored}),
        "identity": {"gid_column": "gid", "level_column": "level", "unique_gid": True, "mixed_levels": True},
        "storage": {
            "parquet_compression": "zstd",
            "sorted_by": ["gid"],
            "row_count": len(stored),
            "partitioning": [],
        },
        "provenance": {
            "created_at": created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generator": "geosquare_v2.compact_store",
            "rules": "docs/cell-dataset-contract.md section 2",
        },
    }
    table = pa.table(
        {
            "gid": pa.array([gid for gid, _ in stored], type=pa.string()),
            "level": pa.array([level for _, level in stored], type=pa.int8()),
        }
    )
    staging = destination.with_name(destination.name + ".tmp")
    (staging / "data").mkdir(parents=True, exist_ok=False)
    pq.write_table(table, staging / "data" / DATA_NAME, compression="zstd")
    (staging / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    staging.rename(destination)
    return manifest


def read_compact_set(path: str | Path) -> tuple[dict[str, Any], tuple[tuple[str, int], ...]]:
    """Read and check a stored compact set. Return its manifest and its `(gid, level)` rows."""
    _, pq = _require_pyarrow()
    root = Path(path)
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CellDatasetError("manifest is missing or not JSON") from exc
    if manifest.get("dataset_type") != "cell_compact_set":
        raise CellDatasetError("dataset_type must be cell_compact_set")
    if manifest.get("identity", {}).get("mixed_levels") is not True:
        raise CellDatasetError("identity.mixed_levels must be true for cell_compact_set")
    table = pq.read_table(root / "data" / DATA_NAME)
    if tuple(table.column_names) != COLUMNS:
        raise CellDatasetError(f"columns must be exactly {list(COLUMNS)}")
    rows = tuple(zip(table.column("gid").to_pylist(), table.column("level").to_pylist()))
    if len(rows) != manifest["storage"]["row_count"]:
        raise CellDatasetError("row count does not match the manifest")
    for gid, level in rows:
        if gid is None or level is None or gid_to_indices(gid)[0] != level:
            raise CellDatasetError(f"row {gid!r} has a level that does not match its GID")
    if sorted(set(level for _, level in rows)) != manifest["levels_present"]:
        raise CellDatasetError("levels_present does not match the rows")
    _check(list(rows))
    return manifest, rows
