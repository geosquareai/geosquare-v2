from __future__ import annotations

from dataclasses import replace

import pytest

from geosquare_v2.crs import require_crs_released, validate_wgs84_point, wgs84_to_grid_transformer
from geosquare_v2.datum import AreaOfUse, DatumTransformation
from geosquare_v2.errors import ValidationError
from geosquare_v2.release import ReleaseProfile


def _operation(reference_epoch: float | None = None) -> dict[str, object]:
    return {
        "source_crs": "EPSG:4326",
        "axis_order": "longitude_latitude",
        "mode": "none",
        "operation_id": None,
        "operation_pipeline": (
            "+proj=pipeline +step +proj=merc +a=6378137 +b=6378137 "
            "+lon_0=0 +k=1 +x_0=0 +y_0=0 +units=m"
        ),
        "operation_source": "test fixture",
        "area_of_use": {
            "west_lon": -180.0,
            "south_lat": -85.0,
            "east_lon": 180.0,
            "north_lat": 85.0,
        },
        "stated_accuracy_m": 0.0,
        "reference_epoch": reference_epoch,
    }


def test_datum_transformation_requires_the_complete_contract():
    with pytest.raises(ValidationError, match="invalid datum_transformation fields"):
        DatumTransformation.from_mapping({"source_crs": "EPSG:4326"})


def test_area_of_use_rejects_reversed_bounds():
    with pytest.raises(ValidationError, match="positive width"):
        AreaOfUse(1, -1, 1, 1)


def test_release_profile_normalizes_datum_metadata(profile):
    assert isinstance(profile.datum_transformation, DatumTransformation)
    assert profile.datum_transformation.axis_order == "longitude_latitude"


def test_explicit_pipeline_is_used_for_wgs84_transform(profile):
    transformer = wgs84_to_grid_transformer(profile)

    x_m, y_m = transformer.transform(1.0, 1.0)

    assert x_m == pytest.approx(111_319.490793, abs=1e-6)
    assert y_m == pytest.approx(111_325.142866, abs=1e-6)


def test_release_profile_requires_datum_metadata(profile):
    values = {
        field_name: getattr(profile, field_name)
        for field_name in profile.__dataclass_fields__
    }
    values["datum_transformation"] = None

    with pytest.raises(ValidationError, match="datum_transformation is required"):
        ReleaseProfile(**values)


def test_point_outside_operation_area_is_rejected(profile):
    with pytest.raises(ValidationError, match="outside the datum operation area"):
        validate_wgs84_point(profile, 0.0, 86.0)


def test_unreleased_profile_fails_the_runtime_gate(profile):
    blocked = replace(profile, support_status="blocked")

    with pytest.raises(ValidationError, match="has not passed the CRS release gate"):
        require_crs_released(blocked)


def test_candidate_profile_requires_explicit_opt_in(profile):
    candidate = replace(profile, support_status="candidate")

    with pytest.raises(ValidationError, match="candidate"):
        require_crs_released(candidate)
    require_crs_released(candidate, allow_candidate=True)
