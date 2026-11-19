"""Validation helpers for source-unit to GeoSquare-cell crosswalk tables."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import math
from typing import Any

from .codec import MAX_LEVEL, gid_to_indices
from .errors import InvalidGIDError, ValidationError

_FORMAT_VERSION = "1.0"
_SPEC_VERSION = "2.0"
_WEIGHT_KINDS = frozenset(("luas", "bangunan", "populasi", "lainnya"))
# The eleven ASEAN domains in registry 2.0.0 (release/registry.v2.json).
KNOWN_DOMAIN_CODES = frozenset(("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"))
_REQUIRED_MANIFEST_FIELDS = frozenset(
    (
        "format_version",
        "spec_version",
        "domain_code",
        "level",
        "weight_kind",
        "source_description",
        "created_at",
        "registry_version",
    )
)
_REQUIRED_ROW_FIELDS = frozenset(("sumber_id", "gid", "bobot"))


def _fail(message: str) -> ValidationError:
    return ValidationError(message)


def _validate_manifest(manifest: Mapping[str, Any]) -> int:
    if not isinstance(manifest, Mapping):
        raise _fail("manifest must be an object")

    missing = sorted(_REQUIRED_MANIFEST_FIELDS - set(manifest))
    if missing:
        raise _fail(f"manifest is missing required field(s): {', '.join(missing)}")

    if manifest["format_version"] != _FORMAT_VERSION:
        raise _fail("manifest format_version must be '1.0'")
    if manifest["spec_version"] != _SPEC_VERSION:
        raise _fail("manifest spec_version must be '2.0'")

    domain_code = manifest["domain_code"]
    if not isinstance(domain_code, str) or domain_code not in KNOWN_DOMAIN_CODES:
        choices = ", ".join(sorted(KNOWN_DOMAIN_CODES))
        raise _fail(f"manifest domain_code must be one of {choices}")

    level = manifest["level"]
    if type(level) is not int or not 0 <= level <= MAX_LEVEL:
        raise _fail(f"manifest level must be an integer in [0, {MAX_LEVEL}]")

    weight_kind = manifest["weight_kind"]
    if not isinstance(weight_kind, str) or weight_kind not in _WEIGHT_KINDS:
        choices = ", ".join(sorted(_WEIGHT_KINDS))
        raise _fail(f"manifest weight_kind must be one of {choices}")

    for field in ("source_description", "registry_version"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            raise _fail(f"manifest {field} must be a non-empty string")

    created_at = manifest["created_at"]
    if not isinstance(created_at, str) or not created_at.strip():
        raise _fail("manifest created_at must be an ISO 8601 string")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail("manifest created_at must be an ISO 8601 string") from exc

    return level


def _validate_row(row: Any, row_number: int, level: int) -> tuple[str, str, float]:
    label = f"row {row_number}"
    if not isinstance(row, Mapping):
        raise _fail(f"{label} must be an object with sumber_id, gid, and bobot")
    missing = sorted(_REQUIRED_ROW_FIELDS - set(row))
    if missing:
        raise _fail(f"{label} is missing required field(s): {', '.join(missing)}")

    sumber_id = row["sumber_id"]
    if not isinstance(sumber_id, str) or not sumber_id.strip():
        raise _fail(f"{label} has an empty sumber_id")

    gid = row["gid"]
    if not isinstance(gid, str):
        raise _fail(f"{label} for sumber_id {sumber_id!r} has an invalid gid")
    try:
        gid_level, _, _ = gid_to_indices(gid)
    except InvalidGIDError as exc:
        raise _fail(f"{label} for sumber_id {sumber_id!r} has an invalid gid {gid!r}: {exc}") from exc
    if gid_level != level:
        raise _fail(
            f"{label} for sumber_id {sumber_id!r} has gid {gid!r} at level {gid_level}; "
            f"manifest requires level {level}"
        )

    bobot = row["bobot"]
    if isinstance(bobot, bool) or not isinstance(bobot, (int, float)):
        raise _fail(f"{label} for sumber_id {sumber_id!r} has bobot that is not a number")
    bobot_float = float(bobot)
    if not math.isfinite(bobot_float):
        raise _fail(f"{label} for sumber_id {sumber_id!r} has bobot that is not finite")
    if bobot_float <= 0:
        raise _fail(f"{label} for sumber_id {sumber_id!r} has bobot <= 0")

    return sumber_id, gid, bobot_float


def validate_crosswalk(rows: Iterable[Mapping[str, Any]], manifest: Mapping[str, Any]) -> dict[str, int]:
    """Validate a source-unit to V2-cell crosswalk and return row counts.

    ``rows`` must contain mappings with ``sumber_id``, ``gid``, and ``bobot``.
    The manifest declares the required GID level and crosswalk metadata. Every
    source unit's positive finite weights must sum to 1 within ``1e-9``.
    """
    level = _validate_manifest(manifest)
    totals: dict[str, float] = {}
    seen_pairs: set[tuple[str, str]] = set()
    cells: set[str] = set()
    row_count = 0

    try:
        iterator = iter(rows)
    except TypeError as exc:
        raise _fail("rows must be an iterable of row objects") from exc

    for row_number, row in enumerate(iterator, start=1):
        sumber_id, gid, bobot = _validate_row(row, row_number, level)
        pair = (sumber_id, gid)
        if pair in seen_pairs:
            raise _fail(f"row {row_number} duplicates (sumber_id, gid) pair {pair!r}")
        seen_pairs.add(pair)
        totals[sumber_id] = totals.get(sumber_id, 0.0) + bobot
        cells.add(gid)
        row_count += 1

    if not totals:
        raise _fail("crosswalk has no rows")

    for sumber_id, total in totals.items():
        if abs(total - 1.0) > 1e-9:
            raise _fail(f"weights for sumber_id {sumber_id!r} sum to {total:.17g}, expected 1 within 1e-9")

    return {"sources": len(totals), "rows": row_count, "cells": len(cells)}


def polygon_crosswalk_rows(polygons: Iterable[tuple[str, Any]], grid: Any, level: int, *, tolerance: float = 1e-6) -> list[dict[str, Any]]:
    """Build area-share crosswalk rows from source polygons already in the grid CRS.

    Each ``(sumber_id, polygon)`` pair gives one row per overlapped cell. The weight is the
    overlap area divided by the polygon area, both measured in the grid CRS. Candidate cells
    come from ``polygon_to_cells``. A polygon whose candidate cells do not cover its full area
    raises ``ValidationError``, so no source loses area silently. Weights are renormalised so
    each source sums to exactly 1, as ``validate_crosswalk`` requires.
    """
    from .conversion import polygon_to_cells
    from .geometry import projected_cell_geometry

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sumber_id, polygon in polygons:
        if not isinstance(sumber_id, str) or not sumber_id.strip():
            raise _fail("polygon sumber_id must be a non-empty string")
        if sumber_id in seen:
            raise _fail(f"duplicate sumber_id {sumber_id!r}")
        seen.add(sumber_id)
        total = polygon.area
        if polygon.is_empty or not math.isfinite(total) or total <= 0:
            raise _fail(f"sumber_id {sumber_id!r} has no area")

        pieces: dict[str, float] = {}
        for record in polygon_to_cells(grid, polygon, grid.profile.crs_wkt2, level):
            if record.gid in pieces:
                raise _fail(f"sumber_id {sumber_id!r} lists cell {record.gid!r} twice")
            overlap = projected_cell_geometry(grid, record.gid).intersection(polygon).area
            if overlap > 0:
                pieces[record.gid] = overlap

        covered = sum(pieces.values())
        if abs(covered / total - 1) > tolerance:
            raise _fail(
                f"candidate cells cover {covered / total:.9f} of sumber_id {sumber_id!r}; expected 1"
            )
        for gid, area in pieces.items():
            rows.append({"sumber_id": sumber_id, "gid": gid, "bobot": area / covered})

    if not rows:
        raise _fail("no polygons produced cells")
    return rows
