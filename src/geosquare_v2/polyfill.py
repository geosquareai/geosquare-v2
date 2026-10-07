"""Bounded fractional polygon coverage for verified Geosquare V2 profiles."""

from __future__ import annotations

from enum import Enum
import math
from typing import TYPE_CHECKING, Iterator

from .boundary import BoundaryPredicate, OperationalBoundary
from .codec import side_cell_count, validate_level
from .errors import CandidateLimitExceededError, GeometryDependencyError, ValidationError
from .geometry import (
    _require_geometry,
    profile_equal_area_crs,
    profile_grid_crs,
    projected_cell_geometry,
)
from .grid import GeosquareGrid
from .model import CanonicalCell
from .release import ReleaseProfile

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry


class CoverageMode(str, Enum):
    """Area basis used for fractional cell coverage."""

    GRID_PLANAR = "GRID_PLANAR"
    EQUAL_AREA = "EQUAL_AREA"


def _require_shapely_utilities() -> tuple[object, object, object, object]:
    try:
        from shapely import make_valid
        from shapely.geometry import GeometryCollection, MultiPolygon, box
        from shapely.ops import transform, unary_union
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise GeometryDependencyError(
            "polyfill operations require the 'geo' optional dependency group"
        ) from exc
    return make_valid, (GeometryCollection, MultiPolygon, box), transform, unary_union


def normalize_polygonal_geometry(geometry: BaseGeometry) -> BaseGeometry:
    """Return a valid Polygon/MultiPolygon, extracting polygonal collection parts."""
    _, geometry_tools, _, unary_union = _require_shapely_utilities()
    geometry_collection, multi_polygon, _ = geometry_tools
    if not hasattr(geometry, "geom_type"):
        raise ValidationError("geometry must be a Shapely polygonal geometry")
    candidate = geometry if geometry.is_valid else _require_shapely_utilities()[0](geometry)
    if candidate.is_empty:
        raise ValidationError("geometry must not be empty")
    if candidate.geom_type in {"Polygon", "MultiPolygon"}:
        return candidate
    if candidate.geom_type == "GeometryCollection":
        polygons = [part for part in candidate.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            raise ValidationError("geometry must contain at least one polygonal component")
        normalized = unary_union(polygons)
        if normalized.geom_type == "Polygon":
            return normalized
        if normalized.geom_type == "MultiPolygon":
            return multi_polygon(list(normalized.geoms))
    raise ValidationError("geometry must be Polygon, MultiPolygon, or a polygonal GeometryCollection")


def _as_mode(mode: CoverageMode | str) -> CoverageMode:
    try:
        return mode if isinstance(mode, CoverageMode) else CoverageMode(mode)
    except ValueError as exc:
        raise ValidationError("coverage_mode must be GRID_PLANAR or EQUAL_AREA") from exc


def _validate_candidate_limit(max_candidate_limit: int) -> None:
    if type(max_candidate_limit) is not int or max_candidate_limit < 1:
        raise ValidationError("max_candidate_limit must be a positive integer")


def _transform_geometry(geometry: BaseGeometry, source_crs: str, destination_crs: str) -> BaseGeometry:
    CRS, Transformer, geometry_tools = _require_geometry()
    _, transform = geometry_tools
    transformer = Transformer.from_crs(
        CRS.from_user_input(source_crs),
        CRS.from_user_input(destination_crs),
        always_xy=True,
    )
    return transform(transformer.transform, geometry)


def _candidate_ranges(grid: GeosquareGrid, clipped: BaseGeometry, level: int) -> tuple[range, range]:
    count = side_cell_count(level)
    side = grid.profile.root_side_m / count
    root = grid.profile.root_bounds
    min_x, min_y, max_x, max_y = clipped.bounds
    min_column = max(0, min(count - 1, math.floor((min_x - root.min_x) / side)))
    min_row = max(0, min(count - 1, math.floor((min_y - root.min_y) / side)))
    max_column = max(0, min(count - 1, math.floor((max_x - root.min_x) / side)))
    max_row = max(0, min(count - 1, math.floor((max_y - root.min_y) / side)))
    return range(min_column, max_column + 1), range(min_row, max_row + 1)


def _clamp_ratio(ratio: float) -> float:
    tolerance = 1e-10
    if -tolerance <= ratio <= 0:
        return 0.0
    if 1 <= ratio <= 1 + tolerance:
        return 1.0
    if not 0 <= ratio <= 1:
        raise ValidationError(f"coverage ratio {ratio!r} is outside [0, 1]")
    return ratio


def polyfill_stream(
    grid: GeosquareGrid,
    geometry: BaseGeometry,
    source_crs: str,
    level: int,
    *,
    coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
    min_coverage: float = 0.0,
    max_candidate_limit: int = 100_000,
    boundary: OperationalBoundary | None = None,
    boundary_predicate: BoundaryPredicate | str | None = None,
    boundary_min_coverage: float | None = None,
) -> Iterator[tuple[str, float]]:
    """Yield ``(bare_gid, coverage_ratio)`` in deterministic row-major order.

    Geometry is transformed with ``always_xy=True``, intersected with the mathematical
    root square, and bounded before any cell enumeration. Country-boundary filtering is
    opt-in: pass an ``OperationalBoundary`` and a named ``boundary_predicate`` when the
    result should follow an operational country policy.
    """
    if not isinstance(grid.profile, ReleaseProfile):
        raise ValidationError("polyfill requires a GeosquareGrid built from a verified ReleaseProfile")
    validate_level(level)
    _validate_candidate_limit(max_candidate_limit)
    if isinstance(min_coverage, bool) or not isinstance(min_coverage, (int, float)):
        raise ValidationError("min_coverage must be a finite number in [0, 1]")
    threshold = float(min_coverage)
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValidationError("min_coverage must be a finite number in [0, 1]")
    if not isinstance(source_crs, str) or not source_crs.strip():
        raise ValidationError("source_crs must be a non-empty CRS definition")
    selected_boundary_predicate: BoundaryPredicate | None = None
    if boundary is None:
        if boundary_predicate is not None or boundary_min_coverage is not None:
            raise ValidationError("boundary_predicate requires an OperationalBoundary")
    else:
        if not isinstance(boundary, OperationalBoundary):
            raise ValidationError("boundary must be an OperationalBoundary")
        if boundary_predicate is None:
            raise ValidationError("boundary_predicate is required when boundary filtering is enabled")
        try:
            selected_boundary_predicate = (
                boundary_predicate
                if isinstance(boundary_predicate, BoundaryPredicate)
                else BoundaryPredicate(boundary_predicate)
            )
        except ValueError as exc:
            raise ValidationError("boundary_predicate is not supported") from exc
        if selected_boundary_predicate is BoundaryPredicate.COVERS_POINT:
            raise ValidationError("COVERS_POINT is for point indexing, not polygon polyfill")
        if selected_boundary_predicate is BoundaryPredicate.MIN_COVERAGE:
            if (
                boundary_min_coverage is None
                or isinstance(boundary_min_coverage, bool)
                or not isinstance(boundary_min_coverage, (int, float))
                or not 0 <= float(boundary_min_coverage) <= 1
            ):
                raise ValidationError("boundary_min_coverage must be a number in [0, 1]")
        elif boundary_min_coverage is not None:
            raise ValidationError("boundary_min_coverage is only valid with MIN_COVERAGE")

    mode = _as_mode(coverage_mode)
    _, geometry_tools, _, _ = _require_shapely_utilities()
    _, _, box = geometry_tools
    normalized = normalize_polygonal_geometry(geometry)
    projected_input = _transform_geometry(normalized, source_crs, profile_grid_crs(grid.profile))
    root = grid.profile.root_bounds
    clipped = projected_input.intersection(box(root.min_x, root.min_y, root.max_x, root.max_y))
    if clipped.is_empty:
        return
    clipped = normalize_polygonal_geometry(clipped)

    columns, rows = _candidate_ranges(grid, clipped, level)
    candidate_count = len(columns) * len(rows)
    if candidate_count > max_candidate_limit:
        raise CandidateLimitExceededError(
            f"polyfill requires {candidate_count} candidates, exceeding max_candidate_limit={max_candidate_limit}"
        )

    for y_idx in rows:
        for x_idx in columns:
            cell = CanonicalCell(grid.profile.domain_code, level, x_idx, y_idx)
            cell_geometry = projected_cell_geometry(grid, cell)
            if boundary is not None and not boundary.cell_matches(
                grid,
                cell,
                selected_boundary_predicate,
                min_coverage=boundary_min_coverage,
            ):
                continue
            # Intersect in the authoritative grid CRS first. Reprojecting neighbouring
            # polygons independently can create a numerical seam in equal-area space.
            planar_intersection = clipped.intersection(cell_geometry)
            if planar_intersection.is_empty or planar_intersection.area <= 0:
                continue
            if mode is CoverageMode.EQUAL_AREA:
                area_cell = _transform_geometry(
                    cell_geometry,
                    profile_grid_crs(grid.profile),
                    profile_equal_area_crs(grid.profile),
                )
                area_intersection = _transform_geometry(
                    planar_intersection,
                    profile_grid_crs(grid.profile),
                    profile_equal_area_crs(grid.profile),
                )
            else:
                area_cell = cell_geometry
                area_intersection = planar_intersection
            ratio = _clamp_ratio(area_intersection.area / area_cell.area)
            if ratio > 0 and ratio >= threshold:
                yield grid.gid_from_canonical(cell), ratio


def polyfill(*args: object, **kwargs: object) -> tuple[tuple[str, float], ...]:
    """Materialize :func:`polyfill_stream` when a finite result is desired."""
    return tuple(polyfill_stream(*args, **kwargs))
