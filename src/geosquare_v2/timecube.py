"""Reference rules for the L7 time cube dataset type ``cell_time_values``.

A time-value dataset has one row per (cell, period). All periods in one dataset
share one granularity. Every label stands for a half-open interval in UTC. A row
can join another row when their intervals contain each other or overlap.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from typing import Any

from .codec import gid_to_indices
from .errors import ValidationError

PERIOD_TYPES: tuple[str, ...] = ("year", "month", "day", "hour")
BUCKET_HOURS: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 12)
TIME_AGGREGATIONS: tuple[str, ...] = ("mean", "min", "max")

_LABEL_PATTERNS: dict[str, re.Pattern[str]] = {
    "year": re.compile(r"[0-9]{4}"),
    "month": re.compile(r"[0-9]{4}-[0-9]{2}"),
    "day": re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}"),
    "hour": re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}"),
}


class TimeCubeError(ValidationError):
    """A time-value label, manifest or row breaks the ``cell_time_values`` contract."""


def parse_label(label: Any, period_type: str, bucket_hours: int | None = None) -> datetime:
    """Return the UTC start of a canonical period label.

    Labels: ``YYYY``, ``YYYY-MM``, ``YYYY-MM-DD``, ``YYYY-MM-DDTHH``. There are no
    offsets, spaces or short forms. An hour label must start a bucket of
    ``bucket_hours`` hours, aligned to 00 UTC.
    """
    if period_type not in PERIOD_TYPES:
        raise TimeCubeError(f"unknown period_type {period_type!r}")
    if period_type == "hour":
        if type(bucket_hours) is not int or bucket_hours not in BUCKET_HOURS:
            raise TimeCubeError(f"bucket_hours must be one of {BUCKET_HOURS}; received {bucket_hours!r}")
    elif bucket_hours is not None:
        raise TimeCubeError("bucket_hours is only allowed for period_type 'hour'")
    if type(label) is not str or not _LABEL_PATTERNS[period_type].fullmatch(label):
        raise TimeCubeError(f"{label!r} is not a canonical {period_type} label")
    try:
        if period_type == "year":
            year = int(label)
            if year < 1:
                raise ValueError("year 0000 does not exist")
            return datetime(year, 1, 1)
        if period_type == "month":
            return datetime(int(label[:4]), int(label[5:7]), 1)
        if period_type == "day":
            return datetime.strptime(label, "%Y-%m-%d")
        hour = int(label[11:13])
        if hour > 23:
            raise ValueError("hour must be 00 to 23")
        if hour % bucket_hours:
            raise ValueError(f"hour {hour:02d} does not start a {bucket_hours}-hour bucket")
        return datetime.strptime(label[:10], "%Y-%m-%d").replace(hour=hour)
    except ValueError as exc:
        raise TimeCubeError(f"{label!r} is not a real {period_type}: {exc}") from exc


def interval(label: str, period_type: str, bucket_hours: int | None = None) -> tuple[datetime, datetime]:
    """Return ``[start, end)`` for one label. ``end`` is the first instant outside the period."""
    start = parse_label(label, period_type, bucket_hours)
    try:
        if period_type == "year":
            end = datetime(start.year + 1, 1, 1)
        elif period_type == "month":
            end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
        elif period_type == "day":
            end = start + timedelta(days=1)
        else:
            end = start + timedelta(hours=bucket_hours)
    except (ValueError, OverflowError) as exc:
        raise TimeCubeError(f"{label!r} has no exclusive end inside years 0001 to 9999") from exc
    return start, end


def validate_manifest(manifest: Mapping[str, Any]) -> tuple[datetime, datetime]:
    """Check the time fields of a manifest. Return the declared ``[start, end)`` range."""
    if manifest.get("dataset_type") != "cell_time_values":
        raise TimeCubeError("dataset_type must be cell_time_values")
    if manifest.get("timezone") != "UTC":
        raise TimeCubeError("timezone must be UTC; convert local time before storing")
    period_type = manifest.get("period_type")
    bucket = manifest.get("bucket_hours")
    start = parse_label(manifest.get("period_start"), period_type, bucket)
    end = parse_label(manifest.get("period_end"), period_type, bucket)
    if start >= end:
        raise TimeCubeError("period_start must be before period_end; the range is half-open and must not be empty")
    identity = manifest.get("identity", {})
    if identity.get("unique_gid") is not False or identity.get("unique_key") != ["gid", "period"]:
        raise TimeCubeError("identity must use unique_key [gid, period] and unique_gid false")
    if manifest.get("storage", {}).get("sorted_by") != ["gid", "period"]:
        raise TimeCubeError("storage.sorted_by must be [gid, period]")
    names = [field.get("name") for field in manifest.get("value_fields", [])]
    if "period" in names:
        raise TimeCubeError("period is reserved and cannot be a value field")
    return start, end


def validate_rows(rows: Iterable[Mapping[str, Any]], manifest: Mapping[str, Any]) -> None:
    """Check rows against the manifest: level, range, uniqueness and sort order."""
    start, end = validate_manifest(manifest)
    period_type = manifest["period_type"]
    bucket = manifest.get("bucket_hours")
    level = manifest["level"]
    previous: tuple[str, str] | None = None
    seen: set[tuple[str, str]] = set()
    for row in rows:
        gid = row["gid"]
        period = row["period"]
        if gid_to_indices(gid)[0] != level:
            raise TimeCubeError(f"GID {gid!r} is not at level {level}")
        moment = parse_label(period, period_type, bucket)
        if not start <= moment < end:
            raise TimeCubeError(f"period {period!r} is outside the declared range")
        key = (gid, period)
        if key in seen:
            raise TimeCubeError(f"duplicate (gid, period) pair {key!r}")
        if previous is not None and key < previous:
            raise TimeCubeError("rows must be sorted by gid, then period")
        seen.add(key)
        previous = key


def time_rollup(semantics: str, declared: str | None = None) -> str:
    """Return the rule for rolling one field up in time.

    COUNT and TOTAL sum. MEASUREMENT needs a declared mean, min or max. CATEGORICAL
    cannot be rolled up in time.
    """
    if semantics in ("COUNT", "TOTAL"):
        return "sum"
    if semantics == "MEASUREMENT":
        if declared in TIME_AGGREGATIONS:
            return declared
        raise TimeCubeError("MEASUREMENT needs a declared time_aggregation of mean, min or max")
    raise TimeCubeError(f"{semantics} cannot be rolled up in time")


def relation(
    left: tuple[str, str, int | None],
    right: tuple[str, str, int | None],
) -> str:
    """Compare two labels. Each side is ``(label, period_type, bucket_hours)``.

    Returns ``equal``, ``contains`` (left contains right), ``contained`` (left inside
    right), ``overlap`` or ``disjoint``.
    """
    a0, a1 = interval(*left)
    b0, b1 = interval(*right)
    if (a0, a1) == (b0, b1):
        return "equal"
    if a0 <= b0 and b1 <= a1:
        return "contains"
    if b0 <= a0 and a1 <= b1:
        return "contained"
    if a0 < b1 and b0 < a1:
        return "overlap"
    return "disjoint"
