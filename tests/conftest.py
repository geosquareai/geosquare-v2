from __future__ import annotations

import pytest
from pyproj import CRS

from geosquare_v2.grid import GeosquareGrid
from geosquare_v2.release import ReleaseProfile


@pytest.fixture(scope="session")
def profile() -> ReleaseProfile:
    return ReleaseProfile(
        domain_id=7,
        domain_code="TS",
        name="Test profile",
        origin_x_m=-25_000_000.0,
        origin_y_m=-25_000_000.0,
        reference_epoch=2000.0,
        grid_crs="EPSG:3857",
        equal_area_crs="EPSG:6933",
        profile_version="test-1",
        crs_authority="EPSG:3857",
        crs_wkt2=CRS.from_epsg(3857).to_wkt("WKT2_2019"),
        equal_area_crs_authority="EPSG:6933",
        equal_area_crs_wkt2=CRS.from_epsg(6933).to_wkt("WKT2_2019"),
        scale_error_max_pct=0.0,
        scale_error_method="test fixture",
        scale_error_evaluation_metadata="test fixture only",
        scale_metadata_sha256="0" * 64,
        boundary_source_crs="EPSG:4326",
        boundary_file="boundaries/test.geojson",
        boundary_sha256="1" * 64,
        boundary_source="test fixture",
    )


@pytest.fixture(scope="session")
def grid(profile: ReleaseProfile) -> GeosquareGrid:
    return GeosquareGrid(profile)
