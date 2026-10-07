from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest
from shapely.geometry import box, mapping

from geosquare_v2.boundary import BoundaryPredicate
from geosquare_v2.errors import OutsideOperationalBoundaryError, ValidationError
from geosquare_v2.facade import GeosquareService, parse_uri
from geosquare_v2.registry import DomainRegistry


def test_service_indexes_points_and_returns_versioned_metadata(profile):
    service = GeosquareService(DomainRegistry([profile]))

    result = service.index_point("TS", 0.0, 0.0, level=9)

    assert result.cell.domain_code == "TS"
    assert result.cell.level == 9
    assert result.gid == result.uri.rsplit(":", 1)[-1]
    assert result.uri.startswith("geosquare:v2:TS:")
    assert result.cell_edge_m == pytest.approx(1_000.0)
    assert result.profile_version == "test-1"
    assert result.scale_error_max_pct == 0.0


def test_service_describes_uris_and_calculates_distance(profile):
    service = GeosquareService(DomainRegistry([profile]))
    first = service.index_point("TS", 0.0, 0.0, level=9)
    described = service.describe(first.uri)
    neighbours = service.neighbourhood(first.uri, 1)

    assert described == first
    assert len(neighbours) == 8
    assert min(service.distance(first.uri, neighbour.uri) for neighbour in neighbours) == pytest.approx(1_000.0)

    with pytest.raises(ValidationError):
        service.describe(first.gid)
    assert service.describe(first.gid, domain_code="TS") == first


def test_parse_uri_requires_the_v2_shape():
    assert parse_uri("geosquare:v2:TS:2G") == ("TS", "2G")
    assert parse_uri("geosquare:v2:TS:") == ("TS", "")

    with pytest.raises(ValidationError):
        parse_uri("TS:2G")


def test_service_applies_point_boundary_policy(tmp_path, profile):
    geometry = box(-1_000, -1_000, 1_000, 1_000)
    boundary_path = tmp_path / "test.geojson"
    content = json.dumps(mapping(geometry)).encode("utf-8")
    boundary_path.write_bytes(content)
    profile_with_boundary = replace(
        profile,
        boundary_file=boundary_path.name,
        boundary_sha256=hashlib.sha256(content).hexdigest(),
        boundary_source_crs=profile.crs_wkt2,
    )
    service = GeosquareService(
        DomainRegistry([profile_with_boundary]),
        boundary_root=tmp_path,
    )

    result = service.index_point(
        "TS",
        0.0,
        0.0,
        level=9,
        boundary_policy=BoundaryPredicate.COVERS_POINT,
    )
    assert result.boundary_policy == "COVERS_POINT"

    with pytest.raises(OutsideOperationalBoundaryError):
        service.index_point(
            "TS",
            1.0,
            1.0,
            level=9,
            boundary_policy=BoundaryPredicate.COVERS_POINT,
        )


def test_canonical_service_names_match_legacy_aliases(profile):
    service = GeosquareService(DomainRegistry([profile]))
    point = service.point_to_cell("TS", 0.0, 0.0, level=9)

    assert point == service.index_point("TS", 0.0, 0.0, level=9)
    assert service.cell_distance(point.uri, point.uri) == 0
    assert service.cell_neighbours(point.uri, 1) == service.neighbourhood(point.uri, 1)
