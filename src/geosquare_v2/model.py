"""Immutable V2 domain, cell, and projected-bounds value objects."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .errors import ValidationError


def _validate_finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{name} must be a finite number; received {value!r}")
    return float(value)


@dataclass(frozen=True, slots=True)
class ProjectedBounds:
    """Axis-aligned bounds in the domain grid CRS, ordered west/south/east/north."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        min_x = _validate_finite_number(self.min_x, "min_x")
        min_y = _validate_finite_number(self.min_y, "min_y")
        max_x = _validate_finite_number(self.max_x, "max_x")
        max_y = _validate_finite_number(self.max_y, "max_y")
        if max_x <= min_x or max_y <= min_y:
            raise ValidationError("Projected bounds must have positive width and height")
        object.__setattr__(self, "min_x", min_x)
        object.__setattr__(self, "min_y", min_y)
        object.__setattr__(self, "max_x", max_x)
        object.__setattr__(self, "max_y", max_y)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.min_x + self.max_x) / 2, (self.min_y + self.max_y) / 2)

    def ring(self) -> tuple[tuple[float, float], ...]:
        """Return the closed projected square ring for geometry adapters."""
        return (
            (self.min_x, self.min_y),
            (self.min_x, self.max_y),
            (self.max_x, self.max_y),
            (self.max_x, self.min_y),
            (self.min_x, self.min_y),
        )


@dataclass(frozen=True, slots=True)
class DomainProfile:
    """Immutable country-domain configuration used by the V2 core.

    CRS definitions are metadata in this dependency-free reference layer. Callers that
    need geographic transforms should supply a compatible transformer to ``GeosquareGrid``.
    """

    domain_id: int
    domain_code: str
    name: str
    origin_x_m: float
    origin_y_m: float
    root_side_m: float = 50_000_000.0
    reference_epoch: float | None = None
    grid_crs: str | None = None
    equal_area_crs: str | None = None

    def __post_init__(self) -> None:
        if type(self.domain_id) is not int or not 1 <= self.domain_id <= 511:
            raise ValidationError("domain_id must be an integer in [1, 511]")
        if not isinstance(self.domain_code, str) or not self.domain_code.isascii() or not self.domain_code.isupper():
            raise ValidationError("domain_code must be a non-empty uppercase ASCII string")
        if not 1 <= len(self.domain_code) <= 16:
            raise ValidationError("domain_code length must be in [1, 16]")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("name must be a non-empty string")
        object.__setattr__(self, "origin_x_m", _validate_finite_number(self.origin_x_m, "origin_x_m"))
        object.__setattr__(self, "origin_y_m", _validate_finite_number(self.origin_y_m, "origin_y_m"))
        side = _validate_finite_number(self.root_side_m, "root_side_m")
        if side != 50_000_000.0:
            raise ValidationError("V2 root_side_m must be exactly 50_000_000.0")
        object.__setattr__(self, "root_side_m", side)
        if self.reference_epoch is not None:
            object.__setattr__(
                self,
                "reference_epoch",
                _validate_finite_number(self.reference_epoch, "reference_epoch"),
            )

    @property
    def root_bounds(self) -> ProjectedBounds:
        return ProjectedBounds(
            self.origin_x_m,
            self.origin_y_m,
            self.origin_x_m + self.root_side_m,
            self.origin_y_m + self.root_side_m,
        )


@dataclass(frozen=True, slots=True)
class CanonicalCell:
    """The durable V2 cell identity: domain, level, and Cartesian indices."""

    domain_code: str
    level: int
    x_idx: int
    y_idx: int

    def __post_init__(self) -> None:
        if not isinstance(self.domain_code, str) or not self.domain_code:
            raise ValidationError("domain_code must be a non-empty string")
        if type(self.level) is not int:
            raise ValidationError("level must be an integer")
        if type(self.x_idx) is not int or type(self.y_idx) is not int:
            raise ValidationError("cell indices must be integers")
