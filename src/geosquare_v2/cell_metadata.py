"""Cross-field checks for manifest 1.1 metadata (spec S8).

The JSON Schema in ``schemas/cell-dataset-manifest-v1.1.schema.json`` checks the shape
of each field. The checks here cover rules a schema cannot express. They need only the
manifest, not the Parquet files. See ``docs/dataset-metadata.md``, section 5.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import hashlib
import json
import math
from typing import Any

from .errors import CellDatasetManifestError

_AREA_WEIGHT = "area"
_WEIGHT_SEMANTICS = frozenset(("COUNT", "TOTAL"))


def _error(path: str, message: str) -> CellDatasetManifestError:
    return CellDatasetManifestError(f"{path}: {message}")


def check_space_weights(manifest: Mapping[str, Any]) -> None:
    """Check each ``space_weight``.

    A weight must be null, the word ``area``, or the name of another COUNT or TOTAL
    value field in the same dataset.
    """
    fields = manifest.get("value_fields")
    if not isinstance(fields, list):
        raise _error("value_fields", "must be a list")

    by_name: dict[str, Mapping[str, Any]] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, Mapping) or not isinstance(field.get("name"), str):
            raise _error(f"value_fields[{index}]", "must be an object with a string name")
        by_name[field["name"]] = field

    for index, field in enumerate(fields):
        path = f"value_fields[{index}].space_weight"
        weight = field.get("space_weight")
        if weight is None:
            continue
        if not isinstance(weight, str) or not weight:
            raise _error(path, "must be null or a non-empty string")
        if weight == _AREA_WEIGHT:
            if _AREA_WEIGHT in by_name:
                raise _error(path, "'area' is ambiguous because a value field has that name")
            continue
        target = by_name.get(weight)
        if target is None:
            raise _error(path, f"{weight!r} is not a value field in this dataset")
        if target["name"] == field["name"]:
            raise _error(path, "a value field cannot weight itself")
        if target.get("semantics") not in _WEIGHT_SEMANTICS:
            raise _error(path, f"{weight!r} must have semantics COUNT or TOTAL")


def check_row_counts(manifest: Mapping[str, Any]) -> None:
    """Check that ``storage.row_count`` equals the sum of the data file row counts."""
    storage = manifest.get("storage")
    if not isinstance(storage, Mapping):
        raise _error("storage", "must be an object")
    files = storage.get("data_files")
    if not isinstance(files, list) or not files:
        raise _error("storage.data_files", "must be a non-empty list")

    total = 0
    for index, entry in enumerate(files):
        count = entry.get("row_count") if isinstance(entry, Mapping) else None
        if not isinstance(count, int) or isinstance(count, bool):
            raise _error(f"storage.data_files[{index}].row_count", "must be an integer")
        total += count

    if storage.get("row_count") != total:
        raise _error(
            "storage.row_count",
            f"is {storage.get('row_count')!r} but the data files hold {total} rows",
        )


def check_dataset_metadata(manifest: Mapping[str, Any]) -> None:
    """Run every manifest 1.1 cross-field check that needs only the manifest."""
    check_space_weights(manifest)
    check_row_counts(manifest)


_FLOAT_TYPES = frozenset(("double", "float"))
_INTEGER_TYPES = frozenset(("int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"))


def _canonical_value(value: Any, parquet_type: str, field_name: str) -> Any:
    """Encode one value by its declared type (docs/dataset-metadata.md, section 3.1)."""
    if value is None:
        return None
    if parquet_type in _FLOAT_TYPES:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field_name}: {value!r} is not a number for {parquet_type}")
        number = float(value)  # an integer stored in a double column is written as 3.0
        if not math.isfinite(number):
            raise ValueError(f"{field_name}: NaN and infinity cannot be hashed")
        return number
    if parquet_type in _INTEGER_TYPES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{field_name}: {value!r} is not an integer for {parquet_type}")
        return value
    if parquet_type == "string":
        if not isinstance(value, str):
            raise ValueError(f"{field_name}: {value!r} is not a string")
        return value
    raise ValueError(f"{field_name}: parquet_type {parquet_type!r} is not supported by content_sha256")


def content_sha256(table: Any, value_fields: Sequence[Mapping[str, Any]]) -> str:
    """Hash the rows of a table in canonical form (docs/dataset-metadata.md, section 3.1).

    ``table`` needs ``num_rows`` and ``column(name).to_pylist()``, as a PyArrow table has.
    ``value_fields`` are the manifest entries, in order: each has ``name`` and ``parquet_type``.
    Each row becomes a JSON array: gid first, then the value fields, each encoded by its declared
    type. The encoded rows are sorted by bytes. Each row is followed by a line feed.
    """
    names = ["gid", *(field["name"] for field in value_fields)]
    types = ["string", *(field["parquet_type"] for field in value_fields)]
    columns = [table.column(name).to_pylist() for name in names]
    encoded = []
    for row in zip(*columns):
        canonical = [_canonical_value(value, kind, name) for value, kind, name in zip(row, types, names)]
        encoded.append(
            json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        )
    digest = hashlib.sha256()
    for line in sorted(encoded):
        digest.update(line)
        digest.update(b"\n")
    return digest.hexdigest()


def data_file_entry(table: Any, value_fields: Sequence[Mapping[str, Any]], *, path: str) -> dict[str, Any]:
    """Build one ``storage.data_files`` entry for ``table``. Call it before the manifest is built."""
    return {
        "path": path,
        "content_sha256": content_sha256(table, value_fields),
        "row_count": int(table.num_rows),
    }
