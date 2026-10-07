"""Profile-driven projected-grid operations for Geosquare V2."""

from __future__ import annotations

import math
from typing import Protocol

from .codec import (
    MAX_LEVEL,
    SUBDIVISIONS,
    canonical_to_gid,
    cell_side_m,
    gid_to_canonical,
    side_cell_count,
    validate_indices,
    validate_level,
)
from .errors import OutOfDomainError, ValidationError
from .model import CanonicalCell, DomainProfile, ProjectedBounds
from .packing import pack_int64, unpack_int64


class CoordinateTransformer(Protocol):
    """Minimal PyProj-compatible transformer interface used by this core."""

    def transform(self, x: float, y: float) -> tuple[float, float]: ...


def _validate_coordinate(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{name} must be a finite number; received {value!r}")
    return float(value)


class GeosquareGrid:
    """V2 grid operations for exactly one immutable country-domain profile."""

    def __init__(self, profile: DomainProfile) -> None:
        if not isinstance(profile, DomainProfile):
            raise ValidationError("profile must be a DomainProfile")
        self.profile = profile

    def canonical_from_projected(self, x_m: float, y_m: float, level: int) -> CanonicalCell:
        """Map grid-CRS metre coordinates to the canonical cell identity."""
        x = _validate_coordinate(x_m, "x_m")
        y = _validate_coordinate(y_m, "y_m")
        validate_level(level)
        root = self.profile.root_bounds
        if not (root.min_x <= x <= root.max_x and root.min_y <= y <= root.max_y):
            raise OutOfDomainError(f"({x}, {y}) is outside the {self.profile.domain_code} root square")
        if level == 0:
            return CanonicalCell(self.profile.domain_code, 0, 0, 0)

        count = side_cell_count(level)
        side = self.profile.root_side_m / count
        x_idx = count - 1 if x == root.max_x else math.floor((x - root.min_x) / side)
        y_idx = count - 1 if y == root.max_y else math.floor((y - root.min_y) / side)
        return CanonicalCell(self.profile.domain_code, level, int(x_idx), int(y_idx))

    def canonical_from_lonlat(
        self,
        longitude: float,
        latitude: float,
        level: int,
        transformer: CoordinateTransformer,
    ) -> CanonicalCell:
        """Transform lon/lat via a caller-supplied ``always_xy`` transformer and index it."""
        lon = _validate_coordinate(longitude, "longitude")
        lat = _validate_coordinate(latitude, "latitude")
        if not hasattr(transformer, "transform"):
            raise ValidationError("transformer must provide transform(longitude, latitude)")
        x_m, y_m = transformer.transform(lon, lat)
        return self.canonical_from_projected(x_m, y_m, level)

    def gid_from_projected(self, x_m: float, y_m: float, level: int) -> str:
        cell = self.canonical_from_projected(x_m, y_m, level)
        return canonical_to_gid(cell.level, cell.x_idx, cell.y_idx)

    def gid_from_lonlat(
        self,
        longitude: float,
        latitude: float,
        level: int,
        transformer: CoordinateTransformer,
    ) -> str:
        cell = self.canonical_from_lonlat(longitude, latitude, level, transformer)
        return canonical_to_gid(cell.level, cell.x_idx, cell.y_idx)

    def canonical_from_gid(self, gid: str) -> CanonicalCell:
        return gid_to_canonical(self.profile.domain_code, gid)

    def gid_from_canonical(self, cell: CanonicalCell) -> str:
        self._assert_domain(cell)
        validate_indices(cell.level, cell.x_idx, cell.y_idx)
        return canonical_to_gid(cell.level, cell.x_idx, cell.y_idx)

    def uri(self, cell_or_gid: CanonicalCell | str) -> str:
        gid = self.gid_from_canonical(cell_or_gid) if isinstance(cell_or_gid, CanonicalCell) else cell_or_gid
        self.canonical_from_gid(gid)
        return f"geosquare:v2:{self.profile.domain_code}:{gid}"

    def projected_bounds(self, cell_or_gid: CanonicalCell | str) -> ProjectedBounds:
        cell = self._as_cell(cell_or_gid)
        side = self.profile.root_side_m / side_cell_count(cell.level)
        return ProjectedBounds(
            self.profile.origin_x_m + cell.x_idx * side,
            self.profile.origin_y_m + cell.y_idx * side,
            self.profile.origin_x_m + (cell.x_idx + 1) * side,
            self.profile.origin_y_m + (cell.y_idx + 1) * side,
        )

    def parent(self, cell_or_gid: CanonicalCell | str) -> CanonicalCell:
        cell = self._as_cell(cell_or_gid)
        if cell.level == 0:
            raise ValidationError("the level-0 root has no parent")
        return CanonicalCell(
            self.profile.domain_code,
            cell.level - 1,
            cell.x_idx // SUBDIVISIONS[cell.level - 1],
            cell.y_idx // SUBDIVISIONS[cell.level - 1],
        )

    def children(self, cell_or_gid: CanonicalCell | str) -> tuple[CanonicalCell, ...]:
        cell = self._as_cell(cell_or_gid)
        if cell.level == MAX_LEVEL:
            raise ValidationError(f"level {MAX_LEVEL} has no children")
        step = SUBDIVISIONS[cell.level]
        return tuple(
            CanonicalCell(self.profile.domain_code, cell.level + 1, cell.x_idx * step + dx, cell.y_idx * step + dy)
            for dy in range(step)
            for dx in range(step)
        )

    def neighbor(self, cell_or_gid: CanonicalCell | str, dx: int, dy: int) -> CanonicalCell | None:
        cell = self._as_cell(cell_or_gid)
        if type(dx) is not int or type(dy) is not int:
            raise ValidationError("neighbour offsets must be integers")
        count = side_cell_count(cell.level)
        x_idx, y_idx = cell.x_idx + dx, cell.y_idx + dy
        if not (0 <= x_idx < count and 0 <= y_idx < count):
            return None
        return CanonicalCell(self.profile.domain_code, cell.level, x_idx, y_idx)

    def k_disk(self, cell_or_gid: CanonicalCell | str, k: int) -> tuple[CanonicalCell, ...]:
        cell = self._as_cell(cell_or_gid)
        if type(k) is not int or k < 0:
            raise ValidationError("k must be a non-negative integer")
        return tuple(
            neighbour
            for dy in range(-k, k + 1)
            for dx in range(-k, k + 1)
            if (neighbour := self.neighbor(cell, dx, dy)) is not None
        )

    def k_ring(self, cell_or_gid: CanonicalCell | str, k: int) -> tuple[CanonicalCell, ...]:
        cell = self._as_cell(cell_or_gid)
        if type(k) is not int or k < 0:
            raise ValidationError("k must be a non-negative integer")
        if k == 0:
            return (cell,)
        return tuple(
            neighbour
            for dy in range(-k, k + 1)
            for dx in range(-k, k + 1)
            if max(abs(dx), abs(dy)) == k
            if (neighbour := self.neighbor(cell, dx, dy)) is not None
        )

    def distance_m(self, first: CanonicalCell | str, second: CanonicalCell | str) -> float:
        a, b = self._as_cell(first), self._as_cell(second)
        if a.level != b.level:
            raise ValidationError("grid distance requires cells at the same level")
        side = cell_side_m(a.level)
        return math.hypot(b.x_idx - a.x_idx, b.y_idx - a.y_idx) * side

    def pack(self, cell_or_gid: CanonicalCell | str) -> int:
        cell = self._as_cell(cell_or_gid)
        return pack_int64(self.profile.domain_id, cell.level, cell.x_idx, cell.y_idx)

    def unpack(self, value: int) -> CanonicalCell:
        domain_id, level, x_idx, y_idx = unpack_int64(value)
        if domain_id != self.profile.domain_id:
            raise ValidationError(
                f"packed value domain {domain_id} does not match {self.profile.domain_code} ({self.profile.domain_id})"
            )
        return CanonicalCell(self.profile.domain_code, level, x_idx, y_idx)

    def _as_cell(self, cell_or_gid: CanonicalCell | str) -> CanonicalCell:
        if isinstance(cell_or_gid, str):
            return self.canonical_from_gid(cell_or_gid)
        if not isinstance(cell_or_gid, CanonicalCell):
            raise ValidationError("expected a CanonicalCell or bare GID")
        self._assert_domain(cell_or_gid)
        validate_indices(cell_or_gid.level, cell_or_gid.x_idx, cell_or_gid.y_idx)
        return cell_or_gid

    def _assert_domain(self, cell: CanonicalCell) -> None:
        if cell.domain_code != self.profile.domain_code:
            raise ValidationError(
                f"cell domain {cell.domain_code!r} does not match grid domain {self.profile.domain_code!r}"
            )
