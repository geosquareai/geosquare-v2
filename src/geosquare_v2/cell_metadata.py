"""Cross-field checks for manifest 1.1 metadata (spec S8).

The JSON Schema in ``schemas/cell-dataset-manifest-v1.1.schema.json`` checks the shape
of each field. The checks here cover rules a schema cannot express. They need only the
manifest, not the Parquet files. See ``docs/dataset-metadata.md``, section 5.
"""

from __future__ import annotations

from collections.abc import Mapping
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
