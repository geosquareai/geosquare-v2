"""Cell-dataset manifest parsing and validation for GeoSquare V2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from importlib import resources
from typing import Any

from .errors import CellDatasetManifestError, UnknownDomainError
from .model import DomainProfile
from .registry import DomainRegistry

_MANIFEST_VERSION = "1.0"
_GRID_SYSTEM = "geosquare"
_GRID_VERSION = "v2"
_MAX_LEVEL = 14
_DOMAIN_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,15}$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_DATASET_TYPES = frozenset(("cell_values", "cell_contributions"))
_ALLOWED_LOGICAL_TYPES = frozenset(("numeric", "categorical", "ordinal", "range"))
_ALLOWED_SEMANTICS = frozenset(
    ("COUNT", "TOTAL", "DENSITY", "MEASUREMENT", "RATE", "ORDINAL", "CATEGORICAL", "RANGE")
)
_NUMERIC_SEMANTICS = frozenset(("COUNT", "TOTAL", "DENSITY", "MEASUREMENT", "RATE"))
_ALLOWED_BOUNDARY_POLICIES = frozenset(("COVERS_POINT", "CENTROID_COVERED", "INTERSECTS", "MIN_COVERAGE"))
_ALLOWED_COVERAGE_MODES = frozenset(("GRID_PLANAR", "EQUAL_AREA"))
_ALLOWED_COMPRESSION = frozenset(("zstd", "snappy", "gzip", "brotli", "uncompressed"))
_ALLOWED_GEOMETRY_FORMATS = frozenset(("wkb", "wkt", "shapely"))
_RESERVED_COLUMNS = frozenset(
    (
        "domain",
        "level",
        "gid",
        "uri",
        "packed_id",
        "x_idx",
        "y_idx",
        "source_id",
        "source_row",
        "coverage_ratio",
        "length_ratio",
        "assignment_method",
        "boundary_policy",
        "geometry_wkb",
    )
)
_SCHEMA_RESOURCE = "data/cell-dataset-manifest-v1.schema.json"

_TOP_LEVEL_KEYS = frozenset(
    (
        "manifest_version",
        "dataset_type",
        "grid_system",
        "grid_version",
        "domain_code",
        "domain_id",
        "level",
        "profile_version",
        "registry_version",
        "value_fields",
        "identity",
        "coverage",
        "source",
        "storage",
        "provenance",
    )
)
_VALUE_FIELD_KEYS = frozenset(
    ("name", "parquet_type", "logical_type", "semantics", "unit", "nullable", "aggregation_rule")
)
_IDENTITY_KEYS = frozenset(("gid_column", "uri_prefix", "packed_id_column", "x_idx_column", "y_idx_column", "unique_gid"))
_COVERAGE_KEYS = frozenset(
    ("assignment_method", "boundary_policy", "boundary_sha256", "coverage_mode", "min_coverage", "length_mode")
)
_SOURCE_KEYS = frozenset(
    ("format", "geometry_type", "source_crs", "source_id_column", "source_dataset", "source_row_count")
)
_STORAGE_KEYS = frozenset(
    (
        "parquet_compression",
        "geometry_column",
        "geometry_format",
        "geometry_crs",
        "partitioning",
        "sorted_by",
        "row_count",
        "unique_cell_count",
    )
)
_PROVENANCE_KEYS = frozenset(("created_at", "created_by", "generator", "aggregation_rule", "value_semantics", "notes"))


def _error(path: str, message: str) -> CellDatasetManifestError:
    return CellDatasetManifestError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(path, "must be an object")
    return value


def _keys(value: Mapping[str, Any], allowed: frozenset[str], required: frozenset[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise _error(path, f"unknown field(s): {', '.join(unknown)}")
    if missing:
        raise _error(path, f"missing required field(s): {', '.join(missing)}")


def _string(value: Any, path: str, *, non_empty: bool = False, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        raise _error(path, "must be a string")
    if non_empty and not value:
        raise _error(path, "must not be empty")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise _error(path, "has an invalid format")
    return value


def _nullable_string(value: Any, path: str) -> None:
    if value is not None:
        _string(value, path)


def _integer(value: Any, path: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise _error(path, "must be an integer")
    if minimum is not None and value < minimum:
        raise _error(path, f"must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise _error(path, f"must be at most {maximum}")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise _error(path, "must be a finite number")
    numeric = float(value)
    if minimum is not None and numeric < minimum:
        raise _error(path, f"must be at least {minimum}")
    if maximum is not None and numeric > maximum:
        raise _error(path, f"must be at most {maximum}")
    return numeric


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise _error(path, "must be a boolean")
    return value


def _string_list(value: Any, path: str) -> None:
    if not isinstance(value, list):
        raise _error(path, "must be an array")
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        item_string = _string(item, item_path, non_empty=True)
        if item_string in seen:
            raise _error(item_path, "must not be duplicated")
        seen.add(item_string)


def _validate_value_fields(value: Any) -> None:
    path = "value_fields"
    if not isinstance(value, list) or not value:
        raise _error(path, "must be a non-empty array")

    names: set[str] = set()
    for index, raw_field in enumerate(value):
        field_path = f"{path}[{index}]"
        field = _mapping(raw_field, field_path)
        _keys(field, _VALUE_FIELD_KEYS, _VALUE_FIELD_KEYS, field_path)
        name = _string(field["name"], f"{field_path}.name", non_empty=True, pattern=_IDENTIFIER_PATTERN)
        if name in _RESERVED_COLUMNS:
            raise _error(f"{field_path}.name", f"uses reserved column name {name!r}")
        if name in names:
            raise _error(f"{field_path}.name", f"duplicates value field {name!r}")
        names.add(name)

        _string(field["parquet_type"], f"{field_path}.parquet_type", non_empty=True)
        logical_type = _string(field["logical_type"], f"{field_path}.logical_type")
        if logical_type not in _ALLOWED_LOGICAL_TYPES:
            raise _error(f"{field_path}.logical_type", f"must be one of {sorted(_ALLOWED_LOGICAL_TYPES)}")
        semantics = _string(field["semantics"], f"{field_path}.semantics")
        if semantics not in _ALLOWED_SEMANTICS:
            raise _error(f"{field_path}.semantics", f"must be one of {sorted(_ALLOWED_SEMANTICS)}")
        expected_semantics = {
            "numeric": _NUMERIC_SEMANTICS,
            "categorical": frozenset(("CATEGORICAL",)),
            "ordinal": frozenset(("ORDINAL",)),
            "range": frozenset(("RANGE",)),
        }[logical_type]
        if semantics not in expected_semantics:
            raise _error(
                f"{field_path}.semantics",
                f"{semantics!r} is incompatible with logical_type {logical_type!r}",
            )
        _nullable_string(field["unit"], f"{field_path}.unit")
        _boolean(field["nullable"], f"{field_path}.nullable")
        _nullable_string(field["aggregation_rule"], f"{field_path}.aggregation_rule")


def _validate_identity(value: Any, domain_code: str, dataset_type: str) -> None:
    path = "identity"
    identity = _mapping(value, path)
    _keys(identity, _IDENTITY_KEYS, _IDENTITY_KEYS, path)
    if identity["gid_column"] != "gid":
        raise _error("identity.gid_column", "must be 'gid'")
    uri_prefix = _string(identity["uri_prefix"], "identity.uri_prefix", non_empty=True)
    expected_prefix = f"geosquare:v2:{domain_code}:"
    if uri_prefix != expected_prefix:
        raise _error("identity.uri_prefix", f"must be {expected_prefix!r}")

    optional_columns = (
        identity["packed_id_column"],
        identity["x_idx_column"],
        identity["y_idx_column"],
    )
    for index, column in enumerate(optional_columns):
        _nullable_string(column, f"identity.{('packed_id_column', 'x_idx_column', 'y_idx_column')[index]}")
    declared_columns = [column for column in optional_columns if column is not None]
    if len(set(declared_columns)) != len(declared_columns):
        raise _error(path, "packed_id_column, x_idx_column, and y_idx_column must be distinct")
    if declared_columns and len(declared_columns) != 3:
        raise _error(path, "packed_id_column, x_idx_column, and y_idx_column must be declared together")

    unique_gid = _boolean(identity["unique_gid"], "identity.unique_gid")
    if dataset_type == "cell_values" and not unique_gid:
        raise _error("identity.unique_gid", "must be true for cell_values datasets")


def _validate_coverage(value: Any) -> None:
    path = "coverage"
    coverage = _mapping(value, path)
    _keys(coverage, _COVERAGE_KEYS, _COVERAGE_KEYS, path)
    _string(coverage["assignment_method"], "coverage.assignment_method", non_empty=True)

    boundary_policy = coverage["boundary_policy"]
    if boundary_policy is not None:
        _string(boundary_policy, "coverage.boundary_policy")
        if boundary_policy not in _ALLOWED_BOUNDARY_POLICIES:
            raise _error("coverage.boundary_policy", f"must be one of {sorted(_ALLOWED_BOUNDARY_POLICIES)}")
    boundary_sha256 = coverage["boundary_sha256"]
    if boundary_sha256 is not None and _SHA256_PATTERN.fullmatch(str(boundary_sha256)) is None:
        raise _error("coverage.boundary_sha256", "must be a lowercase SHA-256 digest or null")

    coverage_mode = coverage["coverage_mode"]
    if coverage_mode is not None:
        _string(coverage_mode, "coverage.coverage_mode")
        if coverage_mode not in _ALLOWED_COVERAGE_MODES:
            raise _error("coverage.coverage_mode", f"must be one of {sorted(_ALLOWED_COVERAGE_MODES)}")
    if coverage["min_coverage"] is not None:
        _number(coverage["min_coverage"], "coverage.min_coverage", minimum=0.0, maximum=1.0)
    _nullable_string(coverage["length_mode"], "coverage.length_mode")


def _validate_source(value: Any) -> None:
    path = "source"
    source = _mapping(value, path)
    _keys(source, _SOURCE_KEYS, _SOURCE_KEYS, path)
    _string(source["format"], "source.format", non_empty=True)
    for field_name in ("geometry_type", "source_crs", "source_id_column", "source_dataset"):
        _nullable_string(source[field_name], f"source.{field_name}")
    if source["source_row_count"] is not None:
        _integer(source["source_row_count"], "source.source_row_count", minimum=0)


def _validate_storage(value: Any, dataset_type: str) -> None:
    path = "storage"
    storage = _mapping(value, path)
    _keys(storage, _STORAGE_KEYS, _STORAGE_KEYS, path)

    compression = storage["parquet_compression"]
    if compression is not None:
        _string(compression, "storage.parquet_compression")
        if compression not in _ALLOWED_COMPRESSION:
            raise _error("storage.parquet_compression", f"must be one of {sorted(_ALLOWED_COMPRESSION)}")

    geometry_column = storage["geometry_column"]
    geometry_format = storage["geometry_format"]
    geometry_crs = storage["geometry_crs"]
    _nullable_string(geometry_column, "storage.geometry_column")
    if geometry_format is not None:
        _string(geometry_format, "storage.geometry_format")
        if geometry_format not in _ALLOWED_GEOMETRY_FORMATS:
            raise _error("storage.geometry_format", f"must be one of {sorted(_ALLOWED_GEOMETRY_FORMATS)}")
    _nullable_string(geometry_crs, "storage.geometry_crs")
    if geometry_column is None and (geometry_format is not None or geometry_crs is not None):
        raise _error("storage", "geometry_format and geometry_crs require geometry_column")
    if geometry_column is not None and (geometry_format is None or geometry_crs is None):
        raise _error("storage", "geometry_column requires geometry_format and geometry_crs")

    _string_list(storage["partitioning"], "storage.partitioning")
    _string_list(storage["sorted_by"], "storage.sorted_by")
    row_count = _integer(storage["row_count"], "storage.row_count", minimum=0)
    unique_cell_count = storage["unique_cell_count"]
    if unique_cell_count is not None:
        unique_cell_count = _integer(unique_cell_count, "storage.unique_cell_count", minimum=0)
        if unique_cell_count > row_count:
            raise _error("storage.unique_cell_count", "must not exceed storage.row_count")
        if dataset_type == "cell_values" and unique_cell_count != row_count:
            raise _error("storage.unique_cell_count", "must equal storage.row_count for cell_values datasets")


def _validate_provenance(value: Any) -> None:
    path = "provenance"
    provenance = _mapping(value, path)
    _keys(provenance, _PROVENANCE_KEYS, _PROVENANCE_KEYS, path)
    for field_name in ("created_at", "created_by", "generator"):
        _string(provenance[field_name], f"provenance.{field_name}", non_empty=True)
    _nullable_string(provenance["aggregation_rule"], "provenance.aggregation_rule")
    value_semantics = provenance["value_semantics"]
    if value_semantics is not None:
        _string(value_semantics, "provenance.value_semantics")
        if value_semantics not in _ALLOWED_SEMANTICS:
            raise _error("provenance.value_semantics", f"must be one of {sorted(_ALLOWED_SEMANTICS)}")
    _nullable_string(provenance["notes"], "provenance.notes")


def _validate_document(document: Mapping[str, Any]) -> None:
    _keys(document, _TOP_LEVEL_KEYS, _TOP_LEVEL_KEYS, "manifest")
    if document["manifest_version"] != _MANIFEST_VERSION:
        raise _error("manifest_version", f"must be {_MANIFEST_VERSION!r}")
    dataset_type = _string(document["dataset_type"], "dataset_type")
    if dataset_type not in _ALLOWED_DATASET_TYPES:
        raise _error("dataset_type", f"must be one of {sorted(_ALLOWED_DATASET_TYPES)}")
    if document["grid_system"] != _GRID_SYSTEM:
        raise _error("grid_system", f"must be {_GRID_SYSTEM!r}")
    if document["grid_version"] != _GRID_VERSION:
        raise _error("grid_version", f"must be {_GRID_VERSION!r}")

    domain_code = _string(document["domain_code"], "domain_code", non_empty=True, pattern=_DOMAIN_PATTERN)
    if not domain_code.isascii() or not domain_code.isupper():
        raise _error("domain_code", "must contain uppercase ASCII characters only")
    _integer(document["domain_id"], "domain_id", minimum=1, maximum=511)
    _integer(document["level"], "level", minimum=0, maximum=_MAX_LEVEL)
    _string(document["profile_version"], "profile_version", non_empty=True)
    _string(document["registry_version"], "registry_version", non_empty=True)

    _validate_value_fields(document["value_fields"])
    _validate_identity(document["identity"], domain_code, dataset_type)
    _validate_coverage(document["coverage"])
    _validate_source(document["source"])
    _validate_storage(document["storage"], dataset_type)
    _validate_provenance(document["provenance"])


@dataclass(frozen=True, slots=True, init=False)
class CellDatasetManifest:
    """Validated metadata describing one single-domain, single-level cell dataset.

    The object owns a defensive copy of the input document. Runtime validation of actual
    Parquet rows belongs to the dataset reader, while this class validates manifest shape,
    cross-field semantics, trusted profile identity, and declared columns.
    """

    _document: dict[str, Any]

    def __init__(self, document: Mapping[str, Any]) -> None:
        if not isinstance(document, Mapping):
            raise _error("manifest", "must be an object")
        copied = deepcopy(dict(document))
        _validate_document(copied)
        object.__setattr__(self, "_document", copied)

    @classmethod
    def from_dict(
        cls,
        document: Mapping[str, Any],
        *,
        registry: DomainRegistry | None = None,
        columns: Iterable[str] | None = None,
    ) -> "CellDatasetManifest":
        """Parse and validate a manifest mapping."""
        manifest = cls(document)
        manifest.validate(registry=registry, columns=columns)
        return manifest

    @classmethod
    def from_json(
        cls,
        payload: str | bytes | bytearray,
        *,
        registry: DomainRegistry | None = None,
        columns: Iterable[str] | None = None,
    ) -> "CellDatasetManifest":
        """Parse a JSON manifest and apply the same runtime validation as ``from_dict``."""
        try:
            document = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _error("manifest", f"invalid JSON: {exc}") from exc
        return cls.from_dict(document, registry=registry, columns=columns)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        registry: DomainRegistry | None = None,
        columns: Iterable[str] | None = None,
    ) -> "CellDatasetManifest":
        """Read and validate a UTF-8 JSON manifest file."""
        manifest_path = Path(path)
        try:
            payload = manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _error("manifest", f"could not read {manifest_path}: {exc}") from exc
        return cls.from_json(payload, registry=registry, columns=columns)

    @classmethod
    def schema(cls) -> dict[str, Any]:
        """Return the packaged JSON schema as a defensive dictionary copy."""
        try:
            schema_path = resources.files("geosquare_v2").joinpath(_SCHEMA_RESOURCE)
            payload = schema_path.read_text(encoding="utf-8")
            schema = json.loads(payload)
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            raise _error("schema", f"could not load packaged schema: {exc}") from exc
        if not isinstance(schema, dict):
            raise _error("schema", "packaged schema must be an object")
        return deepcopy(schema)

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive copy suitable for JSON serialization."""
        return deepcopy(self._document)

    def to_json(self) -> str:
        """Return deterministic JSON with sorted keys and no insignificant whitespace."""
        return json.dumps(self._document, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

    def write(self, path: str | Path) -> None:
        """Write the canonical JSON representation to a UTF-8 file."""
        Path(path).write_text(self.to_json() + "\n", encoding="utf-8")

    def validate(
        self,
        *,
        registry: DomainRegistry | None = None,
        columns: Iterable[str] | None = None,
    ) -> "CellDatasetManifest":
        """Validate optional trusted-profile identity and declared physical columns."""
        if registry is not None:
            self.validate_against_registry(registry)
        if columns is not None:
            self.validate_columns(columns)
        return self

    def validate_against_registry(self, registry: DomainRegistry) -> DomainProfile:
        """Validate domain, ID, profile version, and boundary identity against a registry."""
        if not isinstance(registry, DomainRegistry):
            raise _error("registry", "must be a DomainRegistry")
        try:
            profile = registry.get(self.domain_code)
        except UnknownDomainError as exc:
            raise _error("domain_code", f"is not present in the trusted registry: {self.domain_code!r}") from exc
        if profile.domain_id != self.domain_id:
            raise _error(
                "domain_id",
                f"{self.domain_id} does not match trusted domain {self.domain_code!r} ID {profile.domain_id}",
            )
        profile_version = getattr(profile, "profile_version", None)
        if profile_version is None:
            raise _error("profile_version", "trusted registry profile does not expose a profile version")
        if profile_version != self.profile_version:
            raise _error(
                "profile_version",
                f"{self.profile_version!r} does not match trusted profile {profile_version!r}",
            )
        boundary_sha256 = self.coverage["boundary_sha256"]
        trusted_boundary_sha256 = getattr(profile, "boundary_sha256", None)
        if boundary_sha256 is not None and trusted_boundary_sha256 is not None and boundary_sha256 != trusted_boundary_sha256:
            raise _error("coverage.boundary_sha256", "does not match the trusted profile boundary hash")
        return profile

    def validate_columns(self, columns: Iterable[str]) -> None:
        """Validate declared Parquet column names against manifest requirements."""
        try:
            column_list = list(columns)
        except TypeError as exc:
            raise _error("columns", "must be an iterable of strings") from exc
        if any(not isinstance(column, str) for column in column_list):
            raise _error("columns", "must contain only strings")
        if len(set(column_list)) != len(column_list):
            raise _error("columns", "must not contain duplicate names")
        available = set(column_list)

        if self.identity["gid_column"] not in available:
            raise _error("identity.gid_column", "declared column is missing")
        for field in self.value_fields:
            if field["name"] not in available:
                raise _error(f"value_fields[{field['name']!r}]", "declared value column is missing")
        for field_name in ("packed_id_column", "x_idx_column", "y_idx_column"):
            column = self.identity[field_name]
            if column is not None and column not in available:
                raise _error(f"identity.{field_name}", "declared column is missing")

        if self.dataset_type == "cell_contributions" and not ({"source_id", "source_row"} & available):
            raise _error("dataset_type", "cell_contributions requires source_id or source_row")
        geometry_column = self.storage["geometry_column"]
        if geometry_column is not None and geometry_column not in available:
            raise _error("storage.geometry_column", "declared column is missing")

    @property
    def manifest_version(self) -> str:
        return self._document["manifest_version"]

    @property
    def dataset_type(self) -> str:
        return self._document["dataset_type"]

    @property
    def grid_system(self) -> str:
        return self._document["grid_system"]

    @property
    def grid_version(self) -> str:
        return self._document["grid_version"]

    @property
    def domain_code(self) -> str:
        return self._document["domain_code"]

    @property
    def domain_id(self) -> int:
        return self._document["domain_id"]

    @property
    def level(self) -> int:
        return self._document["level"]

    @property
    def profile_version(self) -> str:
        return self._document["profile_version"]

    @property
    def registry_version(self) -> str:
        return self._document["registry_version"]

    @property
    def value_fields(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(field) for field in self._document["value_fields"])

    @property
    def value_field_names(self) -> tuple[str, ...]:
        return tuple(field["name"] for field in self._document["value_fields"])

    @property
    def identity(self) -> dict[str, Any]:
        return deepcopy(self._document["identity"])

    @property
    def coverage(self) -> dict[str, Any]:
        return deepcopy(self._document["coverage"])

    @property
    def source(self) -> dict[str, Any]:
        return deepcopy(self._document["source"])

    @property
    def storage(self) -> dict[str, Any]:
        return deepcopy(self._document["storage"])

    @property
    def provenance(self) -> dict[str, Any]:
        return deepcopy(self._document["provenance"])

    @property
    def is_queryable(self) -> bool:
        return all(
            self.identity[field_name] is not None
            for field_name in ("packed_id_column", "x_idx_column", "y_idx_column")
        )

    @property
    def reserved_columns(self) -> frozenset[str]:
        return _RESERVED_COLUMNS
