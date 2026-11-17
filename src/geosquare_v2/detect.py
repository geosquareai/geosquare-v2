"""Reference detector for V2 spatial key columns (spec 2.0, section 14).

The detector classifies values. It never converts, trims, lowercases, or repairs
them. A column is accepted only when enough of its non-null values pass the strict
codec or packing checks. Anything else is rejected with a reason.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .codec import SUBDIVISIONS, gid_to_indices, side_cell_count
from .errors import GeosquareError
from .packing import pack_int64, unpack_int64

MIN_GID_LENGTH = 5
MIN_VALID_RATIO = 0.99
EXAMPLE_LIMIT = 3

KIND_URI = "uri"
KIND_GID = "gid"
KIND_PACKED = "packed_id"
KIND_XY = "xy_indices"
KIND_NONE = "none"

STATUS_CERTAIN = "certain"
STATUS_NEEDS_DOMAIN = "needs_domain"
STATUS_NEEDS_LEVEL = "needs_level"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
STATUS_REJECTED = "rejected"

DTYPE_STRING = "string"
DTYPE_INT64 = "int64"

_URI_PATTERN = re.compile(r"^geosquare:v2:([A-Z][A-Z0-9]{0,15}):([^:]+)$")
_URI_PREFIX = "geosquare:v2:"


@dataclass(frozen=True)
class ColumnDetection:
    """Outcome for one column or one x_idx/y_idx pair."""

    column: str
    kind: str
    status: str
    reason: str
    valid_ratio: float
    domain_codes: tuple[str, ...] = ()
    domain_ids: tuple[int, ...] = ()
    levels: tuple[int, ...] = ()
    invalid_examples: tuple[str, ...] = ()


def _non_null(values: Sequence[Any]) -> list[Any]:
    return [value for value in values if value is not None]


def _examples(invalid: list[str]) -> tuple[str, ...]:
    return tuple(invalid[:EXAMPLE_LIMIT])


def _is_valid_gid(value: Any) -> int | None:
    """Return the GID level when ``value`` is a strict V2 GID of accepted length."""
    if type(value) is not str or not MIN_GID_LENGTH <= len(value) <= len(SUBDIVISIONS):
        return None
    try:
        level, _, _ = gid_to_indices(value)
    except GeosquareError:
        return None
    return level


def _detect_uri(column: str, values: list[Any], domain_code: str | None) -> ColumnDetection:
    valid_domains: list[str] = []
    levels: set[int] = set()
    invalid: list[str] = []
    for value in values:
        match = _URI_PATTERN.match(value) if type(value) is str else None
        level = _is_valid_gid(match.group(2)) if match else None
        if match is None or level is None or (domain_code is not None and match.group(1) != domain_code):
            invalid.append(str(value))
            continue
        valid_domains.append(match.group(1))
        levels.add(level)
    ratio = (len(values) - len(invalid)) / len(values)
    domains = tuple(sorted(set(valid_domains)))
    if ratio < MIN_VALID_RATIO:
        return ColumnDetection(
            column, KIND_URI, STATUS_REJECTED,
            f"{ratio:.2%} of values are valid URIs, below {MIN_VALID_RATIO:.0%}",
            ratio, invalid_examples=_examples(invalid),
        )
    return ColumnDetection(
        column, KIND_URI, STATUS_CERTAIN, "valid geosquare:v2 URIs",
        ratio, domain_codes=domains, levels=tuple(sorted(levels)), invalid_examples=_examples(invalid),
    )


def _detect_gid(column: str, values: list[Any], domain_code: str | None) -> ColumnDetection:
    levels: set[int] = set()
    invalid: list[str] = []
    for value in values:
        level = _is_valid_gid(value)
        if level is None:
            invalid.append(str(value))
        else:
            levels.add(level)
    ratio = (len(values) - len(invalid)) / len(values)
    if ratio < MIN_VALID_RATIO:
        return ColumnDetection(
            column, KIND_GID, STATUS_REJECTED,
            f"{ratio:.2%} of values are valid GIDs, below {MIN_VALID_RATIO:.0%}",
            ratio, invalid_examples=_examples(invalid),
        )
    accepted = [value for value in values if _is_valid_gid(value) is not None]
    levels_t = tuple(sorted(levels))
    if domain_code is None:
        return ColumnDetection(
            column, KIND_GID, STATUS_NEEDS_DOMAIN,
            "valid GIDs, but a bare GID needs a domain from the file, the user, or a URI",
            ratio, levels=levels_t, invalid_examples=_examples(invalid),
        )
    if all(value.isdigit() for value in accepted):
        return ColumnDetection(
            column, KIND_GID, STATUS_NEEDS_CONFIRMATION,
            "all values are digits, so they could also be ordinary codes; confirm with the user",
            ratio, domain_codes=(domain_code,), levels=levels_t, invalid_examples=_examples(invalid),
        )
    return ColumnDetection(
        column, KIND_GID, STATUS_CERTAIN, "valid bare GIDs in the given domain",
        ratio, domain_codes=(domain_code,), levels=levels_t, invalid_examples=_examples(invalid),
    )


def _packed_level(value: Any) -> tuple[int, int] | None:
    """Return ``(domain_id, level)`` when ``value`` is an exact packed V2 identity."""
    if type(value) is not int:
        return None
    try:
        domain_id, level, x_idx, y_idx = unpack_int64(value)
        if pack_int64(domain_id, level, x_idx, y_idx) != value:
            return None
    except GeosquareError:
        return None
    return domain_id, level


def _detect_packed(column: str, values: list[Any]) -> ColumnDetection:
    domain_ids: set[int] = set()
    levels: set[int] = set()
    invalid: list[str] = []
    for value in values:
        identity = _packed_level(value)
        if identity is None:
            invalid.append(str(value))
        else:
            domain_ids.add(identity[0])
            levels.add(identity[1])
    ratio = (len(values) - len(invalid)) / len(values)
    if ratio < MIN_VALID_RATIO:
        return ColumnDetection(
            column, KIND_PACKED, STATUS_REJECTED,
            f"{ratio:.2%} of values are valid packed IDs, below {MIN_VALID_RATIO:.0%}",
            ratio, invalid_examples=_examples(invalid),
        )
    return ColumnDetection(
        column, KIND_PACKED, STATUS_CERTAIN, "exact packed V2 identities; domain is in the value",
        ratio, domain_ids=tuple(sorted(domain_ids)), levels=tuple(sorted(levels)),
        invalid_examples=_examples(invalid),
    )


def _digit_gid_in_int_column(values: list[Any]) -> bool:
    """True when an int column holds values that would be valid GIDs if read as text."""
    return all(type(value) is int and _is_valid_gid(str(value)) is not None for value in values)


def detect_column(
    column: str,
    dtype: str,
    values: Sequence[Any],
    *,
    domain_code: str | None = None,
) -> ColumnDetection:
    """Classify one column. ``dtype`` is ``"string"``, ``"int64"``, or any other label."""
    present = _non_null(values)
    if not present:
        return ColumnDetection(column, KIND_NONE, STATUS_REJECTED, "no non-null values", 0.0)

    if dtype == DTYPE_INT64:
        if _digit_gid_in_int_column(present):
            return ColumnDetection(
                column, KIND_GID, STATUS_REJECTED,
                "values look like GIDs but the column is int64; read the column as text first",
                0.0,
            )
        return _detect_packed(column, present)

    if dtype != DTYPE_STRING:
        return ColumnDetection(column, KIND_NONE, STATUS_REJECTED, f"dtype {dtype} cannot hold a spatial key", 0.0)

    if any(type(value) is str and value.startswith(_URI_PREFIX) for value in present):
        return _detect_uri(column, present, domain_code)
    return _detect_gid(column, present, domain_code)


def detect_table(
    columns: Mapping[str, tuple[str, Sequence[Any]]],
    *,
    domain_code: str | None = None,
    level: int | None = None,
) -> tuple[ColumnDetection, ...]:
    """Classify every column in a table and check x_idx/y_idx pairs.

    ``columns`` maps a column name to ``(dtype, values)``. When both ``x_idx`` and
    ``y_idx`` exist as int64 columns, they are reported once as ``xy_indices`` and
    are not also tested as packed IDs. ``level`` is required to judge indices.
    """
    lowered = {name.lower(): name for name in columns}
    xy_pair = None
    if "x_idx" in lowered and "y_idx" in lowered:
        x_name, y_name = lowered["x_idx"], lowered["y_idx"]
        if columns[x_name][0] == DTYPE_INT64 and columns[y_name][0] == DTYPE_INT64:
            xy_pair = (x_name, y_name)

    results: list[ColumnDetection] = []
    for name, (dtype, values) in columns.items():
        if xy_pair and name in xy_pair:
            continue
        results.append(detect_column(name, dtype, values, domain_code=domain_code))
    if xy_pair:
        results.append(_detect_xy(xy_pair, columns, domain_code=domain_code, level=level))
    return tuple(results)


def _detect_xy(
    pair: tuple[str, str],
    columns: Mapping[str, tuple[str, Sequence[Any]]],
    *,
    domain_code: str | None,
    level: int | None,
) -> ColumnDetection:
    label = f"{pair[0]}+{pair[1]}"
    if level is None:
        return ColumnDetection(label, KIND_XY, STATUS_NEEDS_LEVEL, "x/y indices need a level", 0.0)
    x_values, y_values = columns[pair[0]][1], columns[pair[1]][1]
    if len(x_values) != len(y_values):
        return ColumnDetection(label, KIND_XY, STATUS_REJECTED, "x and y columns differ in length", 0.0)
    size = side_cell_count(level)
    invalid: list[str] = []
    for x_value, y_value in zip(x_values, y_values):
        ok = (
            type(x_value) is int and type(y_value) is int
            and 0 <= x_value < size and 0 <= y_value < size
        )
        if not ok:
            invalid.append(f"({x_value}, {y_value})")
    ratio = (len(x_values) - len(invalid)) / len(x_values)
    if ratio < MIN_VALID_RATIO:
        return ColumnDetection(
            label, KIND_XY, STATUS_REJECTED,
            f"{ratio:.2%} of pairs are inside 0..{size - 1} at level {level}, below {MIN_VALID_RATIO:.0%}",
            ratio, levels=(level,), invalid_examples=_examples(invalid),
        )
    if domain_code is None:
        return ColumnDetection(
            label, KIND_XY, STATUS_NEEDS_DOMAIN, "indices need a domain from the file or the user",
            ratio, levels=(level,), invalid_examples=_examples(invalid),
        )
    return ColumnDetection(
        label, KIND_XY, STATUS_CERTAIN, "integer indices inside the grid at the given level",
        ratio, domain_codes=(domain_code,), levels=(level,), invalid_examples=_examples(invalid),
    )
