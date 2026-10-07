"""Optional Shapely/PyProj geometry adapters for exact V2 grid squares."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import GeometryDependencyError, ValidationError
from .grid import GeosquareGrid
from .model import CanonicalCell
from .release import ReleaseProfile

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry


def _require_geometry() -> tuple[object, object, object]:
    try:
        from pyproj import CRS, Transformer
        from shapely.geometry import Polygon
        from shapely.ops import transform
    except ImportError as exc:  # pragma: no cover - exercised without optional extra
        raise GeometryDependencyError(
            "geometry operations require the 'geo' optional dependency group"
        ) from exc
    return CRS, Transformer, (Polygon, transform)


def profile_grid_crs(profile: ReleaseProfile) -> str:
    """Return the verified grid CRS WKT2 from a registry-loaded profile."""
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("geometry operations require a verified ReleaseProfile")
    return profile.crs_wkt2


def profile_equal_area_crs(profile: ReleaseProfile) -> str:
    """Return the verified equal-area CRS WKT2 from a registry-loaded profile."""
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("equal-area coverage requires a verified ReleaseProfile")
    return profile.equal_area_crs_wkt2


def projected_cell_geometry(grid: GeosquareGrid, cell_or_gid: CanonicalCell | str) -> BaseGeometry:
    """Return the authoritative exact square in the profile's grid CRS."""
    _, _, geometry_tools = _require_geometry()
    polygon, _ = geometry_tools
    return polygon(grid.projected_bounds(cell_or_gid).ring())


def wgs84_cell_geometry(
    grid: GeosquareGrid,
    cell_or_gid: CanonicalCell | str,
    *,
    max_segment_length_m: float = 25_000.0,
) -> BaseGeometry:
    """Return a densified WGS84 polygon for display or geographic interchange.

    The authoritative shape remains the exact projected square. Densification occurs
    before reprojection so curved projected edges are represented in WGS84.
    """
    if isinstance(max_segment_length_m, bool) or not isinstance(max_segment_length_m, (int, float)):
        raise ValidationError("max_segment_length_m must be a positive finite number")
    if not 0 < float(max_segment_length_m) < float("inf"):
        raise ValidationError("max_segment_length_m must be a positive finite number")

    CRS, Transformer, geometry_tools = _require_geometry()
    _, transform = geometry_tools
    try:
        from shapely import segmentize
    except ImportError as exc:  # pragma: no cover - Shapely 2 is pinned by the extra
        raise GeometryDependencyError("wgs84 geometry requires Shapely 2.x") from exc

    projected = segmentize(projected_cell_geometry(grid, cell_or_gid), max_segment_length=float(max_segment_length_m))
    transformer = Transformer.from_crs(
        CRS.from_user_input(profile_grid_crs(grid.profile)),
        CRS.from_epsg(4326),
        always_xy=True,
    )
    return transform(transformer.transform, projected)
