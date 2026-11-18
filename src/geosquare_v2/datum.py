"""Explicit datum-operation metadata for verified GeoSquare profiles."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

from .errors import ValidationError


@dataclass(frozen=True, slots=True)
class AreaOfUse:
    """Longitude/latitude bounds where a datum rule is valid."""

    west_lon: float
    south_lat: float
    east_lon: float
    north_lat: float

    def __post_init__(self) -> None:
        values = {
            "west_lon": self.west_lon,
            "south_lat": self.south_lat,
            "east_lon": self.east_lon,
            "north_lat": self.north_lat,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValidationError(f"area_of_use.{name} must be a finite number")
            object.__setattr__(self, name, float(value))
        if not -180.0 <= self.west_lon <= 180.0 or not -180.0 <= self.east_lon <= 180.0:
            raise ValidationError("area_of_use longitude must be in [-180, 180]")
        if not -90.0 <= self.south_lat <= 90.0 or not -90.0 <= self.north_lat <= 90.0:
            raise ValidationError("area_of_use latitude must be in [-90, 90]")
        if self.east_lon <= self.west_lon or self.north_lat <= self.south_lat:
            raise ValidationError("area_of_use bounds must have positive width and height")

    @classmethod
    def from_mapping(cls, value: Any) -> "AreaOfUse":
        if not isinstance(value, Mapping):
            raise ValidationError("area_of_use must be an object")
        names = ("west_lon", "south_lat", "east_lon", "north_lat")
        if set(value) != set(names):
            raise ValidationError("area_of_use must contain only west_lon, south_lat, east_lon, and north_lat")
        try:
            return cls(*(value[name] for name in names))
        except (KeyError, TypeError) as exc:
            raise ValidationError("area_of_use has invalid bounds") from exc

    def as_mapping(self) -> dict[str, float]:
        return {
            "west_lon": self.west_lon,
            "south_lat": self.south_lat,
            "east_lon": self.east_lon,
            "north_lat": self.north_lat,
        }


@dataclass(frozen=True, slots=True)
class DatumTransformation:
    """A complete, explicit WGS84-lon/lat to grid-x/y operation."""

    source_crs: str
    axis_order: str
    mode: str
    operation_id: str | None
    operation_pipeline: str
    operation_source: str
    area_of_use: AreaOfUse
    stated_accuracy_m: float
    reference_epoch: float | None = None

    def __post_init__(self) -> None:
        if self.source_crs != "EPSG:4326":
            raise ValidationError("datum_transformation.source_crs must be EPSG:4326")
        if self.axis_order != "longitude_latitude":
            raise ValidationError(
                "datum_transformation.axis_order must be longitude_latitude"
            )
        if self.mode not in {"none", "explicit_operation"}:
            raise ValidationError("datum_transformation.mode must be none or explicit_operation")
        if self.mode == "none" and self.operation_id is not None:
            raise ValidationError("datum_transformation.operation_id must be null when mode is none")
        if not isinstance(self.operation_pipeline, str) or not self.operation_pipeline.strip():
            raise ValidationError("datum_transformation.operation_pipeline must be non-empty")
        if not isinstance(self.operation_source, str) or not self.operation_source.strip():
            raise ValidationError("datum_transformation.operation_source must be non-empty")
        if self.operation_id is not None and (
            not isinstance(self.operation_id, str) or not self.operation_id.strip()
        ):
            raise ValidationError("datum_transformation.operation_id must be non-empty when provided")
        accuracy = self.stated_accuracy_m
        if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)) or not math.isfinite(accuracy):
            raise ValidationError("datum_transformation.stated_accuracy_m must be a finite number")
        if accuracy < 0:
            raise ValidationError("datum_transformation.stated_accuracy_m must be non-negative")
        object.__setattr__(self, "stated_accuracy_m", float(accuracy))
        if self.reference_epoch is not None:
            epoch = self.reference_epoch
            if isinstance(epoch, bool) or not isinstance(epoch, (int, float)) or not math.isfinite(epoch):
                raise ValidationError("datum_transformation.reference_epoch must be a finite number")
            object.__setattr__(self, "reference_epoch", float(epoch))

    @classmethod
    def from_mapping(cls, value: Any) -> "DatumTransformation":
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValidationError("datum_transformation must be an object")
        required = {
            "source_crs",
            "axis_order",
            "mode",
            "operation_id",
            "operation_pipeline",
            "operation_source",
            "area_of_use",
            "stated_accuracy_m",
            "reference_epoch",
        }
        if set(value) != required:
            missing = sorted(required - set(value))
            extra = sorted(set(value) - required)
            detail = []
            if missing:
                detail.append(f"missing {', '.join(missing)}")
            if extra:
                detail.append(f"unknown {', '.join(extra)}")
            raise ValidationError("invalid datum_transformation fields: " + "; ".join(detail))
        return cls(
            source_crs=value["source_crs"],
            axis_order=value["axis_order"],
            mode=value["mode"],
            operation_id=value["operation_id"],
            operation_pipeline=value["operation_pipeline"],
            operation_source=value["operation_source"],
            area_of_use=AreaOfUse.from_mapping(value["area_of_use"]),
            stated_accuracy_m=value["stated_accuracy_m"],
            reference_epoch=value["reference_epoch"],
        )

    def as_mapping(self) -> dict[str, Any]:
        return {
            "source_crs": self.source_crs,
            "axis_order": self.axis_order,
            "mode": self.mode,
            "operation_id": self.operation_id,
            "operation_pipeline": self.operation_pipeline,
            "operation_source": self.operation_source,
            "area_of_use": self.area_of_use.as_mapping(),
            "stated_accuracy_m": self.stated_accuracy_m,
            "reference_epoch": self.reference_epoch,
        }
