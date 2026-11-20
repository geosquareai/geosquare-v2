"""cell_time_values: committed vectors and independent checks of the time rules."""

from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import pytest

from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.timecube import BUCKET_HOURS, TimeCubeError, interval, parse_label, relation, validate_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = REPO_ROOT / "conformance" / "spec-2.0" / "time-values.json"
GENERATOR = REPO_ROOT / "tools" / "generate_conformance_vectors.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_conformance_vectors", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _vectors() -> dict:
    return json.loads(VECTOR_FILE.read_text(encoding="utf-8"))


def test_committed_cases_match_reference_rules():
    data = _vectors()
    assert data["dataset_type"] == "cell_time_values"
    evaluate = _load_generator().evaluate_time_case
    for case in data["cases"]:
        assert evaluate(case) == case["expect"], case["name"]


def test_case_names_are_unique_and_cover_every_operation():
    cases = _vectors()["cases"]
    names = [case["name"] for case in cases]
    assert len(names) == len(set(names))
    assert {case["operation"] for case in cases} == {"parse", "interval", "manifest", "rows", "rollup", "relation"}


@pytest.mark.parametrize("bucket", BUCKET_HOURS)
def test_every_allowed_bucket_gives_its_own_length(bucket):
    start, end = interval("2026-11-19T00", "hour", bucket)
    assert end - start == timedelta(hours=bucket)


def test_leap_day_rule_follows_the_gregorian_calendar():
    assert parse_label("2000-02-29", "day") is not None
    assert parse_label("2024-02-29", "day") is not None
    with pytest.raises(TimeCubeError):
        parse_label("2100-02-29", "day")


def test_year_9999_has_no_exclusive_end():
    assert parse_label("9999", "year").year == 9999
    with pytest.raises(TimeCubeError):
        interval("9999", "year")


def test_relation_is_antisymmetric_for_containment():
    labels = [("2026", "year", None), ("2026-11", "month", None), ("2026-11-19", "day", None), ("2026-11-19T04", "hour", 4)]
    for left in labels:
        for right in labels:
            forward = relation(left, right)
            backward = relation(right, left)
            if forward == "contains":
                assert backward == "contained", (left, right)
            if forward == "equal":
                assert backward == "equal", (left, right)


def test_rows_pass_for_a_month_window_of_daily_values():
    manifest = {
        "dataset_type": "cell_time_values",
        "level": 9,
        "period_type": "day",
        "bucket_hours": None,
        "timezone": "UTC",
        "period_start": "2026-11-01",
        "period_end": "2026-12-01",
        "identity": {"unique_gid": False, "unique_key": ["gid", "period"]},
        "storage": {"sorted_by": ["gid", "period"]},
        "value_fields": [{"name": "rain_mm", "semantics": "MEASUREMENT", "time_aggregation": "mean"}],
    }
    gid = canonical_to_gid(9, 0, 0)
    rows = [{"gid": gid, "period": f"2026-11-{day:02d}"} for day in range(1, 31)]
    validate_rows(rows, manifest)
