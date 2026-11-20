"""Round trips and rejection for the cell_compact_set and cell_time_values stores."""

from __future__ import annotations

import json

import pytest

from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.compact_store import read_compact_set, write_compact_set
from geosquare_v2.errors import CellDatasetError
from geosquare_v2.time_store import read_time_values, write_time_values

LEVEL1_CELL = canonical_to_gid(1, 0, 0)
LEVEL9_A = canonical_to_gid(9, 0, 0)
LEVEL9_B = canonical_to_gid(9, 0, 1)


def _write_compact(tmp_path, rows, name="set"):
    return write_compact_set(tmp_path / name, rows, domain_code="ID", domain_id=1, created_at="2026-11-20T00:00:00Z")


def test_compact_set_round_trip(tmp_path):
    _write_compact(tmp_path, [(LEVEL1_CELL, 1)])
    manifest, rows = read_compact_set(tmp_path / "set")
    assert manifest["dataset_type"] == "cell_compact_set"
    assert rows == ((LEVEL1_CELL, 1),)


def test_compact_set_refuses_non_canonical_rows(tmp_path):
    children = [canonical_to_gid(2, x, y) for y in range(2) for x in range(2)]
    assert len(children) == 4
    with pytest.raises(CellDatasetError, match="not canonical"):
        _write_compact(tmp_path, [(gid, 2) for gid in children])
    assert not (tmp_path / "set").exists()


def test_compact_set_reader_rejects_row_count_tampering(tmp_path):
    _write_compact(tmp_path, [(LEVEL1_CELL, 1)])
    manifest_path = tmp_path / "set" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["storage"]["row_count"] = 2
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CellDatasetError, match="row count"):
        read_compact_set(tmp_path / "set")


def _time_manifest_args(**overrides):
    args = {
        "domain_code": "ID",
        "domain_id": 1,
        "level": 9,
        "period_type": "day",
        "period_start": "2026-11-01",
        "period_end": "2026-12-01",
        "value_fields": [{"name": "rain_mm", "semantics": "MEASUREMENT", "time_aggregation": "mean"}],
        "created_at": "2026-11-20T00:00:00Z",
    }
    args.update(overrides)
    return args


def test_time_values_round_trip_keeps_rows_sorted(tmp_path):
    rows = [
        {"gid": LEVEL9_B, "period": "2026-11-02", "rain_mm": 1.5},
        {"gid": LEVEL9_A, "period": "2026-11-02", "rain_mm": 0.0},
        {"gid": LEVEL9_A, "period": "2026-11-01", "rain_mm": 12.4},
    ]
    write_time_values(tmp_path / "tv", rows, **_time_manifest_args())
    manifest, stored = read_time_values(tmp_path / "tv")
    assert manifest["storage"]["row_count"] == 3
    assert [(row["gid"], row["period"]) for row in stored] == sorted((row["gid"], row["period"]) for row in rows)


def test_time_values_refuse_duplicate_pair(tmp_path):
    rows = [
        {"gid": LEVEL9_A, "period": "2026-11-01", "rain_mm": 1.0},
        {"gid": LEVEL9_A, "period": "2026-11-01", "rain_mm": 2.0},
    ]
    with pytest.raises(CellDatasetError, match="duplicate"):
        write_time_values(tmp_path / "tv", rows, **_time_manifest_args())


def test_time_values_refuse_period_outside_range(tmp_path):
    rows = [{"gid": LEVEL9_A, "period": "2026-12-01", "rain_mm": 1.0}]
    with pytest.raises(CellDatasetError, match="outside"):
        write_time_values(tmp_path / "tv", rows, **_time_manifest_args())


def test_time_values_reader_rejects_local_timezone(tmp_path):
    rows = [{"gid": LEVEL9_A, "period": "2026-11-01", "rain_mm": 1.0}]
    write_time_values(tmp_path / "tv", rows, **_time_manifest_args())
    manifest_path = tmp_path / "tv" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["timezone"] = "Asia/Jakarta"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(CellDatasetError, match="UTC"):
        read_time_values(tmp_path / "tv")


def test_hourly_bucket_dataset_round_trip(tmp_path):
    hour_rows = [
        {"gid": LEVEL9_A, "period": "2026-11-19T00", "mobile_devices": 5.0},
        {"gid": LEVEL9_A, "period": "2026-11-19T04", "mobile_devices": 7.0},
    ]
    args = _time_manifest_args(
        period_type="hour",
        bucket_hours=4,
        period_start="2026-11-19T00",
        period_end="2026-11-20T00",
        value_fields=[{"name": "mobile_devices", "semantics": "COUNT"}],
    )
    write_time_values(tmp_path / "hours", hour_rows, **args)
    manifest, stored = read_time_values(tmp_path / "hours")
    assert manifest["bucket_hours"] == 4
    assert len(stored) == 2
