"""Optional vectorized NumPy, Pandas, and Arrow encoders for Geosquare V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .codec import BASE_2_MATRIX, BASE_5_MATRIX, SUBDIVISIONS, side_cell_count, validate_level
from .errors import GeometryDependencyError, OutOfDomainError, ValidationError
from .geometry import _require_geometry, profile_grid_crs
from .grid import GeosquareGrid


@dataclass(frozen=True, slots=True)
class BatchEncoding:
    """Vectorized canonical and packed V2 outputs, preserving input array shape."""

    domain_code: str
    level: int
    x_idx: Any
    y_idx: Any
    gid: Any
    packed_id: Any


def _require_numpy() -> Any:
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised without batch extra
        raise GeometryDependencyError("batch operations require the 'batch' optional dependency group") from exc
    return np


def _coordinate_arrays(x_m: Any, y_m: Any) -> tuple[Any, Any, Any]:
    np = _require_numpy()
    x = np.asarray(x_m)
    y = np.asarray(y_m)
    if x.shape != y.shape:
        raise ValidationError("x_m and y_m must have identical shapes")
    if x.dtype.kind not in "iuf" or y.dtype.kind not in "iuf":
        raise ValidationError("x_m and y_m arrays must have numeric dtypes")
    x = x.astype(np.float64, copy=False)
    y = y.astype(np.float64, copy=False)
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValidationError("x_m and y_m arrays must contain only finite values")
    return np, x, y


def _gid_array(np: Any, level: int, x_idx: Any, y_idx: Any) -> Any:
    if level == 0:
        return np.full(x_idx.shape, "", dtype="<U1")
    x = x_idx.copy()
    y = y_idx.copy()
    characters: list[Any] = []
    matrices = {5: np.asarray(BASE_5_MATRIX), 2: np.asarray(BASE_2_MATRIX)}
    for step in reversed(SUBDIVISIONS[:level]):
        characters.append(matrices[step][y % step, x % step])
        x //= step
        y //= step
    gid = characters.pop()
    while characters:
        gid = np.char.add(gid, characters.pop())
    return gid


def _packed_array(np: Any, grid: GeosquareGrid, level: int, x_idx: Any, y_idx: Any) -> Any:
    x = x_idx.copy()
    y = y_idx.copy()
    codes: list[Any] = []
    for step in reversed(SUBDIVISIONS[:level]):
        codes.append((y % step) * step + (x % step))
        x //= step
        y //= step
    path = np.zeros(x_idx.shape, dtype=np.int64)
    for step, code in zip(SUBDIVISIONS[:level], reversed(codes)):
        path = (path << (5 if step == 5 else 2)) | code
    return ((grid.profile.domain_id << 54) | (level << 50) | (path << 1)).astype(np.int64, copy=False)


def encode_projected_numpy(grid: GeosquareGrid, x_m: Any, y_m: Any, level: int) -> BatchEncoding:
    """Vectorize projected-coordinate encoding with scalar-equivalent root-edge rules."""
    validate_level(level)
    np, x, y = _coordinate_arrays(x_m, y_m)
    root = grid.profile.root_bounds
    outside = (x < root.min_x) | (x > root.max_x) | (y < root.min_y) | (y > root.max_y)
    if outside.any():
        raise OutOfDomainError(f"{int(outside.sum())} coordinates are outside the {grid.profile.domain_code} root square")
    if level == 0:
        indices = np.zeros(x.shape, dtype=np.int64)
        return BatchEncoding(grid.profile.domain_code, level, indices, indices.copy(), _gid_array(np, level, indices, indices), _packed_array(np, grid, level, indices, indices))
    count = side_cell_count(level)
    side = grid.profile.root_side_m / count
    x_idx = np.floor((x - root.min_x) / side).astype(np.int64)
    y_idx = np.floor((y - root.min_y) / side).astype(np.int64)
    x_idx = np.where(x == root.max_x, count - 1, x_idx)
    y_idx = np.where(y == root.max_y, count - 1, y_idx)
    return BatchEncoding(
        grid.profile.domain_code,
        level,
        x_idx,
        y_idx,
        _gid_array(np, level, x_idx, y_idx),
        _packed_array(np, grid, level, x_idx, y_idx),
    )


def encode_lonlat_numpy(grid: GeosquareGrid, longitude: Any, latitude: Any, level: int) -> BatchEncoding:
    """Transform WGS84 arrays with ``always_xy=True`` then encode without row loops."""
    np, lon, lat = _coordinate_arrays(longitude, latitude)
    CRS, Transformer, _ = _require_geometry()
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(profile_grid_crs(grid.profile)), always_xy=True)
    # PyProj 3.7.2's scalar fast path misclassifies NumPy 2.3 arrays on Python 3.14.
    # Lists select PyProj's vector transform path; numeric indexing remains NumPy-vectorized.
    x_values, y_values = transformer.transform(lon.reshape(-1).tolist(), lat.reshape(-1).tolist())
    x_m = np.asarray(x_values, dtype=np.float64).reshape(lon.shape)
    y_m = np.asarray(y_values, dtype=np.float64).reshape(lat.shape)
    return encode_projected_numpy(grid, x_m, y_m, level)


def _pandas_result(grid: GeosquareGrid, result: BatchEncoding, index: Any) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise GeometryDependencyError("Pandas adapters require the 'batch' optional dependency group") from exc
    return pd.DataFrame(
        {"domain": grid.profile.domain_code, "level": result.level, "x_idx": result.x_idx, "y_idx": result.y_idx, "gid": result.gid, "packed_id": result.packed_id},
        index=index,
    )


def encode_projected_pandas(
    grid: GeosquareGrid,
    frame: Any,
    x_column: str,
    y_column: str,
    level: int,
) -> Any:
    """Return a Pandas result frame without row-wise numeric encoding."""
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise GeometryDependencyError("Pandas adapters require the 'batch' optional dependency group") from exc
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    return _pandas_result(grid, encode_projected_numpy(grid, frame[x_column].to_numpy(), frame[y_column].to_numpy(), level), frame.index)


def encode_lonlat_pandas(
    grid: GeosquareGrid,
    frame: Any,
    longitude_column: str,
    latitude_column: str,
    level: int,
) -> Any:
    """Transform WGS84 Pandas columns then return vectorized V2 outputs."""
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover
        raise GeometryDependencyError("Pandas adapters require the 'batch' optional dependency group") from exc
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    return _pandas_result(grid, encode_lonlat_numpy(grid, frame[longitude_column].to_numpy(), frame[latitude_column].to_numpy(), level), frame.index)


def _arrow_result(pa: Any, grid: GeosquareGrid, result: BatchEncoding) -> Any:
    return pa.table(
        {
            "domain": pa.array([grid.profile.domain_code] * len(result.x_idx), type=pa.string()),
            "level": pa.array([result.level] * len(result.x_idx), type=pa.int8()),
            "x_idx": pa.array(result.x_idx, type=pa.int64()),
            "y_idx": pa.array(result.y_idx, type=pa.int64()),
            "gid": pa.array(result.gid, type=pa.string()),
            "packed_id": pa.array(result.packed_id, type=pa.int64()),
        }
    )


def _arrow_coordinates(table: Any, first_column: str, second_column: str) -> tuple[Any, Any, Any]:
    try:
        import pyarrow as pa
    except ImportError as exc:  # pragma: no cover
        raise GeometryDependencyError("Arrow adapters require the 'batch' optional dependency group") from exc
    if not isinstance(table, pa.Table):
        raise ValidationError("table must be a pyarrow.Table")
    first = table[first_column].combine_chunks()
    second = table[second_column].combine_chunks()
    if first.null_count or second.null_count:
        raise ValidationError("Arrow coordinate columns must not contain nulls")
    return pa, first.to_numpy(zero_copy_only=False), second.to_numpy(zero_copy_only=False)


def encode_projected_arrow(grid: GeosquareGrid, table: Any, x_column: str, y_column: str, level: int) -> Any:
    """Return an Arrow table using columnar extraction and NumPy vector kernels."""
    pa, x, y = _arrow_coordinates(table, x_column, y_column)
    return _arrow_result(pa, grid, encode_projected_numpy(grid, x, y, level))


def encode_lonlat_arrow(grid: GeosquareGrid, table: Any, longitude_column: str, latitude_column: str, level: int) -> Any:
    """Transform WGS84 Arrow columns then return vectorized V2 outputs."""
    pa, longitude, latitude = _arrow_coordinates(table, longitude_column, latitude_column)
    return _arrow_result(pa, grid, encode_lonlat_numpy(grid, longitude, latitude, level))
