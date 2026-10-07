"""Local Parquet cell-dataset storage and validation for GeoSquare V2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import math
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .cell_manifest import CellDatasetManifest
from .codec import gid_to_canonical, side_cell_count
from .errors import (
    CellDatasetError,
    CellDatasetManifestError,
    GeometryDependencyError,
    TableDependencyError,
    ValidationError,
)
from .packing import InvalidPackedIDError, unpack_int64
from .registry import DomainRegistry
from .release import ReleaseProfile

_MANIFEST_METADATA_KEY = b"geosquare.manifest"
_DATA_DIRECTORY = "data"
_MANIFEST_FILENAME = "manifest.json"
_PARQUET_FILENAME = "part-00000.parquet"
_IDENTITY_COLUMNS = frozenset(("gid", "uri", "packed_id", "x_idx", "y_idx", "domain", "level"))
_CONTRIBUTION_COLUMNS = frozenset(("source_id", "source_row", "coverage_ratio", "length_ratio", "assignment_method", "boundary_policy"))


def _require_pyarrow() -> tuple[Any, Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised without table extra
        raise TableDependencyError(
            "cell dataset operations require the 'table' optional dependency group"
        ) from exc
    return pa, pq, pa.types


def _dataset_error(path: str, message: str) -> CellDatasetError:
    return CellDatasetError(f"{path}: {message}")


def _column(table: Any, name: str) -> Any:
    try:
        return table.column(name)
    except (KeyError, IndexError) as exc:
        raise _dataset_error(name, "column is missing") from exc


def _field(table: Any, name: str) -> Any:
    index = table.schema.get_field_index(name)
    if index < 0:
        raise _dataset_error(name, "column is missing")
    return table.schema.field(index)


def _is_string_type(types: Any, data_type: Any) -> bool:
    return types.is_string(data_type) or types.is_large_string(data_type)


def _is_integer_type(types: Any, data_type: Any) -> bool:
    return types.is_integer(data_type) and not types.is_boolean(data_type)


def _normalise_type_name(value: str) -> str:
    normalized = "".join(value.split()).lower()
    aliases = {
        "float64": "double",
        "float": "double",
        "float32": "float",
        "str": "string",
        "large_string": "string",
        "large_binary": "binary",
    }
    return aliases.get(normalized, normalized)


def _type_matches(types: Any, actual: Any, declared: str) -> bool:
    actual_name = _normalise_type_name(str(actual))
    declared_name = _normalise_type_name(declared)
    if actual_name == declared_name:
        return True
    if declared_name == "string" and _is_string_type(types, actual):
        return True
    if declared_name == "binary" and (types.is_binary(actual) or types.is_large_binary(actual)):
        return True
    return False


def _ensure_no_nulls(values: Any, path: str) -> None:
    if values.null_count:
        raise _dataset_error(path, f"contains {values.null_count} null value(s)")


def _ensure_column_type(table: Any, name: str, predicate: Any, expected: str) -> None:
    actual = _field(table, name).type
    if not predicate(actual):
        raise _dataset_error(name, f"must use {expected}; found {actual}")


def _as_arrow_table(table: Any) -> Any:
    pa, _, _ = _require_pyarrow()
    if isinstance(table, pa.Table):
        return table
    if hasattr(table, "to_arrow"):
        converted = table.to_arrow()
        if isinstance(converted, pa.Table):
            return converted
    try:
        return pa.Table.from_pandas(table, preserve_index=False)
    except (TypeError, ValueError, ImportError) as exc:
        raise _dataset_error("table", "must be a PyArrow table or a convertible tabular object") from exc


def _read_embedded_manifest(path: Path, pq: Any, *, registry: DomainRegistry | None) -> CellDatasetManifest:
    try:
        metadata = pq.read_metadata(path).metadata or {}
    except Exception as exc:
        raise _dataset_error(str(path), f"could not read Parquet metadata: {exc}") from exc
    payload = metadata.get(_MANIFEST_METADATA_KEY)
    if payload is None:
        raise _dataset_error(str(path), "missing geosquare.manifest Parquet metadata")
    try:
        return CellDatasetManifest.from_json(payload, registry=registry)
    except CellDatasetManifestError as exc:
        raise _dataset_error(str(path), f"embedded manifest is invalid: {exc}") from exc


class CellDataset:
    """A validated local GeoSquare cell dataset backed by a PyArrow table.

    The on-disk representation is a directory containing ``manifest.json`` and one or
    more Parquet files below ``data/``. Phase 2 reads local files eagerly into a table;
    remote filesystems and lazy query execution are deliberately deferred.
    """

    __slots__ = ("_table", "_manifest", "_registry")

    def __init__(
        self,
        table: Any,
        manifest: CellDatasetManifest,
        *,
        registry: DomainRegistry | None = None,
    ) -> None:
        if not isinstance(manifest, CellDatasetManifest):
            raise ValidationError("manifest must be a CellDatasetManifest")
        if registry is not None and not isinstance(registry, DomainRegistry):
            raise ValidationError("registry must be a DomainRegistry")
        self._table = _as_arrow_table(table)
        self._manifest = manifest
        self._registry = registry
        self.validate()

    @classmethod
    def from_table(
        cls,
        table: Any,
        manifest: CellDatasetManifest | Mapping[str, Any],
        *,
        registry: DomainRegistry | None = None,
    ) -> "CellDataset":
        """Create and validate a dataset from an Arrow or convertible table."""
        parsed = (
            manifest
            if isinstance(manifest, CellDatasetManifest)
            else CellDatasetManifest.from_dict(manifest, registry=registry)
        )
        return cls(table, parsed, registry=registry)

    @classmethod
    def read(
        cls,
        path: str | Path,
        *,
        registry: DomainRegistry | None = None,
    ) -> "CellDataset":
        """Read and validate a local dataset directory."""
        _, pq, _ = _require_pyarrow()
        root = Path(path)
        if not root.is_dir():
            raise _dataset_error(str(root), "dataset directory does not exist")
        sidecar_path = root / _MANIFEST_FILENAME
        data_path = root / _DATA_DIRECTORY
        if not sidecar_path.is_file():
            raise _dataset_error(str(sidecar_path), "manifest sidecar does not exist")
        if not data_path.is_dir():
            raise _dataset_error(str(data_path), "data directory does not exist")
        try:
            manifest = CellDatasetManifest.from_file(sidecar_path, registry=registry)
        except CellDatasetManifestError as exc:
            raise _dataset_error(str(sidecar_path), f"sidecar manifest is invalid: {exc}") from exc

        parquet_files = sorted(data_path.glob("*.parquet"))
        if not parquet_files:
            raise _dataset_error(str(data_path), "contains no Parquet files")
        expected_json = manifest.to_json()
        for parquet_file in parquet_files:
            embedded = _read_embedded_manifest(parquet_file, pq, registry=registry)
            if embedded.to_json() != expected_json:
                raise _dataset_error(
                    str(parquet_file),
                    "embedded manifest does not match the manifest.json sidecar",
                )
        try:
            tables = [pq.read_table(parquet_file) for parquet_file in parquet_files]
            table = tables[0] if len(tables) == 1 else __import__("pyarrow").concat_tables(tables)
        except Exception as exc:
            raise _dataset_error(str(data_path), f"could not read Parquet data: {exc}") from exc
        return cls(table, manifest, registry=registry)

    @property
    def table(self) -> Any:
        """Return the backing PyArrow table."""
        return self._table

    @property
    def manifest(self) -> CellDatasetManifest:
        """Return the validated dataset manifest."""
        return self._manifest

    @property
    def registry(self) -> DomainRegistry | None:
        """Return the optional trusted registry used during validation."""
        return self._registry

    @property
    def num_rows(self) -> int:
        return self._table.num_rows

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(self._table.column_names)

    def to_pandas(self) -> Any:
        """Convert the validated table to a Pandas DataFrame."""
        return self._table.to_pandas()

    def validate(self) -> "CellDataset":
        """Validate manifest, Arrow schema, row values, counts, and identity columns."""
        self._manifest.validate(registry=self._registry, columns=self._table.column_names)
        self._validate_schema()
        self._validate_rows()
        return self

    def write(self, path: str | Path) -> Path:
        """Write an atomic local dataset directory and return its path.

        The destination must not already exist. This avoids silently replacing an
        unrelated directory and keeps the operation safely repeatable.
        """
        _, pq, _ = _require_pyarrow()
        destination = Path(path)
        if destination.exists():
            raise _dataset_error(str(destination), "destination already exists")
        parent = destination.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.tmp-", dir=parent))
        try:
            data_path = temporary / _DATA_DIRECTORY
            data_path.mkdir()
            metadata = dict(self._table.schema.metadata or {})
            metadata[_MANIFEST_METADATA_KEY] = self._manifest.to_json().encode("utf-8")
            table = self._table.replace_schema_metadata(metadata)
            compression = self._manifest.storage["parquet_compression"]
            parquet_path = data_path / _PARQUET_FILENAME
            pq.write_table(table, parquet_path, compression=compression)
            self._manifest.write(temporary / _MANIFEST_FILENAME)
            os.replace(temporary, destination)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return destination

    def _validate_schema(self) -> None:
        _, _, types = _require_pyarrow()
        columns = set(self._table.column_names)
        identity = self._manifest.identity
        storage = self._manifest.storage
        allowed = set(self._manifest.value_field_names) | _IDENTITY_COLUMNS
        if self._manifest.dataset_type == "cell_contributions":
            allowed |= _CONTRIBUTION_COLUMNS
        geometry_column = storage["geometry_column"]
        if geometry_column is not None:
            allowed.add(geometry_column)
        unexpected = sorted(columns - allowed)
        if unexpected:
            raise _dataset_error("columns", f"undeclared column(s): {', '.join(unexpected)}")

        _ensure_column_type(self._table, "gid", lambda value: _is_string_type(types, value), "UTF-8 string")
        if "uri" in columns:
            _ensure_column_type(self._table, "uri", lambda value: _is_string_type(types, value), "UTF-8 string")
        if "domain" in columns:
            _ensure_column_type(self._table, "domain", lambda value: _is_string_type(types, value), "UTF-8 string")
        if "level" in columns:
            _ensure_column_type(self._table, "level", lambda value: _is_integer_type(types, value), "integer")
        for column in ("packed_id", "x_idx", "y_idx", "source_row"):
            if column in columns:
                _ensure_column_type(self._table, column, lambda value: _is_integer_type(types, value), "integer")
        for column in ("source_id", "assignment_method", "boundary_policy"):
            if column in columns:
                _ensure_column_type(self._table, column, lambda value: _is_string_type(types, value), "UTF-8 string")
        for column in ("coverage_ratio", "length_ratio"):
            if column in columns:
                _ensure_column_type(self._table, column, types.is_floating, "floating point")
        if geometry_column is not None:
            actual_geometry = _field(self._table, geometry_column).type
            geometry_format = storage["geometry_format"]
            if geometry_format == "wkb" and not (types.is_binary(actual_geometry) or types.is_large_binary(actual_geometry)):
                raise _dataset_error(geometry_column, "WKB geometry must use a binary Parquet type")
            if geometry_format == "wkt" and not _is_string_type(types, actual_geometry):
                raise _dataset_error(geometry_column, "WKT geometry must use a UTF-8 string Parquet type")

        for value_field in self._manifest.value_fields:
            name = value_field["name"]
            actual = _field(self._table, name).type
            if not _type_matches(types, actual, value_field["parquet_type"]):
                raise _dataset_error(
                    name,
                    f"Parquet type {actual} does not match declared type {value_field['parquet_type']!r}",
                )
            if not value_field["nullable"]:
                _ensure_no_nulls(_column(self._table, name), name)

        declared_query_columns = {
            identity[field_name]
            for field_name in ("packed_id_column", "x_idx_column", "y_idx_column")
            if identity[field_name] is not None
        }
        for column in declared_query_columns:
            if column not in columns:
                raise _dataset_error(column, "declared query column is missing")
        if self._manifest.dataset_type == "cell_contributions":
            if not ({"source_id", "source_row"} & columns):
                raise _dataset_error("dataset_type", "cell_contributions requires source_id or source_row")
            if "source_id" in columns and "source_row" in columns:
                raise _dataset_error("columns", "cell_contributions must not use both source_id and source_row")
        elif columns & _CONTRIBUTION_COLUMNS:
            raise _dataset_error("columns", "contribution columns require dataset_type cell_contributions")

    def _validate_rows(self) -> None:
        columns = set(self._table.column_names)
        gid_values = _column(self._table, "gid")
        _ensure_no_nulls(gid_values, "gid")
        gids = gid_values.to_pylist()
        canonical_cells = []
        for row_number, gid in enumerate(gids):
            try:
                cell = gid_to_canonical(self._manifest.domain_code, gid)
            except Exception as exc:
                raise _dataset_error(f"gid[{row_number}]", f"is invalid: {exc}") from exc
            if cell.level != self._manifest.level:
                raise _dataset_error(
                    f"gid[{row_number}]",
                    f"has level {cell.level}; expected manifest level {self._manifest.level}",
                )
            canonical_cells.append(cell)

        if self._manifest.identity["unique_gid"] and len(set(gids)) != len(gids):
            raise _dataset_error("gid", "contains duplicate values but manifest requires unique GIDs")
        unique_cell_count = self._manifest.storage["unique_cell_count"]
        if unique_cell_count is not None and unique_cell_count != len(set(gids)):
            raise _dataset_error(
                "storage.unique_cell_count",
                f"declares {unique_cell_count}, but data contains {len(set(gids))} unique GIDs",
            )
        if self._manifest.storage["row_count"] != self._table.num_rows:
            raise _dataset_error(
                "storage.row_count",
                f"declares {self._manifest.storage['row_count']}, but data contains {self._table.num_rows} rows",
            )

        if "domain" in columns:
            domain_values = _column(self._table, "domain")
            _ensure_no_nulls(domain_values, "domain")
            if any(value != self._manifest.domain_code for value in domain_values.to_pylist()):
                raise _dataset_error("domain", "contains a value different from manifest.domain_code")
        if "level" in columns:
            level_values = _column(self._table, "level")
            _ensure_no_nulls(level_values, "level")
            if any(value != self._manifest.level for value in level_values.to_pylist()):
                raise _dataset_error("level", "contains a value different from manifest.level")
        if "uri" in columns:
            uri_values = _column(self._table, "uri")
            _ensure_no_nulls(uri_values, "uri")
            expected_prefix = self._manifest.identity["uri_prefix"]
            for row_number, (gid, uri) in enumerate(zip(gids, uri_values.to_pylist())):
                if uri != f"{expected_prefix}{gid}":
                    raise _dataset_error(f"uri[{row_number}]", "does not match the GID and manifest URI prefix")

        identity = self._manifest.identity
        query_columns = ("packed_id_column", "x_idx_column", "y_idx_column")
        query_values = {
            field_name: _column(self._table, identity[field_name]).to_pylist()
            for field_name in query_columns
            if identity[field_name] is not None
        }
        for field_name, values in query_values.items():
            _ensure_no_nulls(_column(self._table, identity[field_name]), f"identity.{field_name}")
        for row_number, cell in enumerate(canonical_cells):
            if "packed_id_column" in query_values:
                try:
                    packed = unpack_int64(query_values["packed_id_column"][row_number])
                except (InvalidPackedIDError, TypeError, ValueError) as exc:
                    raise _dataset_error(f"packed_id[{row_number}]", f"is invalid: {exc}") from exc
                expected = (self._manifest.domain_id, cell.level, cell.x_idx, cell.y_idx)
                if packed != expected:
                    raise _dataset_error(f"packed_id[{row_number}]", f"does not match {expected}")
            if "x_idx_column" in query_values and query_values["x_idx_column"][row_number] != cell.x_idx:
                raise _dataset_error(f"x_idx[{row_number}]", "does not match the GID")
            if "y_idx_column" in query_values and query_values["y_idx_column"][row_number] != cell.y_idx:
                raise _dataset_error(f"y_idx[{row_number}]", "does not match the GID")

        if self._manifest.dataset_type == "cell_contributions":
            source_column = "source_id" if "source_id" in columns else "source_row"
            source_values = _column(self._table, source_column)
            _ensure_no_nulls(source_values, source_column)
            has_coverage = "coverage_ratio" in columns
            has_length = "length_ratio" in columns
            for row_number, (coverage, length) in enumerate(
                zip(
                    _column(self._table, "coverage_ratio").to_pylist() if has_coverage else [None] * self._table.num_rows,
                    _column(self._table, "length_ratio").to_pylist() if has_length else [None] * self._table.num_rows,
                )
            ):
                if coverage is not None and length is not None:
                    raise _dataset_error(f"row[{row_number}]", "must not declare both coverage_ratio and length_ratio")
            for ratio_name in ("coverage_ratio", "length_ratio"):
                if ratio_name in columns:
                    values = _column(self._table, ratio_name)
                    for row_number, ratio in enumerate(values.to_pylist()):
                        if ratio is not None and (not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1):
                            raise _dataset_error(f"{ratio_name}[{row_number}]", "must be in [0, 1]")


def write_cell_dataset(
    dataset: CellDataset | Any,
    path: str | Path,
    *,
    manifest: CellDatasetManifest | Mapping[str, Any] | None = None,
    registry: DomainRegistry | None = None,
) -> Path:
    """Write a ``CellDataset`` or construct one from a table and write it locally."""
    if isinstance(dataset, CellDataset):
        if manifest is not None or registry is not None and dataset.registry is not registry:
            raise ValidationError("manifest/registry arguments cannot override a CellDataset")
        return dataset.write(path)
    if manifest is None:
        raise ValidationError("manifest is required when writing a raw table")
    return CellDataset.from_table(dataset, manifest, registry=registry).write(path)


def read_cell_dataset(path: str | Path, *, registry: DomainRegistry | None = None) -> CellDataset:
    """Read and validate a local ``CellDataset`` directory."""
    return CellDataset.read(path, registry=registry)


def _validate_query_bbox(bbox: Iterable[float]) -> tuple[tuple[float, float, float, float], ...]:
    try:
        values = list(bbox)
    except TypeError as exc:
        raise _dataset_error("bbox", "must be an iterable of four numbers") from exc
    if len(values) != 4:
        raise _dataset_error("bbox", "must contain (min_lon, min_lat, max_lon, max_lat)")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        raise _dataset_error("bbox", "coordinates must be finite numbers")
    min_lon, min_lat, max_lon, max_lat = (float(value) for value in values)
    if not -180.0 <= min_lon <= 180.0 or not -180.0 <= max_lon <= 180.0:
        raise _dataset_error("bbox", "longitude must be in [-180, 180]")
    if not -90.0 <= min_lat <= 90.0 or not -90.0 <= max_lat <= 90.0:
        raise _dataset_error("bbox", "latitude must be in [-90, 90]")
    if min_lat >= max_lat:
        raise _dataset_error("bbox", "latitude bounds must be strictly increasing")
    if min_lon == max_lon:
        raise _dataset_error("bbox", "longitude bounds must not be equal")
    if min_lon < max_lon:
        return ((min_lon, min_lat, max_lon, max_lat),)
    # A decreasing longitude interval explicitly denotes an antimeridian crossing.
    return (
        (min_lon, min_lat, 180.0, max_lat),
        (-180.0, min_lat, max_lon, max_lat),
    )


def _projected_query_window(
    projected_bbox: tuple[float, float, float, float],
    profile: ReleaseProfile,
    level: int,
) -> tuple[int, int, int, int] | None:
    min_x, min_y, max_x, max_y = projected_bbox
    if any(not math.isfinite(value) for value in projected_bbox):
        raise _dataset_error("bbox", "transformation produced non-finite coordinates")
    root = profile.root_bounds
    if max_x <= root.min_x or min_x >= root.max_x or max_y <= root.min_y or min_y >= root.max_y:
        return None
    clipped_min_x = max(min_x, root.min_x)
    clipped_min_y = max(min_y, root.min_y)
    clipped_max_x = min(max_x, root.max_x)
    clipped_max_y = min(max_y, root.max_y)
    side = profile.root_side_m / side_cell_count(level)
    count = side_cell_count(level)
    x_start = max(0, math.floor((clipped_min_x - root.min_x) / side))
    y_start = max(0, math.floor((clipped_min_y - root.min_y) / side))
    x_stop = min(count - 1, math.ceil((clipped_max_x - root.min_x) / side) - 1)
    y_stop = min(count - 1, math.ceil((clipped_max_y - root.min_y) / side) - 1)
    if x_start > x_stop or y_start > y_stop:
        return None
    return x_start, x_stop, y_start, y_stop


def query_cell_dataset(
    path: str | Path,
    *,
    bbox: Iterable[float],
    domain: str | None = None,
    level: int | None = None,
    registry: DomainRegistry | None = None,
) -> Any:
    """Query a local queryable dataset by a WGS84 bounding box.

    The manifest and every Parquet fragment's embedded manifest are validated before
    scanning. The result is a PyArrow table filtered using x/y predicate expressions;
    its schema retains the canonical ``geosquare.manifest`` metadata. Compact GID-only
    datasets are rejected because they do not provide a rectangular query index.
    """
    pa, pq, types = _require_pyarrow()
    try:
        import pyarrow.dataset as pds
    except ImportError as exc:  # pragma: no cover - bundled with pyarrow table extra
        raise TableDependencyError("dataset queries require the 'table' optional dependency group") from exc
    if not isinstance(registry, DomainRegistry):
        raise _dataset_error("registry", "a trusted DomainRegistry is required for bbox queries")

    root = Path(path)
    if not root.is_dir():
        raise _dataset_error(str(root), "dataset directory does not exist")
    sidecar_path = root / _MANIFEST_FILENAME
    data_path = root / _DATA_DIRECTORY
    if not sidecar_path.is_file():
        raise _dataset_error(str(sidecar_path), "manifest sidecar does not exist")
    if not data_path.is_dir():
        raise _dataset_error(str(data_path), "data directory does not exist")
    try:
        manifest = CellDatasetManifest.from_file(sidecar_path, registry=registry)
    except CellDatasetManifestError as exc:
        raise _dataset_error(str(sidecar_path), f"sidecar manifest is invalid: {exc}") from exc
    if not manifest.is_queryable:
        raise _dataset_error("identity", "dataset is compact and has no complete x/y query index")
    if domain is not None and domain != manifest.domain_code:
        raise _dataset_error("domain", f"requested {domain!r}, but dataset domain is {manifest.domain_code!r}")
    if level is not None:
        if type(level) is not int:
            raise _dataset_error("level", "must be an integer")
        if level != manifest.level:
            raise _dataset_error("level", f"requested {level}, but dataset level is {manifest.level}")

    parquet_files = sorted(data_path.glob("*.parquet"))
    if not parquet_files:
        raise _dataset_error(str(data_path), "contains no Parquet files")
    expected_json = manifest.to_json()
    for parquet_file in parquet_files:
        embedded = _read_embedded_manifest(parquet_file, pq, registry=registry)
        if embedded.to_json() != expected_json:
            raise _dataset_error(
                str(parquet_file),
                "embedded manifest does not match the manifest.json sidecar",
            )

    profile = registry.get(manifest.domain_code)
    if not isinstance(profile, ReleaseProfile):
        raise _dataset_error("registry", "bbox queries require a trusted ReleaseProfile with CRS metadata")
    try:
        from pyproj import CRS, Transformer

        transformer = Transformer.from_crs(
            CRS.from_epsg(4326),
            CRS.from_user_input(profile.crs_wkt2),
            always_xy=True,
        )
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise GeometryDependencyError(
            "bbox queries require the 'geo' optional dependency group"
        ) from exc
    except Exception as exc:
        raise _dataset_error("registry", f"could not construct the profile CRS transformer: {exc}") from exc

    windows: list[tuple[int, int, int, int]] = []
    for min_lon, min_lat, max_lon, max_lat in _validate_query_bbox(bbox):
        try:
            transformed = [
                transformer.transform(longitude, latitude)
                for longitude, latitude in (
                    (min_lon, min_lat),
                    (min_lon, max_lat),
                    (max_lon, min_lat),
                    (max_lon, max_lat),
                )
            ]
        except Exception as exc:
            raise _dataset_error("bbox", f"could not transform coordinates: {exc}") from exc
        projected_bbox = (
            min(point[0] for point in transformed),
            min(point[1] for point in transformed),
            max(point[0] for point in transformed),
            max(point[1] for point in transformed),
        )
        window = _projected_query_window(projected_bbox, profile, manifest.level)
        if window is not None and window not in windows:
            windows.append(window)

    query_dataset = pds.dataset(str(data_path), format="parquet")
    x_column = manifest.identity["x_idx_column"]
    y_column = manifest.identity["y_idx_column"]
    for column_name in (x_column, y_column):
        if query_dataset.schema.get_field_index(column_name) < 0:
            raise _dataset_error(column_name, "declared query column is missing from Parquet data")
        if not types.is_integer(query_dataset.schema.field(column_name).type):
            raise _dataset_error(column_name, "query column must use an integer Parquet type")

    if windows:
        x_field = pds.field(x_column)
        y_field = pds.field(y_column)
        expressions = [
            (x_field >= x_start) & (x_field <= x_stop) & (y_field >= y_start) & (y_field <= y_stop)
            for x_start, x_stop, y_start, y_stop in windows
        ]
        predicate = expressions[0]
        for expression in expressions[1:]:
            predicate = predicate | expression
        result = query_dataset.to_table(filter=predicate)
    else:
        result = pa.Table.from_batches([], schema=query_dataset.schema)

    metadata = dict(result.schema.metadata or {})
    metadata[_MANIFEST_METADATA_KEY] = manifest.to_json().encode("utf-8")
    return result.replace_schema_metadata(metadata)
