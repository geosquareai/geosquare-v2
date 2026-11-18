"""Explicit CRS transforms built from profile-owned operation pipelines."""

from __future__ import annotations

from typing import Any

from .errors import GeometryDependencyError, ValidationError
from .release import ReleaseProfile


def require_crs_released(profile: ReleaseProfile, *, allow_candidate: bool = False) -> None:
    """Reject profiles outside the normal CRS release gate.

    Candidate profiles require an explicit caller opt-in. Blocked profiles always fail.
    """
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("CRS release checks require a verified ReleaseProfile")
    if profile.support_status == "released":
        return
    if profile.support_status == "candidate" and allow_candidate:
        return
    if profile.support_status == "candidate":
        raise ValidationError(
            f"domain {profile.domain_code} CRS is a candidate; "
            "set allow_candidate_crs=True for provisional use"
        )
    raise ValidationError(
        f"domain {profile.domain_code} CRS status is {profile.support_status}; "
        "the domain has not passed the CRS release gate"
    )


def validate_wgs84_point(profile: ReleaseProfile, longitude: float, latitude: float) -> None:
    """Reject a point outside the datum operation's declared area of use."""
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("explicit CRS transforms require a verified ReleaseProfile")
    area = profile.datum_transformation.area_of_use
    if not area.west_lon <= longitude <= area.east_lon or not area.south_lat <= latitude <= area.north_lat:
        raise ValidationError(
            f"point ({longitude}, {latitude}) is outside the datum operation area of use"
        )


def wgs84_to_grid_transformer(profile: ReleaseProfile) -> Any:
    """Build the profile's complete WGS84 lon/lat to grid x/y transform.

    The operation comes only from ``datum_transformation.operation_pipeline``.
    This function never asks PROJ to choose a path between two CRS definitions.
    """
    if not isinstance(profile, ReleaseProfile):
        raise ValidationError("explicit CRS transforms require a verified ReleaseProfile")
    operation = profile.datum_transformation
    if operation is None:  # pragma: no cover - ReleaseProfile validates this
        raise ValidationError(
            f"domain {profile.domain_code} has no datum transformation contract"
        )
    try:
        from pyproj import Transformer
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise GeometryDependencyError(
            "CRS transforms require the 'geo' optional dependency group"
        ) from exc
    try:
        return Transformer.from_pipeline(operation.operation_pipeline)
    except Exception as exc:
        raise ValidationError(
            f"domain {profile.domain_code} has an invalid explicit operation pipeline"
        ) from exc
