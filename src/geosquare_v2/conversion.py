"""Geometry-to-cell conversion helpers with consistent V2 records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

from .boundary import BoundaryPredicate, OperationalBoundary
from .codec import side_cell_count
from .errors import CandidateLimitExceededError, GeometryDependencyError, ValidationError
from .geometry import _require_geometry, profile_grid_crs, projected_cell_geometry, wgs84_cell_geometry
from .grid import CoordinateTransformer, GeosquareGrid
from .model import CanonicalCell
from .polyfill import CoverageMode, polyfill


@dataclass(frozen=True, slots=True)
class GridCellRecord:
    """One cell result with optional source overlap information and geometry."""

    cell: CanonicalCell
    gid: str
    uri: str
    coverage_ratio: float | None = None
    length_ratio: float | None = None
    geometry: Any | None = None
    source_id: Any | None = None


def _require_conversion_geometry() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from pyproj import CRS, Transformer
        from shapely import make_valid
        from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon, box
        from shapely.ops import transform, unary_union
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise GeometryDependencyError(
            "geometry conversion requires the 'geo' optional dependency group"
        ) from exc
    return CRS, Transformer, make_valid, (GeometryCollection, LineString, MultiLineString, MultiPolygon, Point, Polygon, box), transform, unary_union


def _format_geometry(geometry: Any, geometry_format: str) -> Any:
    if geometry_format == "shapely":
        return geometry
    if geometry_format == "wkt":
        return geometry.wkt
    if geometry_format == "wkb":
        return bytes(geometry.wkb)
    raise ValidationError("geometry_format must be shapely, wkt, or wkb")


def cell_to_geometry(
    grid: GeosquareGrid,
    cell_or_gid: CanonicalCell | str,
    *,
    output_crs: str = "grid",
    geometry_format: str = "shapely",
    max_segment_length_m: float = 25_000.0,
) -> Any:
    """Build one cell geometry in the grid CRS, WGS84, or another CRS."""
    if output_crs.lower() in {"grid", "projected"}:
        geometry = projected_cell_geometry(grid, cell_or_gid)
    elif output_crs.upper() in {"WGS84", "EPSG:4326", "OGC:CRS84"}:
        geometry = wgs84_cell_geometry(
            grid,
            cell_or_gid,
            max_segment_length_m=max_segment_length_m,
        )
    else:
        CRS, Transformer, _, _, transform, _ = _require_conversion_geometry()
        projected = projected_cell_geometry(grid, cell_or_gid)
        transformer = Transformer.from_crs(
            CRS.from_user_input(profile_grid_crs(grid.profile)),
            CRS.from_user_input(output_crs),
            always_xy=True,
        )
        geometry = transform(transformer.transform, projected)
    return _format_geometry(geometry, geometry_format)


def cells_to_geometry(
    grid: GeosquareGrid,
    cells: Iterable[CanonicalCell | str],
    *,
    output_crs: str = "grid",
    geometry_format: str = "shapely",
) -> tuple[Any, ...]:
    """Build geometries for a sequence of cell IDs."""
    return tuple(
        cell_to_geometry(grid, cell, output_crs=output_crs, geometry_format=geometry_format)
        for cell in cells
    )


def point_to_cell(
    grid: GeosquareGrid,
    longitude: float,
    latitude: float,
    level: int,
    transformer: CoordinateTransformer,
    *,
    boundary: OperationalBoundary | None = None,
    boundary_policy: BoundaryPredicate | str | None = None,
) -> IndexedCell:
    """Convert one longitude/latitude point to one V2 cell."""
    from .facade import IndexedCell

    cell = grid.canonical_from_lonlat(longitude, latitude, level, transformer)
    if boundary_policy is not None:
        if boundary is None:
            raise ValidationError("boundary_policy requires an OperationalBoundary")
        if boundary_policy not in {BoundaryPredicate.COVERS_POINT, BoundaryPredicate.COVERS_POINT.value}:
            raise ValidationError("point_to_cell requires the COVERS_POINT policy")
        x_m, y_m = transformer.transform(longitude, latitude)
        if not boundary.covers_projected(x_m, y_m):
            from .errors import OutsideOperationalBoundaryError

            raise OutsideOperationalBoundaryError("point is outside the operational boundary")
    gid = grid.gid_from_canonical(cell)
    return IndexedCell(
        cell=cell,
        gid=gid,
        uri=grid.uri(cell),
        projected_bounds=grid.projected_bounds(cell),
        cell_edge_m=grid.profile.root_side_m / side_cell_count(level),
        profile_version=str(getattr(grid.profile, "profile_version", "unversioned")),
        scale_error_max_pct=float(getattr(grid.profile, "scale_error_max_pct", 0.0)),
        boundary_policy=(boundary_policy.value if isinstance(boundary_policy, BoundaryPredicate) else boundary_policy),
    )


def _project_geometry(geometry: Any, source_crs: str, destination_crs: str) -> Any:
    CRS, Transformer, make_valid, _, transform, _ = _require_conversion_geometry()
    if not hasattr(geometry, "geom_type"):
        raise ValidationError("geometry must be a Shapely geometry")
    candidate = geometry if geometry.is_valid else make_valid(geometry)
    transformer = Transformer.from_crs(
        CRS.from_user_input(source_crs),
        CRS.from_user_input(destination_crs),
        always_xy=True,
    )
    return transform(transformer.transform, candidate)


def _cell_record(
    grid: GeosquareGrid,
    cell: CanonicalCell,
    *,
    coverage_ratio: float | None = None,
    length_ratio: float | None = None,
    output_geometry: bool = False,
    geometry_crs: str = "grid",
    geometry_format: str = "shapely",
    source_id: Any | None = None,
) -> GridCellRecord:
    gid = grid.gid_from_canonical(cell)
    geometry = (
        cell_to_geometry(grid, cell, output_crs=geometry_crs, geometry_format=geometry_format)
        if output_geometry
        else None
    )
    return GridCellRecord(
        cell=cell,
        gid=gid,
        uri=grid.uri(cell),
        coverage_ratio=coverage_ratio,
        length_ratio=length_ratio,
        geometry=geometry,
        source_id=source_id,
    )


def polygon_to_cells(
    grid: GeosquareGrid,
    geometry: Any,
    source_crs: str,
    level: int,
    *,
    coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
    min_coverage: float = 0.0,
    max_candidate_limit: int = 100_000,
    boundary: OperationalBoundary | None = None,
    boundary_policy: BoundaryPredicate | str | None = None,
    boundary_min_coverage: float | None = None,
    output_geometry: bool = False,
    geometry_crs: str = "grid",
    geometry_format: str = "shapely",
) -> tuple[GridCellRecord, ...]:
    """Convert a polygon to intersecting V2 cells with area ratios."""
    pairs = polyfill(
        grid,
        geometry,
        source_crs,
        level,
        coverage_mode=coverage_mode,
        min_coverage=min_coverage,
        max_candidate_limit=max_candidate_limit,
        boundary=boundary,
        boundary_predicate=boundary_policy,
        boundary_min_coverage=boundary_min_coverage,
    )
    return tuple(
        _cell_record(
            grid,
            grid.canonical_from_gid(gid),
            coverage_ratio=ratio,
            output_geometry=output_geometry,
            geometry_crs=geometry_crs,
            geometry_format=geometry_format,
        )
        for gid, ratio in pairs
    )


def polygon_to_cell(
    grid: GeosquareGrid,
    geometry: Any,
    source_crs: str,
    level: int,
    *,
    selection: str = "centroid",
    coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
    max_candidate_limit: int = 100_000,
    boundary: OperationalBoundary | None = None,
    boundary_policy: BoundaryPredicate | str | None = None,
    boundary_min_coverage: float | None = None,
    output_geometry: bool = False,
    geometry_crs: str = "grid",
    geometry_format: str = "shapely",
) -> GridCellRecord:
    """Choose one cell for a polygon using an explicit selection rule."""
    if selection not in {"centroid", "representative_point", "largest_overlap"}:
        raise ValidationError("selection must be centroid, representative_point, or largest_overlap")
    if selection == "largest_overlap":
        records = polygon_to_cells(
            grid,
            geometry,
            source_crs,
            level,
            coverage_mode=coverage_mode,
            max_candidate_limit=max_candidate_limit,
            boundary=boundary,
            boundary_policy=boundary_policy,
            boundary_min_coverage=boundary_min_coverage,
            output_geometry=output_geometry,
            geometry_crs=geometry_crs,
            geometry_format=geometry_format,
        )
        if not records:
            raise ValidationError("polygon does not produce any target cell")
        return max(records, key=lambda record: (record.coverage_ratio or 0.0, record.gid))

    projected = _project_geometry(geometry, source_crs, profile_grid_crs(grid.profile))
    point = projected.centroid if selection == "centroid" else projected.representative_point()
    cell = grid.canonical_from_projected(point.x, point.y, level)
    if boundary is not None and boundary_policy is not None:
        if boundary_policy == BoundaryPredicate.COVERS_POINT or boundary_policy == BoundaryPredicate.COVERS_POINT.value:
            allowed = boundary.covers_projected(point.x, point.y)
        else:
            allowed = boundary.cell_matches(
                grid,
                cell,
                boundary_policy,
                min_coverage=boundary_min_coverage,
            )
        if not allowed:
            raise ValidationError("selected polygon cell fails the boundary policy")
    return _cell_record(
        grid,
        cell,
        output_geometry=output_geometry,
        geometry_crs=geometry_crs,
        geometry_format=geometry_format,
    )


def line_to_cells(
    grid: GeosquareGrid,
    geometry: Any,
    source_crs: str,
    level: int,
    *,
    max_candidate_limit: int = 100_000,
    boundary: OperationalBoundary | None = None,
    boundary_policy: BoundaryPredicate | str | None = None,
    boundary_min_coverage: float | None = None,
    output_geometry: bool = False,
    geometry_crs: str = "grid",
    geometry_format: str = "shapely",
) -> tuple[GridCellRecord, ...]:
    """Convert a line to cells with positive line-length overlap."""
    CRS, Transformer, make_valid, geometry_tools, transform, _ = _require_conversion_geometry()
    _, line_string, multi_line_string, _, _, _, box = geometry_tools
    projected = _project_geometry(geometry, source_crs, profile_grid_crs(grid.profile))
    if projected.geom_type not in {"LineString", "MultiLineString"}:
        raise ValidationError("line_to_cells requires a LineString or MultiLineString")
    if projected.is_empty or projected.length <= 0:
        return ()
    if boundary is None and boundary_policy is not None:
        raise ValidationError("boundary_policy requires an OperationalBoundary")
    if boundary is not None and boundary_policy is None:
        raise ValidationError("boundary_policy is required when boundary filtering is enabled")
    root = grid.profile.root_bounds
    clipped = projected.intersection(box(root.min_x, root.min_y, root.max_x, root.max_y))
    if clipped.is_empty or clipped.length <= 0:
        return ()
    count = side_cell_count(level)
    side = grid.profile.root_side_m / count
    min_x, min_y, max_x, max_y = clipped.bounds
    min_column = max(0, min(count - 1, math.floor((min_x - root.min_x) / side)))
    min_row = max(0, min(count - 1, math.floor((min_y - root.min_y) / side)))
    max_column = max(0, min(count - 1, math.floor((max_x - root.min_x) / side)))
    max_row = max(0, min(count - 1, math.floor((max_y - root.min_y) / side)))
    candidate_count = (max_column - min_column + 1) * (max_row - min_row + 1)
    if candidate_count > max_candidate_limit:
        raise CandidateLimitExceededError(
            f"line conversion requires {candidate_count} candidates, exceeding max_candidate_limit={max_candidate_limit}"
        )

    records: list[GridCellRecord] = []
    total_length = clipped.length
    for y_idx in range(min_row, max_row + 1):
        for x_idx in range(min_column, max_column + 1):
            cell = CanonicalCell(grid.profile.domain_code, level, x_idx, y_idx)
            if boundary is not None and boundary_policy is not None and not boundary.cell_matches(
                grid,
                cell,
                boundary_policy,
                min_coverage=boundary_min_coverage,
            ):
                continue
            overlap_length = clipped.intersection(projected_cell_geometry(grid, cell)).length
            if overlap_length <= 0:
                continue
            records.append(
                _cell_record(
                    grid,
                    cell,
                    length_ratio=float(overlap_length / total_length),
                    output_geometry=output_geometry,
                    geometry_crs=geometry_crs,
                    geometry_format=geometry_format,
                )
            )
    return tuple(records)
