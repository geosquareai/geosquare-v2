"""Explicit operational country-boundary policies for V2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Iterable

from .errors import ArtifactHashMismatchError, GeometryDependencyError, ValidationError
from .geometry import profile_grid_crs, projected_cell_geometry
from .grid import CoordinateTransformer, GeosquareGrid
from .model import CanonicalCell
from .release import ReleaseProfile


class BoundaryPredicate(str, Enum):
    """Named rules for deciding whether a point or cell is operationally included."""

    COVERS_POINT = "COVERS_POINT"
    CENTROID_COVERED = "CENTROID_COVERED"
    INTERSECTS = "INTERSECTS"
    MIN_COVERAGE = "MIN_COVERAGE"


def _require_geometry() -> tuple[object, object, object, object, object]:
    try:
        from pyproj import CRS, Transformer
        from shapely import make_valid
        from shapely.geometry import GeometryCollection, Point, shape
        from shapely.ops import transform, unary_union
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise GeometryDependencyError(
            "boundary policies require the 'geo' optional dependency group"
        ) from exc
    return CRS, Transformer, make_valid, (GeometryCollection, Point, shape), (transform, unary_union)


def _normalize_polygonal(geometry: object) -> object:
    _, _, make_valid, geometry_tools, operation_tools = _require_geometry()
    geometry_collection, _, _ = geometry_tools
    _, unary_union = operation_tools
    if not hasattr(geometry, "geom_type"):
        raise ValidationError("boundary must be a Shapely polygonal geometry")
    candidate = geometry if geometry.is_valid else make_valid(geometry)
    if candidate.is_empty:
        raise ValidationError("boundary must not be empty")
    if candidate.geom_type in {"Polygon", "MultiPolygon"}:
        return candidate
    if candidate.geom_type == "GeometryCollection":
        polygons = [part for part in candidate.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        if polygons:
            merged = unary_union(polygons)
            if merged.geom_type in {"Polygon", "MultiPolygon"}:
                return merged
        raise ValidationError("boundary collection must contain polygonal parts")
    raise ValidationError("boundary must be Polygon, MultiPolygon, or a polygonal GeometryCollection")


def _as_predicate(predicate: BoundaryPredicate | str) -> BoundaryPredicate:
    try:
        return predicate if isinstance(predicate, BoundaryPredicate) else BoundaryPredicate(predicate)
    except ValueError as exc:
        raise ValidationError(
            "boundary_predicate must be COVERS_POINT, CENTROID_COVERED, INTERSECTS, or MIN_COVERAGE"
        ) from exc


def _validate_threshold(value: float | None) -> float:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError("min_coverage is required for MIN_COVERAGE")
    threshold = float(value)
    if not 0 <= threshold <= 1:
        raise ValidationError("min_coverage must be in [0, 1]")
    return threshold


@dataclass(frozen=True, slots=True)
class OperationalBoundary:
    """A country boundary transformed into one domain's grid CRS."""

    geometry: object
    source_crs: str
    grid_crs: str
    source_path: str | None = None
    source_sha256: str | None = None

    @classmethod
    def from_geometry(
        cls,
        geometry: object,
        *,
        source_crs: str,
        grid_crs: str,
    ) -> "OperationalBoundary":
        CRS, Transformer, _, _, operation_tools = _require_geometry()
        transform, _ = operation_tools
        normalized = _normalize_polygonal(geometry)
        source = CRS.from_user_input(source_crs)
        destination = CRS.from_user_input(grid_crs)
        if source == destination:
            projected = normalized
        else:
            transformer = Transformer.from_crs(source, destination, always_xy=True)
            projected = transform(transformer.transform, normalized)
        return cls(_normalize_polygonal(projected), source_crs, grid_crs)

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        source_crs: str,
        grid_crs: str,
        expected_sha256: str | None = None,
    ) -> "OperationalBoundary":
        _, _, _, geometry_tools, _ = _require_geometry()
        _, _, shape = geometry_tools
        boundary_path = Path(path).resolve()
        try:
            content = boundary_path.read_bytes()
        except OSError as exc:
            raise ValidationError(f"boundary file cannot be read: {boundary_path}") from exc
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise ArtifactHashMismatchError(
                f"boundary SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
            )
        try:
            document = json.loads(content.decode("utf-8"))
            geometry = shape(document)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise ValidationError(f"boundary file is not valid GeoJSON: {boundary_path}") from exc
        result = cls.from_geometry(geometry, source_crs=source_crs, grid_crs=grid_crs)
        return cls(result.geometry, result.source_crs, result.grid_crs, str(boundary_path), actual_sha256)

    @classmethod
    def from_profile(
        cls,
        grid: GeosquareGrid,
        boundary_root: str | Path,
    ) -> "OperationalBoundary":
        if not isinstance(grid.profile, ReleaseProfile):
            raise ValidationError("profile-boundary loading requires a verified ReleaseProfile")
        root = Path(boundary_root).resolve()
        relative = Path(grid.profile.boundary_file)
        candidates = [root / relative, root / "profiles" / relative]
        path = next((candidate.resolve() for candidate in candidates if candidate.resolve().is_file()), None)
        if path is None:
            raise ValidationError(f"boundary file is missing below {root}: {grid.profile.boundary_file}")
        return cls.from_file(
            path,
            source_crs=grid.profile.boundary_source_crs,
            grid_crs=profile_grid_crs(grid.profile),
            expected_sha256=grid.profile.boundary_sha256,
        )

    def covers_projected(self, x_m: float, y_m: float) -> bool:
        _, _, _, geometry_tools, _ = _require_geometry()
        _, Point, _ = geometry_tools
        return bool(self.geometry.covers(Point(float(x_m), float(y_m))))

    def covers_lonlat(self, longitude: float, latitude: float, transformer: CoordinateTransformer) -> bool:
        if not hasattr(transformer, "transform"):
            raise ValidationError("transformer must provide transform(longitude, latitude)")
        x_m, y_m = transformer.transform(longitude, latitude)
        return self.covers_projected(x_m, y_m)

    def coverage_ratio(self, grid: GeosquareGrid, cell_or_gid: CanonicalCell | str) -> float:
        cell_geometry = projected_cell_geometry(grid, cell_or_gid)
        intersection = self.geometry.intersection(cell_geometry)
        return max(0.0, min(1.0, float(intersection.area / cell_geometry.area)))

    def cell_matches(
        self,
        grid: GeosquareGrid,
        cell_or_gid: CanonicalCell | str,
        predicate: BoundaryPredicate | str,
        *,
        min_coverage: float | None = None,
    ) -> bool:
        selected = _as_predicate(predicate)
        if selected is BoundaryPredicate.COVERS_POINT:
            raise ValidationError("COVERS_POINT is for points; use a cell predicate for cells")
        cell_geometry = projected_cell_geometry(grid, cell_or_gid)
        if selected is BoundaryPredicate.CENTROID_COVERED:
            return bool(self.geometry.covers(cell_geometry.centroid))
        if selected is BoundaryPredicate.INTERSECTS:
            return bool(self.geometry.intersects(cell_geometry))
        return self.coverage_ratio(grid, cell_or_gid) >= _validate_threshold(min_coverage)

    def filter_cells(
        self,
        grid: GeosquareGrid,
        cells: Iterable[CanonicalCell],
        predicate: BoundaryPredicate | str,
        *,
        min_coverage: float | None = None,
    ) -> tuple[CanonicalCell, ...]:
        return tuple(
            cell
            for cell in cells
            if self.cell_matches(grid, cell, predicate, min_coverage=min_coverage)
        )

    def k_ring(
        self,
        grid: GeosquareGrid,
        cell_or_gid: CanonicalCell | str,
        k: int,
        predicate: BoundaryPredicate | str,
        *,
        min_coverage: float | None = None,
    ) -> tuple[CanonicalCell, ...]:
        return self.filter_cells(
            grid,
            grid.k_ring(cell_or_gid, k),
            predicate,
            min_coverage=min_coverage,
        )

    def k_disk(
        self,
        grid: GeosquareGrid,
        cell_or_gid: CanonicalCell | str,
        k: int,
        predicate: BoundaryPredicate | str,
        *,
        min_coverage: float | None = None,
    ) -> tuple[CanonicalCell, ...]:
        return self.filter_cells(
            grid,
            grid.k_disk(cell_or_gid, k),
            predicate,
            min_coverage=min_coverage,
        )
