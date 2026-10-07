"""Optional fsspec filesystem support for the GeoSquare dataset format."""

from __future__ import annotations

from collections.abc import Iterable
import io
import math
import posixpath
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from .cell_manifest import CellDatasetManifest
from .dataset import (
    _DATA_DIRECTORY,
    _MANIFEST_FILENAME,
    _MANIFEST_METADATA_KEY,
    _PARQUET_FILENAME,
    _dataset_error,
    _projected_query_window,
    _require_pyarrow,
    _validate_query_bbox,
    CellDataset,
)
from .errors import CellDatasetError, CellDatasetManifestError, FilesystemDependencyError, GeometryDependencyError, ValidationError
from .registry import DomainRegistry
from .release import ReleaseProfile


def _require_fsspec() -> Any:
    try:
        import fsspec
    except ImportError as exc:  # pragma: no cover - exercised without filesystem extra
        raise FilesystemDependencyError(
            "filesystem operations require the 'filesystem' optional dependency group"
        ) from exc
    return fsspec


class FilesystemDatasetStore:
    """Filesystem handle for the standard manifest-plus-Parquet dataset layout."""

    def __init__(self, url: str | Path, *, filesystem: Any | None = None) -> None:
        fsspec = _require_fsspec()
        raw_url = str(url)
        if filesystem is None:
            self.filesystem, self.root = fsspec.core.url_to_fs(raw_url)
        else:
            self.filesystem = filesystem
            self.root = raw_url.split("://", 1)[1] if "://" in raw_url else raw_url
        self.root = self.root.rstrip("/")
        if not self.root:
            raise ValidationError("filesystem dataset URL must include a non-empty path")

    def path(self, *parts: str) -> str:
        return posixpath.join(self.root, *(part.strip("/") for part in parts))

    def exists(self, path: str | None = None) -> bool:
        return bool(self.filesystem.exists(path or self.root))

    def read_bytes(self, path: str) -> bytes:
        with self.filesystem.open(path, "rb") as stream:
            return stream.read()

    def write_bytes(self, path: str, payload: bytes) -> None:
        with self.filesystem.open(path, "wb") as stream:
            stream.write(payload)

    def parquet_files(self) -> list[str]:
        return sorted(self.filesystem.glob(self.path(_DATA_DIRECTORY, "*.parquet")))


def _parquet_payload(dataset: CellDataset) -> bytes:
    pa, pq, _ = _require_pyarrow()
    metadata = dict(dataset.table.schema.metadata or {})
    metadata[_MANIFEST_METADATA_KEY] = dataset.manifest.to_json().encode("utf-8")
    table = dataset.table.replace_schema_metadata(metadata)
    buffer = io.BytesIO()
    compression = dataset.manifest.storage["parquet_compression"]
    pq.write_table(table, buffer, compression=compression)
    return buffer.getvalue()


def _manifest_from_sidecar(store: FilesystemDatasetStore, *, registry: DomainRegistry | None) -> CellDatasetManifest:
    sidecar_path = store.path(_MANIFEST_FILENAME)
    if not store.exists(sidecar_path):
        raise _dataset_error(sidecar_path, "manifest sidecar does not exist")
    try:
        return CellDatasetManifest.from_json(store.read_bytes(sidecar_path), registry=registry)
    except CellDatasetManifestError as exc:
        raise _dataset_error(sidecar_path, f"sidecar manifest is invalid: {exc}") from exc


def _embedded_manifest(payload: bytes, path: str, *, registry: DomainRegistry | None) -> CellDatasetManifest:
    pa, pq, _ = _require_pyarrow()
    try:
        metadata = pq.read_metadata(pa.BufferReader(payload)).metadata or {}
    except Exception as exc:
        raise _dataset_error(path, f"could not read Parquet metadata: {exc}") from exc
    embedded = metadata.get(_MANIFEST_METADATA_KEY)
    if embedded is None:
        raise _dataset_error(path, "missing geosquare.manifest Parquet metadata")
    try:
        return CellDatasetManifest.from_json(embedded, registry=registry)
    except CellDatasetManifestError as exc:
        raise _dataset_error(path, f"embedded manifest is invalid: {exc}") from exc


def _as_dataset(value: CellDataset | Any, *, manifest: CellDatasetManifest | dict[str, Any] | None, registry: DomainRegistry | None) -> CellDataset:
    if isinstance(value, CellDataset):
        if manifest is not None:
            raise ValidationError("manifest cannot override a CellDataset")
        if registry is not None and value.registry is not registry:
            raise ValidationError("registry cannot override a CellDataset")
        return value
    if manifest is None:
        raise ValidationError("manifest is required when writing a raw table")
    return CellDataset.from_table(value, manifest, registry=registry)


def write_cell_dataset_filesystem(
    dataset: CellDataset | Any,
    url: str | Path,
    *,
    manifest: CellDatasetManifest | dict[str, Any] | None = None,
    registry: DomainRegistry | None = None,
    filesystem: Any | None = None,
) -> str:
    """Write a validated dataset to a local, memory, or remote fsspec URL."""
    store = FilesystemDatasetStore(url, filesystem=filesystem)
    if store.exists():
        raise _dataset_error(store.root, "destination already exists")
    validated = _as_dataset(dataset, manifest=manifest, registry=registry)
    temporary_root = f"{store.root}.tmp-{uuid4().hex}"
    temporary = FilesystemDatasetStore(temporary_root, filesystem=store.filesystem)
    try:
        store.filesystem.makedirs(temporary.path(_DATA_DIRECTORY), exist_ok=False)
        temporary.write_bytes(
            temporary.path(_MANIFEST_FILENAME),
            (validated.manifest.to_json() + "\n").encode("utf-8"),
        )
        temporary.write_bytes(
            temporary.path(_DATA_DIRECTORY, _PARQUET_FILENAME),
            _parquet_payload(validated),
        )
        store.filesystem.mv(temporary.root, store.root, recursive=True)
    except Exception:
        try:
            if store.filesystem.exists(temporary.root):
                store.filesystem.rm(temporary.root, recursive=True)
        except Exception:
            pass
        raise
    return str(url)


def read_cell_dataset_filesystem(
    url: str | Path,
    *,
    registry: DomainRegistry | None = None,
    filesystem: Any | None = None,
) -> CellDataset:
    """Read and validate the standard dataset layout through fsspec."""
    pa, pq, _ = _require_pyarrow()
    store = FilesystemDatasetStore(url, filesystem=filesystem)
    if not store.exists():
        raise _dataset_error(store.root, "dataset directory does not exist")
    data_path = store.path(_DATA_DIRECTORY)
    if not store.filesystem.isdir(data_path):
        raise _dataset_error(data_path, "data directory does not exist")
    manifest = _manifest_from_sidecar(store, registry=registry)
    parquet_paths = store.parquet_files()
    if not parquet_paths:
        raise _dataset_error(data_path, "contains no Parquet files")
    expected_json = manifest.to_json()
    tables = []
    for parquet_path in parquet_paths:
        payload = store.read_bytes(parquet_path)
        embedded = _embedded_manifest(payload, parquet_path, registry=registry)
        if embedded.to_json() != expected_json:
            raise _dataset_error(parquet_path, "embedded manifest does not match the manifest.json sidecar")
        try:
            tables.append(pq.read_table(pa.BufferReader(payload)))
        except Exception as exc:
            raise _dataset_error(parquet_path, f"could not read Parquet data: {exc}") from exc
    table = tables[0] if len(tables) == 1 else pa.concat_tables(tables)
    return CellDataset(table, manifest, registry=registry)


def _filesystem_query_windows(
    bbox: Iterable[float],
    manifest: CellDatasetManifest,
    registry: DomainRegistry,
) -> list[tuple[int, int, int, int]]:
    try:
        from pyproj import CRS, Transformer
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise GeometryDependencyError("bbox queries require the 'geo' optional dependency group") from exc
    profile = registry.get(manifest.domain_code)
    if not isinstance(profile, ReleaseProfile):
        raise _dataset_error("registry", "bbox queries require a trusted ReleaseProfile with CRS metadata")
    transformer = Transformer.from_crs(
        CRS.from_epsg(4326),
        CRS.from_user_input(profile.crs_wkt2),
        always_xy=True,
    )
    windows: list[tuple[int, int, int, int]] = []
    for min_lon, min_lat, max_lon, max_lat in _validate_query_bbox(bbox):
        transformed = [
            transformer.transform(longitude, latitude)
            for longitude, latitude in (
                (min_lon, min_lat),
                (min_lon, max_lat),
                (max_lon, min_lat),
                (max_lon, max_lat),
            )
        ]
        projected_bbox = (
            min(point[0] for point in transformed),
            min(point[1] for point in transformed),
            max(point[0] for point in transformed),
            max(point[1] for point in transformed),
        )
        window = _projected_query_window(projected_bbox, profile, manifest.level)
        if window is not None and window not in windows:
            windows.append(window)
    return windows


def query_cell_dataset_filesystem(
    url: str | Path,
    *,
    bbox: Iterable[float],
    domain: str | None = None,
    level: int | None = None,
    registry: DomainRegistry | None = None,
    filesystem: Any | None = None,
) -> Any:
    """Query an fsspec-backed dataset while preserving local query semantics.

    The validated table is filtered with Arrow compute expressions after reading the
    filesystem-backed fragments. Local ``query_cell_dataset`` retains predicate
    pushdown; this backend-neutral path prioritizes identical validation and results.
    """
    pa, _, _ = _require_pyarrow()
    if not isinstance(registry, DomainRegistry):
        raise _dataset_error("registry", "a trusted DomainRegistry is required for bbox queries")
    dataset = read_cell_dataset_filesystem(url, registry=registry, filesystem=filesystem)
    manifest = dataset.manifest
    if not manifest.is_queryable:
        raise _dataset_error("identity", "dataset is compact and has no complete x/y query index")
    if domain is not None and domain != manifest.domain_code:
        raise _dataset_error("domain", f"requested {domain!r}, but dataset domain is {manifest.domain_code!r}")
    if level is not None:
        if type(level) is not int:
            raise _dataset_error("level", "must be an integer")
        if level != manifest.level:
            raise _dataset_error("level", f"requested {level}, but dataset level is {manifest.level}")
    windows = _filesystem_query_windows(bbox, manifest, registry)
    if not windows:
        result = dataset.table.slice(0, 0)
    else:
        import pyarrow.compute as pc

        x_column = manifest.identity["x_idx_column"]
        y_column = manifest.identity["y_idx_column"]
        x_values = dataset.table[x_column]
        y_values = dataset.table[y_column]
        mask = None
        for x_start, x_stop, y_start, y_stop in windows:
            expression = pc.and_(
                pc.and_(pc.greater_equal(x_values, x_start), pc.less_equal(x_values, x_stop)),
                pc.and_(pc.greater_equal(y_values, y_start), pc.less_equal(y_values, y_stop)),
            )
            mask = expression if mask is None else pc.or_(mask, expression)
        result = dataset.table.filter(mask)
    metadata = dict(result.schema.metadata or {})
    metadata[_MANIFEST_METADATA_KEY] = manifest.to_json().encode("utf-8")
    return result.replace_schema_metadata(metadata)
