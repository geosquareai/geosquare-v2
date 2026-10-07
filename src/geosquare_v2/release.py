"""Fully specified, verified domain profiles used by signed registry releases."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import ValidationError
from .model import DomainProfile, _validate_finite_number

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ReleaseProfile(DomainProfile):
    """A V2 profile that has passed signed-registry artifact verification."""

    profile_version: str = ""
    crs_authority: str = ""
    crs_wkt2: str = ""
    equal_area_crs_authority: str = ""
    equal_area_crs_wkt2: str = ""
    min_level: int = 0
    max_level: int = 14
    scale_error_max_pct: float = 0.0
    scale_error_method: str = ""
    scale_error_evaluation_metadata: str = ""
    scale_metadata_sha256: str = ""
    boundary_source_crs: str = ""
    boundary_file: str = ""
    boundary_sha256: str = ""
    boundary_source: str = ""

    def __post_init__(self) -> None:
        # NOTE: `super().__post_init__()` (zero-argument super) is intentionally avoided
        # here. `@dataclass(slots=True)` rebuilds the class object after the class body
        # executes, which can leave the implicit `__class__` closure cell used by
        # zero-arg `super()` stale on some Python versions (observed on CPython 3.13;
        # not reproducible on 3.14). Calling the parent method explicitly sidesteps that
        # closure entirely and works identically on every supported Python version.
        DomainProfile.__post_init__(self)
        non_empty = (
            "profile_version",
            "crs_authority",
            "crs_wkt2",
            "equal_area_crs_authority",
            "equal_area_crs_wkt2",
            "scale_error_method",
            "scale_error_evaluation_metadata",
            "boundary_source_crs",
            "boundary_file",
            "boundary_source",
        )
        for field_name in non_empty:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{field_name} must be a non-empty string")
        if type(self.min_level) is not int or self.min_level != 0:
            raise ValidationError("min_level must be 0")
        if type(self.max_level) is not int or self.max_level != 14:
            raise ValidationError("max_level must be 14")
        error_pct = _validate_finite_number(self.scale_error_max_pct, "scale_error_max_pct")
        if error_pct < 0:
            raise ValidationError("scale_error_max_pct must be non-negative")
        object.__setattr__(self, "scale_error_max_pct", error_pct)
        for field_name in ("scale_metadata_sha256", "boundary_sha256"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise ValidationError(f"{field_name} must be a lowercase SHA-256 digest")
