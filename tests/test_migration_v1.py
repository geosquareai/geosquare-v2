from __future__ import annotations

import pytest

from geosquare_v2.errors import InvalidGIDError, ValidationError
from geosquare_v2.migration import LegacyV1Decoder, V1MigrationAdapter


class IdentityTransformer:
    def transform(self, x: float, y: float) -> tuple[float, float]:
        return x, y


def test_v1_decoder_preserves_legacy_2x2_character_rules():
    decoder = LegacyV1Decoder()
    cell = decoder.decode("H")

    assert cell.level == 1
    assert cell.gid == "H"
    assert cell.min_longitude < cell.max_longitude
    assert cell.min_latitude < cell.max_latitude
    assert cell.min_longitude < cell.representative_point[0] < cell.max_longitude
    assert cell.min_latitude < cell.representative_point[1] < cell.max_latitude

    # V1's second-level 2x2 alphabet is 2, 3, 7, 8. V2 uses a different alphabet.
    with pytest.raises(InvalidGIDError):
        decoder.decode("H6")


def test_point_migration_prefers_original_coordinates(grid):
    adapter = V1MigrationAdapter(grid, IdentityTransformer())

    record = adapter.migrate_point(
        source_gid="H",
        longitude=12.5,
        latitude=34.5,
        target_level=9,
    )

    assert record.source_gid == "H"
    assert record.method == "source_coordinates"
    assert record.representative_point == (12.5, 34.5)
    assert record.target_domain == "TS"
    assert record.target_level == 9
    assert record.target_uri.startswith("geosquare:v2:TS:")
    assert record.legacy_bounds is not None


def test_point_migration_uses_legacy_cell_centroid_when_coordinates_are_missing(grid):
    adapter = V1MigrationAdapter(grid, IdentityTransformer())

    record = adapter.migrate_point(source_gid="H", target_level=5)

    assert record.method == "v1_cell_centroid"
    assert record.representative_point is not None
    assert record.legacy_bounds is not None
    assert record.target_uri.startswith("geosquare:v2:TS:")


def test_point_migration_requires_coordinates_or_source_gid(grid):
    adapter = V1MigrationAdapter(grid, IdentityTransformer())

    with pytest.raises(ValidationError):
        adapter.migrate_point(target_level=5)
    with pytest.raises(ValidationError):
        adapter.migrate_point(source_gid="H", longitude=1.0, target_level=5)


def test_area_migration_can_expand_one_v1_cell_to_many_v2_cells(grid):
    adapter = V1MigrationAdapter(grid)

    records = adapter.migrate_area("H", target_level=3, max_candidate_limit=5_000)

    assert records
    assert all(record.source_gid == "H" for record in records)
    assert all(record.method == "v1_cell_geometry_polyfill" for record in records)
    assert all(record.target_level == 3 for record in records)
    assert all(record.coverage_mode == "GRID_PLANAR" for record in records)
    assert all(record.coverage_ratio is not None and 0 < record.coverage_ratio <= 1 for record in records)
    assert all(record.target_uri.startswith("geosquare:v2:TS:") for record in records)
