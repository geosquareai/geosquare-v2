"""Pandas table readers and point-to-cell table adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from .boundary import BoundaryPredicate, OperationalBoundary
from .conversion import cell_to_geometry, line_to_cells, point_to_cell, polygon_to_cells
from .errors import GeometryDependencyError, OutsideOperationalBoundaryError, ValidationError
from .facade import GeosquareService
from .polyfill import CoverageMode


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - exercised without table extra
        from .errors import TableDependencyError

        raise TableDependencyError(
            "table operations require the 'table' optional dependency group"
        ) from exc
    return pd


def read_table(source: Any, *, input_format: str | None = None, **read_options: Any) -> Any:
    """Read CSV, XLSX, or Parquet into a Pandas DataFrame."""
    pd = _require_pandas()
    if isinstance(source, pd.DataFrame):
        return source.copy()
    path = Path(source)
    format_name = (input_format or path.suffix.lstrip(".")).lower()
    if format_name in {"csv", "txt"}:
        return pd.read_csv(path, **read_options)
    if format_name in {"xlsx", "xls"}:
        return pd.read_excel(path, **read_options)
    if format_name in {"parquet", "pq"}:
        return pd.read_parquet(path, **read_options)
    raise ValidationError("input_format must be csv, xlsx, or parquet")


def _read_table_chunks(source: Any, *, input_format: str | None, chunksize: int, **read_options: Any) -> Iterator[Any]:
    pd = _require_pandas()
    if isinstance(source, pd.DataFrame):
        for start in range(0, len(source), chunksize):
            yield source.iloc[start : start + chunksize].copy()
        return
    path = Path(source)
    format_name = (input_format or path.suffix.lstrip(".")).lower()
    if format_name in {"csv", "txt"}:
        yield from pd.read_csv(path, chunksize=chunksize, **read_options)
        return
    yield read_table(path, input_format=format_name, **read_options)


def _validate_columns(frame: Any, columns: list[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValidationError(f"missing table columns: {missing}")


def table_to_cells(
    source: Any,
    service: GeosquareService,
    domain_code: str,
    level: int,
    *,
    input_format: str | None = None,
    longitude_column: str | None = "longitude",
    latitude_column: str | None = "latitude",
    x_column: str | None = None,
    y_column: str | None = None,
    keep_columns: list[str] | None = None,
    output_geometry: bool = False,
    geometry_crs: str = "grid",
    geometry_format: str = "wkt",
    boundary_policy: BoundaryPredicate | str | None = None,
    drop_outside_boundary: bool = False,
    boundary_match_column: str = "boundary_match",
    **read_options: Any,
) -> Any:
    """Add V2 cell fields to a point table while preserving selected source fields.

    Use either longitude/latitude columns or projected x/y columns. All input columns
    are retained by default. ``drop_outside_boundary`` only has an effect when a point
    boundary policy is supplied.
    """
    pd = _require_pandas()
    if not isinstance(service, GeosquareService):
        raise ValidationError("service must be a GeosquareService")
    frame = read_table(source, input_format=input_format, **read_options)
    if keep_columns is None:
        result = frame.copy()
    else:
        _validate_columns(frame, keep_columns)
        result = frame.loc[:, keep_columns].copy()

    context = service._context(domain_code)
    if (x_column is None) != (y_column is None):
        raise ValidationError("x_column and y_column must be supplied together")
    if x_column is not None and y_column is not None:
        _validate_columns(frame, [x_column, y_column])
        from .batch import encode_projected_pandas

        encoded = encode_projected_pandas(context.grid, frame, x_column, y_column, level)
        source_coordinates = list(zip(frame[x_column].tolist(), frame[y_column].tolist()))
        coordinate_mode = "projected"
    else:
        if longitude_column is None or latitude_column is None:
            raise ValidationError("provide longitude/latitude or projected x/y columns")
        _validate_columns(frame, [longitude_column, latitude_column])
        from .batch import encode_lonlat_pandas

        encoded = encode_lonlat_pandas(context.grid, frame, longitude_column, latitude_column, level)
        source_coordinates = list(zip(frame[longitude_column].tolist(), frame[latitude_column].tolist()))
        coordinate_mode = "lonlat"

    result["domain"] = encoded["domain"]
    result["level"] = encoded["level"]
    result["x_idx"] = encoded["x_idx"]
    result["y_idx"] = encoded["y_idx"]
    result["gid"] = encoded["gid"]
    result["uri"] = encoded["gid"].map(lambda gid: f"geosquare:v2:{domain_code}:{gid}")
    result["packed_id"] = encoded["packed_id"]

    if boundary_policy is not None:
        boundary = service._boundary(context)
        try:
            selected_boundary_policy = (
                boundary_policy
                if isinstance(boundary_policy, BoundaryPredicate)
                else BoundaryPredicate(boundary_policy)
            )
        except ValueError as exc:
            raise ValidationError("unknown point boundary policy") from exc
        if selected_boundary_policy is not BoundaryPredicate.COVERS_POINT:
            raise ValidationError("table_to_cells point filtering requires COVERS_POINT")
        if coordinate_mode == "lonlat":
            matches = [
                boundary.covers_lonlat(float(first), float(second), context.transformer)
                for first, second in source_coordinates
            ]
        else:
            matches = [boundary.covers_projected(float(first), float(second)) for first, second in source_coordinates]
        result[boundary_match_column] = matches
        if drop_outside_boundary:
            result = result.loc[result[boundary_match_column]].copy()

    if output_geometry:
        result["geometry"] = [
            cell_to_geometry(
                context.grid,
                gid,
                output_crs=geometry_crs,
                geometry_format=geometry_format,
            )
            for gid in result["gid"]
        ]
    return result


def table_to_cells_chunks(
    source: Any,
    service: GeosquareService,
    domain_code: str,
    level: int,
    *,
    chunksize: int = 100_000,
    **kwargs: Any,
) -> Iterator[Any]:
    """Stream point-table conversion in chunks."""
    input_format = kwargs.pop("input_format", None)
    for frame in _read_table_chunks(source, input_format=input_format, chunksize=chunksize):
        yield table_to_cells(
            frame,
            service,
            domain_code,
            level,
            input_format="csv",  # DataFrame input; format is ignored.
            **kwargs,
        )


def write_table(frame: Any, destination: str | Path, *, output_format: str | None = None, **write_options: Any) -> None:
    """Write a converted table to CSV, XLSX, or Parquet."""
    pd = _require_pandas()
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    path = Path(destination)
    format_name = (output_format or path.suffix.lstrip(".")).lower()
    if format_name == "csv":
        frame.to_csv(path, index=False, **write_options)
    elif format_name in {"xlsx", "xls"}:
        frame.to_excel(path, index=False, **write_options)
    elif format_name in {"parquet", "pq"}:
        frame.to_parquet(path, index=False, **write_options)
    else:
        raise ValidationError("output_format must be csv, xlsx, or parquet")


def geometry_table_to_cells(
    source: Any,
    service: GeosquareService,
    domain_code: str,
    level: int,
    *,
    geometry_column: str = "geometry",
    source_id_column: str | None = None,
    source_crs: str = "EPSG:4326",
    keep_columns: list[str] | None = None,
    coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
    min_coverage: float = 0.0,
    max_candidate_limit: int = 100_000,
    boundary: OperationalBoundary | None = None,
    boundary_policy: BoundaryPredicate | str | None = None,
    boundary_min_coverage: float | None = None,
) -> Any:
    """Convert a geometry table into an auditable cell-contribution DataFrame.

    Supported geometry types are Point, MultiPoint, LineString, MultiLineString,
    Polygon, and MultiPolygon. Each output row keeps source provenance and the
    assignment metadata; this function deliberately does not allocate values or
    aggregate contributions.
    """
    pd = _require_pandas()
    if not isinstance(service, GeosquareService):
        raise ValidationError("service must be a GeosquareService")
    if not isinstance(geometry_column, str) or not geometry_column:
        raise ValidationError("geometry_column must be a non-empty string")
    if not isinstance(source_crs, str) or not source_crs.strip():
        raise ValidationError("source_crs must be a non-empty CRS definition")

    frame = read_table(source)
    if geometry_column not in frame.columns:
        raise ValidationError(f"missing table columns: ['{geometry_column}']")
    if source_id_column is not None:
        _validate_columns(frame, [source_id_column])
    if keep_columns is None:
        payload_columns = [column for column in frame.columns if column != geometry_column]
    else:
        _validate_columns(frame, keep_columns)
        if geometry_column in keep_columns:
            raise ValidationError("geometry_column cannot be included in keep_columns")
        payload_columns = list(keep_columns)

    context = service._context(domain_code)
    selected_policy: BoundaryPredicate | None = None
    if boundary_policy is not None:
        try:
            selected_policy = (
                boundary_policy
                if isinstance(boundary_policy, BoundaryPredicate)
                else BoundaryPredicate(boundary_policy)
            )
        except ValueError as exc:
            raise ValidationError("unknown geometry boundary policy") from exc
        if boundary is None:
            boundary = service._boundary(context)
    elif boundary is not None:
        raise ValidationError("boundary_policy is required when boundary filtering is enabled")

    reserved_payload = {
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
        geometry_column,
    }
    payload_columns = [column for column in payload_columns if column not in reserved_payload]
    output_rows: list[dict[str, Any]] = []
    policy_name = selected_policy.value if selected_policy is not None else None

    for source_row, (_, row) in enumerate(frame.iterrows()):
        geometry = row[geometry_column]
        if geometry is None or not hasattr(geometry, "geom_type"):
            raise ValidationError(f"{geometry_column}[{source_row}] must be a Shapely geometry")
        if geometry.is_empty:
            continue
        geometry_type = geometry.geom_type
        records: list[tuple[str, float | None, float | None, str]] = []
        if geometry_type in {"Point", "MultiPoint"}:
            points = (geometry,) if geometry_type == "Point" else tuple(geometry.geoms)
            for point in points:
                try:
                    if source_crs.upper() in {"EPSG:4326", "WGS84", "OGC:CRS84"}:
                        indexed = point_to_cell(
                            context.grid,
                            float(point.x),
                            float(point.y),
                            level,
                            context.transformer,
                            boundary=boundary,
                            boundary_policy=selected_policy,
                        )
                    else:
                        try:
                            from pyproj import CRS, Transformer
                        except ImportError as exc:  # pragma: no cover - exercised without geo extra
                            raise GeometryDependencyError(
                                "geometry conversion requires the 'geo' optional dependency group"
                            ) from exc
                        transformer = Transformer.from_crs(
                            CRS.from_user_input(source_crs),
                            CRS.from_user_input(context.profile.crs_wkt2),
                            always_xy=True,
                        )
                        x_m, y_m = transformer.transform(float(point.x), float(point.y))
                        cell = context.grid.canonical_from_projected(x_m, y_m, level)
                        if selected_policy is not None:
                            if selected_policy is not BoundaryPredicate.COVERS_POINT:
                                raise ValidationError("point geometry requires the COVERS_POINT policy")
                            if not boundary.covers_projected(x_m, y_m):
                                continue
                        indexed = None
                        projected_gid = context.grid.gid_from_canonical(cell)
                except OutsideOperationalBoundaryError:
                    continue
                if indexed is not None:
                    point_gid = indexed.gid
                else:
                    point_gid = projected_gid
                records.append((point_gid, None, None, "point_to_cell"))
        elif geometry_type in {"LineString", "MultiLineString"}:
            line_records = line_to_cells(
                context.grid,
                geometry,
                source_crs,
                level,
                max_candidate_limit=max_candidate_limit,
                boundary=boundary,
                boundary_policy=selected_policy,
                boundary_min_coverage=boundary_min_coverage,
            )
            records.extend((record.gid, record.coverage_ratio, record.length_ratio, "line_to_cells") for record in line_records)
        elif geometry_type in {"Polygon", "MultiPolygon"}:
            polygon_records = polygon_to_cells(
                context.grid,
                geometry,
                source_crs,
                level,
                coverage_mode=coverage_mode,
                min_coverage=min_coverage,
                max_candidate_limit=max_candidate_limit,
                boundary=boundary,
                boundary_policy=selected_policy,
                boundary_min_coverage=boundary_min_coverage,
            )
            coverage_total = sum(record.coverage_ratio or 0.0 for record in polygon_records)
            if coverage_total <= 0:
                records.extend(
                    (record.gid, record.coverage_ratio, record.length_ratio, "polygon_to_cells")
                    for record in polygon_records
                )
            else:
                records.extend(
                    (
                        record.gid,
                        (record.coverage_ratio or 0.0) / coverage_total,
                        record.length_ratio,
                        "polygon_to_cells",
                    )
                    for record in polygon_records
                )
        else:
            raise ValidationError(
                f"{geometry_column}[{source_row}] has unsupported geometry type {geometry_type!r}"
            )

        if source_id_column is not None:
            source_identifier = row[source_id_column]
            if pd.isna(source_identifier):
                raise ValidationError(f"{source_id_column}[{source_row}] must not be null")
            provenance = {"source_id": str(source_identifier)}
        else:
            provenance = {"source_row": source_row}
        source_values = {column: row[column] for column in payload_columns}
        for gid, coverage_ratio, length_ratio, assignment_method in records:
            output_rows.append(
                {
                    **source_values,
                    "domain": domain_code,
                    "level": level,
                    **provenance,
                    "gid": gid,
                    "uri": f"geosquare:v2:{domain_code}:{gid}",
                    "coverage_ratio": coverage_ratio,
                    "length_ratio": length_ratio,
                    "assignment_method": assignment_method,
                    "boundary_policy": policy_name,
                }
            )

    output_columns = [
        *payload_columns,
        "domain",
        "level",
        "source_id" if source_id_column is not None else "source_row",
        "gid",
        "uri",
        "coverage_ratio",
        "length_ratio",
        "assignment_method",
        "boundary_policy",
    ]
    result = pd.DataFrame(output_rows, columns=output_columns)
    for string_column in ("domain", "gid", "uri", "source_id", "assignment_method", "boundary_policy"):
        if string_column in result.columns:
            result[string_column] = result[string_column].astype("string")
    if "level" in result.columns:
        result["level"] = result["level"].astype("int64")
    if "source_row" in result.columns:
        result["source_row"] = result["source_row"].astype("Int64")
    for ratio_column in ("coverage_ratio", "length_ratio"):
        if ratio_column in result.columns:
            result[ratio_column] = result[ratio_column].astype("Float64")
    return result
