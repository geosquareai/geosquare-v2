"""Explicit V1-to-V2 migration helpers.

V1 and V2 are different coordinate and identifier systems. This module decodes the
legacy V1 value in isolation, then re-indexes a point or legacy cell geometry through a
V2 ``GeosquareGrid``. It never treats a V1 GID as a V2 GID.
"""

from __future__ import annotations

from dataclasses import dataclass

from .codec import validate_level
from .errors import GeometryDependencyError, InvalidGIDError, ValidationError
from .grid import CoordinateTransformer, GeosquareGrid
from .polyfill import CoverageMode, polyfill


V1_SUBDIVISIONS: tuple[int, ...] = (5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5)
V1_MAX_LEVEL = len(V1_SUBDIVISIONS)
V1_LON_RANGE = (-217.0, 232.157642055036)
V1_LAT_RANGE = (-216.0, 233.157642055036)
V1_BASE_5_MATRIX: tuple[tuple[str, ...], ...] = (
    ("2", "3", "4", "5", "6"),
    ("7", "8", "9", "C", "E"),
    ("F", "G", "H", "J", "L"),
    ("M", "N", "P", "Q", "R"),
    ("T", "V", "W", "X", "Y"),
)
# V1 used the upper-left 2x2 part of its 5x5 matrix. V2 uses a different 2x2 table.
V1_BASE_2_MATRIX: tuple[tuple[str, ...], ...] = (("2", "3"), ("7", "8"))
V1_POSITION_BY_STEP: dict[int, dict[str, tuple[int, int]]] = {
    step: {
        character: (row, column)
        for row, values in enumerate(matrix)
        for column, character in enumerate(values)
    }
    for step, matrix in ((5, V1_BASE_5_MATRIX), (2, V1_BASE_2_MATRIX))
}


@dataclass(frozen=True, slots=True)
class LegacyV1Cell:
    """A decoded V1 cell in the legacy longitude/latitude-like coordinate space."""

    gid: str
    level: int
    min_longitude: float
    min_latitude: float
    max_longitude: float
    max_latitude: float

    @property
    def representative_point(self) -> tuple[float, float]:
        return (
            (self.min_longitude + self.max_longitude) / 2,
            (self.min_latitude + self.max_latitude) / 2,
        )

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.min_longitude, self.min_latitude, self.max_longitude, self.max_latitude)


class LegacyV1Decoder:
    """Decode V1 GIDs without importing or changing the legacy package."""

    def decode(self, gid: str) -> LegacyV1Cell:
        if type(gid) is not str or not 1 <= len(gid) <= V1_MAX_LEVEL:
            raise InvalidGIDError(f"V1 GID must be a string of 1-{V1_MAX_LEVEL} characters")

        lon_min, lon_max = V1_LON_RANGE
        lat_min, lat_max = V1_LAT_RANGE
        for position, (step, character) in enumerate(zip(V1_SUBDIVISIONS[: len(gid)], gid), start=1):
            try:
                row, column = V1_POSITION_BY_STEP[step][character]
            except KeyError as exc:
                raise InvalidGIDError(
                    f"character {character!r} is invalid at V1 level {position} (base {step})"
                ) from exc
            width = (lon_max - lon_min) / step
            height = (lat_max - lat_min) / step
            lon_min += width * column
            lon_max = lon_min + width
            lat_min += height * row
            lat_max = lat_min + height

        return LegacyV1Cell(gid, len(gid), lon_min, lat_min, lon_max, lat_max)


@dataclass(frozen=True, slots=True)
class MigrationRecord:
    """One auditable source-to-target mapping produced by the adapter."""

    source_system: str
    source_version: str
    source_gid: str | None
    target_system: str
    target_version: str
    target_domain: str
    target_profile_version: str
    target_level: int
    target_uri: str
    method: str
    source_crs: str
    representative_point: tuple[float, float] | None = None
    legacy_bounds: tuple[float, float, float, float] | None = None
    coverage_mode: str | None = None
    min_coverage: float | None = None
    coverage_ratio: float | None = None


class V1MigrationAdapter:
    """Migrate V1 points or V1 cell areas into one V2 domain."""

    def __init__(
        self,
        grid: GeosquareGrid,
        transformer: CoordinateTransformer | None = None,
        *,
        decoder: LegacyV1Decoder | None = None,
    ) -> None:
        self.grid = grid
        self.transformer = transformer
        self.decoder = decoder or LegacyV1Decoder()

    @property
    def target_profile_version(self) -> str:
        return str(getattr(self.grid.profile, "profile_version", "") or "unversioned")

    def migrate_point(
        self,
        *,
        target_level: int,
        source_gid: str | None = None,
        longitude: float | None = None,
        latitude: float | None = None,
        transformer: CoordinateTransformer | None = None,
        source_crs: str = "OGC:CRS84",
    ) -> MigrationRecord:
        """Migrate a point using source coordinates or a V1 cell representative point.

        Source coordinates always take precedence when supplied. If coordinates are not
        available, the V1 cell centroid is used and recorded as an approximation.
        """
        validate_level(target_level)
        if (longitude is None) != (latitude is None):
            raise ValidationError("longitude and latitude must be supplied together")
        legacy_cell = self.decoder.decode(source_gid) if source_gid is not None else None

        if longitude is not None and latitude is not None:
            point = (float(longitude), float(latitude))
            method = "source_coordinates"
            legacy_bounds = legacy_cell.bounds if legacy_cell is not None else None
        elif legacy_cell is not None:
            point = legacy_cell.representative_point
            method = "v1_cell_centroid"
            legacy_bounds = legacy_cell.bounds
        else:
            raise ValidationError("provide source_gid or both longitude and latitude")

        active_transformer = transformer or self.transformer
        if active_transformer is None:
            raise ValidationError("a V2 coordinate transformer is required for point migration")
        cell = self.grid.canonical_from_lonlat(point[0], point[1], target_level, active_transformer)
        return MigrationRecord(
            source_system="geosquare",
            source_version="v1",
            source_gid=source_gid,
            target_system="geosquare",
            target_version="v2",
            target_domain=self.grid.profile.domain_code,
            target_profile_version=self.target_profile_version,
            target_level=target_level,
            target_uri=self.grid.uri(cell),
            method=method,
            source_crs=source_crs,
            representative_point=point,
            legacy_bounds=legacy_bounds,
        )

    def migrate_area(
        self,
        source_gid: str,
        *,
        target_level: int,
        coverage_mode: CoverageMode | str = CoverageMode.GRID_PLANAR,
        min_coverage: float = 0.0,
        max_candidate_limit: int = 100_000,
        source_crs: str = "OGC:CRS84",
    ) -> tuple[MigrationRecord, ...]:
        """Decode one V1 cell and reprocess its area through the V2 polyfill."""
        legacy_cell = self.decoder.decode(source_gid)
        try:
            from shapely.geometry import box
        except ImportError as exc:  # pragma: no cover - exercised without geo extra
            raise GeometryDependencyError(
                "V1 area migration requires the 'geo' optional dependency group"
            ) from exc

        geometry = box(*legacy_cell.bounds)
        coverage = polyfill(
            self.grid,
            geometry,
            source_crs,
            target_level,
            coverage_mode=coverage_mode,
            min_coverage=min_coverage,
            max_candidate_limit=max_candidate_limit,
        )
        mode = coverage_mode.value if isinstance(coverage_mode, CoverageMode) else str(coverage_mode)
        return tuple(
            MigrationRecord(
                source_system="geosquare",
                source_version="v1",
                source_gid=source_gid,
                target_system="geosquare",
                target_version="v2",
                target_domain=self.grid.profile.domain_code,
                target_profile_version=self.target_profile_version,
                target_level=target_level,
                target_uri=self.grid.uri(gid),
                method="v1_cell_geometry_polyfill",
                source_crs=source_crs,
                representative_point=legacy_cell.representative_point,
                legacy_bounds=legacy_cell.bounds,
                coverage_mode=mode,
                min_coverage=float(min_coverage),
                coverage_ratio=ratio,
            )
            for gid, ratio in coverage
        )
