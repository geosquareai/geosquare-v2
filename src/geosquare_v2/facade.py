"""Simple registry-backed public API for common V2 operations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

from .boundary import BoundaryPredicate, OperationalBoundary
from .codec import cell_side_m
from .errors import GeometryDependencyError, OutsideOperationalBoundaryError, ValidationError
from .grid import GeosquareGrid
from .model import CanonicalCell, ProjectedBounds
from .polyfill import CoverageMode, polyfill
from .registry import DomainRegistry
from .release import ReleaseProfile


@dataclass(frozen=True, slots=True)
class IndexedCell:
    """A user-facing V2 cell result with the useful metadata attached."""

    cell: CanonicalCell
    gid: str
    uri: str
    projected_bounds: ProjectedBounds
    cell_edge_m: float
    profile_version: str
    scale_error_max_pct: float
    boundary_policy: str | None = None


def parse_uri(value: str) -> tuple[str, str]:
    """Parse ``geosquare:v2:<domain>:<gid>`` into ``(domain, bare_gid)``."""
    if not isinstance(value, str):
        raise ValidationError("V2 URI must be a string")
    parts = value.split(":", 3)
    if len(parts) != 4 or parts[0] != "geosquare" or parts[1] != "v2" or not parts[2]:
        raise ValidationError("URI must use geosquare:v2:<domain>:<gid>")
    return parts[2], parts[3]


def _validate_lonlat(longitude: float, latitude: float) -> tuple[float, float]:
    if (
        isinstance(longitude, bool)
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or not isinstance(latitude, (int, float))
        or not math.isfinite(longitude)
        or not math.isfinite(latitude)
    ):
        raise ValidationError("longitude and latitude must be finite numbers")
    if not -180 <= longitude <= 180:
        raise ValidationError("longitude must be in [-180, 180]")
    if not -90 <= latitude <= 90:
        raise ValidationError("latitude must be in [-90, 90]")
    return float(longitude), float(latitude)


@dataclass(slots=True)
class _DomainContext:
    profile: ReleaseProfile
    grid: GeosquareGrid
    transformer: Any
    boundary: OperationalBoundary | None = None


class GeosquareService:
    """High-level V2 API backed by a verified domain registry.

    The service creates the correct ``always_xy`` transformer automatically. Boundary
    filtering is still opt-in and must use a named predicate.
    """

    def __init__(
        self,
        registry: DomainRegistry,
        *,
        boundary_root: str | Path | None = None,
    ) -> None:
        if not isinstance(registry, DomainRegistry):
            raise ValidationError("registry must be a DomainRegistry")
        self.registry = registry
        self.boundary_root = Path(boundary_root).resolve() if boundary_root is not None else None
        self._contexts: dict[str, _DomainContext] = {}

    @property
    def domains(self) -> tuple[str, ...]:
        """Return the domain codes available in this registry."""
        return tuple(profile.domain_code for profile in self.registry.profiles())

    def _context(self, domain_code: str) -> _DomainContext:
        if not isinstance(domain_code, str) or not domain_code:
            raise ValidationError("domain_code must be a non-empty string")
        context = self._contexts.get(domain_code)
        if context is not None:
            return context
        profile = self.registry.get(domain_code)
        if not isinstance(profile, ReleaseProfile):
            raise ValidationError("GeosquareService requires verified ReleaseProfile entries")
        try:
            from pyproj import CRS, Transformer
        except ImportError as exc:  # pragma: no cover - exercised without registry/geo extras
            raise GeometryDependencyError(
                "GeosquareService requires the 'geo' optional dependency group"
            ) from exc
        transformer = Transformer.from_crs(
            CRS.from_epsg(4326),
            CRS.from_user_input(profile.crs_wkt2),
            always_xy=True,
        )
        context = _DomainContext(profile, GeosquareGrid(profile), transformer)
        self._contexts[domain_code] = context
        return context

    def _boundary(self, context: _DomainContext) -> OperationalBoundary:
        if context.boundary is None:
            if self.boundary_root is None:
                raise ValidationError(
                    "boundary_root is required for boundary-aware operations"
                )
            context.boundary = OperationalBoundary.from_profile(context.grid, self.boundary_root)
        return context.boundary

    @staticmethod
    def _point_policy(policy: BoundaryPredicate | str) -> BoundaryPredicate:
        try:
            selected = policy if isinstance(policy, BoundaryPredicate) else BoundaryPredicate(policy)
        except ValueError as exc:
            raise ValidationError("unknown boundary policy") from exc
        if selected is not BoundaryPredicate.COVERS_POINT:
            raise ValidationError("point indexing requires the COVERS_POINT policy")
        return selected

    def _result(
        self,
        context: _DomainContext,
        cell: CanonicalCell,
        boundary_policy: BoundaryPredicate | str | None = None,
    ) -> IndexedCell:
        policy = None
        if boundary_policy is not None:
            policy = (
                boundary_policy.value
                if isinstance(boundary_policy, BoundaryPredicate)
                else str(boundary_policy)
            )
        gid = context.grid.gid_from_canonical(cell)
        return IndexedCell(
            cell=cell,
            gid=gid,
            uri=context.grid.uri(cell),
            projected_bounds=context.grid.projected_bounds(cell),
            cell_edge_m=cell_side_m(cell.level),
            profile_version=context.profile.profile_version,
            scale_error_max_pct=context.profile.scale_error_max_pct,
            boundary_policy=policy,
        )

    def index_point(
        self,
        domain_code: str,
        longitude: float,
        latitude: float,
        level: int,
        *,
        boundary_policy: BoundaryPredicate | str | None = None,
    ) -> IndexedCell:
        """Index a lon/lat point without manually creating a CRS transformer."""
        longitude, latitude = _validate_lonlat(longitude, latitude)
        context = self._context(domain_code)
        cell = context.grid.canonical_from_lonlat(
            longitude,
            latitude,
            level,
            context.transformer,
        )
        if boundary_policy is not None:
            policy = self._point_policy(boundary_policy)
            if not self._boundary(context).covers_lonlat(longitude, latitude, context.transformer):
                raise OutsideOperationalBoundaryError(
                    f"point ({longitude}, {latitude}) is outside the {domain_code} operational boundary"
                )
            return self._result(context, cell, policy)
        return self._result(context, cell)

    def point_to_cell(
        self,
        domain_code: str,
        longitude: float,
        latitude: float,
        level: int,
        *,
        boundary_policy: BoundaryPredicate | str | None = None,
    ) -> IndexedCell:
        """Canonical name for point-to-cell conversion."""
        return self.index_point(
            domain_code,
            longitude,
            latitude,
            level,
            boundary_policy=boundary_policy,
        )

    def cell_to_geometry(
        self,
        value: str,
        *,
        domain_code: str | None = None,
        output_crs: str = "grid",
        geometry_format: str = "shapely",
    ) -> Any:
        """Build geometry for one V2 cell."""
        from .conversion import cell_to_geometry

        result = self.describe(value, domain_code=domain_code)
        context = self._context(result.cell.domain_code)
        return cell_to_geometry(
            context.grid,
            result.cell,
            output_crs=output_crs,
            geometry_format=geometry_format,
        )

    def cells_to_geometry(
        self,
        values: Any,
        *,
        domain_code: str | None = None,
        output_crs: str = "grid",
        geometry_format: str = "shapely",
    ) -> tuple[Any, ...]:
        """Build geometry for several V2 cells."""
        from .conversion import cells_to_geometry

        values = tuple(values)
        if not values:
            return ()
        results = tuple(self.describe(value, domain_code=domain_code) for value in values)
        domain = results[0].cell.domain_code
        if any(result.cell.domain_code != domain for result in results):
            raise ValidationError("cells_to_geometry requires one domain")
        context = self._context(domain)
        return cells_to_geometry(
            context.grid,
            (result.cell for result in results),
            output_crs=output_crs,
            geometry_format=geometry_format,
        )

    def polygon_to_cells(
        self,
        domain_code: str,
        geometry: Any,
        source_crs: str,
        level: int,
        *,
        coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
        min_coverage: float = 0.0,
        max_candidate_limit: int = 100_000,
        boundary_policy: BoundaryPredicate | str | None = None,
        boundary_min_coverage: float | None = None,
        output_geometry: bool = False,
        geometry_crs: str = "grid",
        geometry_format: str = "shapely",
    ) -> tuple[Any, ...]:
        """Convert a polygon to cell records."""
        from .conversion import polygon_to_cells

        context = self._context(domain_code)
        boundary = self._boundary(context) if boundary_policy is not None else None
        return polygon_to_cells(
            context.grid,
            geometry,
            source_crs,
            level,
            coverage_mode=coverage_mode,
            min_coverage=min_coverage,
            max_candidate_limit=max_candidate_limit,
            boundary=boundary,
            boundary_policy=boundary_policy,
            boundary_min_coverage=boundary_min_coverage,
            output_geometry=output_geometry,
            geometry_crs=geometry_crs,
            geometry_format=geometry_format,
        )

    def polygon_to_cell(
        self,
        domain_code: str,
        geometry: Any,
        source_crs: str,
        level: int,
        *,
        selection: str = "centroid",
        coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
        max_candidate_limit: int = 100_000,
        boundary_policy: BoundaryPredicate | str | None = None,
        boundary_min_coverage: float | None = None,
        output_geometry: bool = False,
        geometry_crs: str = "grid",
        geometry_format: str = "shapely",
    ) -> Any:
        """Choose one cell for a polygon."""
        from .conversion import polygon_to_cell

        context = self._context(domain_code)
        boundary = self._boundary(context) if boundary_policy is not None else None
        return polygon_to_cell(
            context.grid,
            geometry,
            source_crs,
            level,
            selection=selection,
            coverage_mode=coverage_mode,
            max_candidate_limit=max_candidate_limit,
            boundary=boundary,
            boundary_policy=boundary_policy,
            boundary_min_coverage=boundary_min_coverage,
            output_geometry=output_geometry,
            geometry_crs=geometry_crs,
            geometry_format=geometry_format,
        )

    def line_to_cells(
        self,
        domain_code: str,
        geometry: Any,
        source_crs: str,
        level: int,
        *,
        max_candidate_limit: int = 100_000,
        boundary_policy: BoundaryPredicate | str | None = None,
        boundary_min_coverage: float | None = None,
        output_geometry: bool = False,
        geometry_crs: str = "grid",
        geometry_format: str = "shapely",
    ) -> tuple[Any, ...]:
        """Convert a line to cell records with length ratios."""
        from .conversion import line_to_cells

        context = self._context(domain_code)
        boundary = self._boundary(context) if boundary_policy is not None else None
        return line_to_cells(
            context.grid,
            geometry,
            source_crs,
            level,
            max_candidate_limit=max_candidate_limit,
            boundary=boundary,
            boundary_policy=boundary_policy,
            boundary_min_coverage=boundary_min_coverage,
            output_geometry=output_geometry,
            geometry_crs=geometry_crs,
            geometry_format=geometry_format,
        )

    def describe(self, value: str, *, domain_code: str | None = None) -> IndexedCell:
        """Decode a full V2 URI or a bare GID with an explicit domain."""
        if not isinstance(value, str):
            raise ValidationError("cell value must be a V2 URI or bare GID string")
        if value.startswith("geosquare:"):
            parsed_domain, gid = parse_uri(value)
            if domain_code is not None and domain_code != parsed_domain:
                raise ValidationError("URI domain does not match domain_code")
            domain_code = parsed_domain
        else:
            if domain_code is None:
                raise ValidationError("domain_code is required when describing a bare GID")
            gid = value
        context = self._context(domain_code)
        return self._result(context, context.grid.canonical_from_gid(gid))

    def polyfill(
        self,
        domain_code: str,
        geometry: object,
        source_crs: str,
        level: int,
        *,
        coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
        min_coverage: float = 0.0,
        max_candidate_limit: int = 100_000,
        boundary_policy: BoundaryPredicate | str | None = None,
        boundary_min_coverage: float | None = None,
    ) -> tuple[tuple[str, float], ...]:
        """Run V2 polyfill with optional named country-boundary filtering."""
        context = self._context(domain_code)
        if boundary_policy is None:
            return polyfill(
                context.grid,
                geometry,
                source_crs,
                level,
                coverage_mode=coverage_mode,
                min_coverage=min_coverage,
                max_candidate_limit=max_candidate_limit,
            )
        return polyfill(
            context.grid,
            geometry,
            source_crs,
            level,
            coverage_mode=coverage_mode,
            min_coverage=min_coverage,
            max_candidate_limit=max_candidate_limit,
            boundary=self._boundary(context),
            boundary_predicate=boundary_policy,
            boundary_min_coverage=boundary_min_coverage,
        )

    def neighbourhood(
        self,
        value: str,
        k: int,
        *,
        domain_code: str | None = None,
        kind: str = "ring",
        boundary_policy: BoundaryPredicate | str | None = None,
        boundary_min_coverage: float | None = None,
    ) -> tuple[IndexedCell, ...]:
        """Return ring or disk cells around a V2 URI or domain-qualified bare GID."""
        source = self.describe(value, domain_code=domain_code)
        context = self._context(source.cell.domain_code)
        if kind == "ring":
            cells = context.grid.k_ring(source.cell, k)
        elif kind == "disk":
            cells = context.grid.k_disk(source.cell, k)
        else:
            raise ValidationError("kind must be 'ring' or 'disk'")
        if boundary_policy is not None:
            cells = self._boundary(context).filter_cells(
                context.grid,
                cells,
                boundary_policy,
                min_coverage=boundary_min_coverage,
            )
        return tuple(self._result(context, cell, boundary_policy) for cell in cells)

    def distance(self, first: str, second: str) -> float:
        """Return same-level grid distance between two V2 URIs in metres."""
        first_result = self.describe(first)
        second_result = self.describe(second)
        if first_result.cell.domain_code != second_result.cell.domain_code:
            raise ValidationError("grid distance requires one domain")
        context = self._context(first_result.cell.domain_code)
        return context.grid.distance_m(first_result.cell, second_result.cell)

    def cell_neighbours(self, *args: Any, **kwargs: Any) -> tuple[IndexedCell, ...]:
        """Canonical name for :meth:`neighbourhood`."""
        return self.neighbourhood(*args, **kwargs)

    def cell_distance(self, first: str, second: str) -> float:
        """Canonical name for :meth:`distance`."""
        return self.distance(first, second)

    def table_to_cells(
        self,
        source: Any,
        domain_code: str,
        level: int,
        **kwargs: Any,
    ) -> Any:
        """Add V2 cell fields to a CSV, XLSX, Parquet, or DataFrame input."""
        from .table import table_to_cells

        return table_to_cells(source, self, domain_code, level, **kwargs)

    def aggregate_to_cells(self, frame: Any, **kwargs: Any) -> Any:
        """Aggregate a cell-assigned table with explicit value rules."""
        from .aggregation import aggregate_to_cells

        return aggregate_to_cells(frame, **kwargs)
