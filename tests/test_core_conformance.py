"""Scalar conformance tests for the V2 canonical grid contract."""

from __future__ import annotations

import math

import pytest

from geosquare_v2.codec import (
    BASE_2_MATRIX,
    BASE_5_MATRIX,
    MAX_LEVEL,
    SUBDIVISIONS,
    canonical_to_gid,
    cell_side_m,
    gid_to_canonical,
    gid_to_indices,
    side_cell_count,
)
from geosquare_v2.errors import InvalidGIDError, InvalidPackedIDError, OutOfDomainError, ValidationError
from geosquare_v2.geometry import projected_cell_geometry
from geosquare_v2.model import CanonicalCell
from geosquare_v2.packing import pack_int64, unpack_int64


def _valid_characters(step: int) -> tuple[str, ...]:
    matrix = BASE_5_MATRIX if step == 5 else BASE_2_MATRIX
    return tuple(character for row in matrix for character in row)


def _representative_indices(level: int) -> tuple[tuple[int, int], ...]:
    count = side_cell_count(level)
    candidates = (
        (0, 0),
        (count - 1, count - 1),
        (count // 2, count // 3),
        (count // 3, count // 2),
    )
    return tuple(dict.fromkeys(candidates))


def test_resolution_sequence_matches_product_contract():
    expected_edges = (
        50_000_000,
        10_000_000,
        5_000_000,
        1_000_000,
        500_000,
        100_000,
        50_000,
        10_000,
        5_000,
        1_000,
        500,
        100,
        50,
        10,
        5,
    )

    assert MAX_LEVEL == 14
    assert len(SUBDIVISIONS) == MAX_LEVEL
    assert tuple(cell_side_m(level) for level in range(MAX_LEVEL + 1)) == expected_edges


@pytest.mark.parametrize("level", range(MAX_LEVEL + 1))
def test_representative_canonical_gid_round_trip(level):
    for x_idx, y_idx in _representative_indices(level):
        gid = canonical_to_gid(level, x_idx, y_idx)

        assert len(gid) == level
        assert gid_to_indices(gid) == (level, x_idx, y_idx)
        assert gid_to_canonical("TS", gid) == CanonicalCell("TS", level, x_idx, y_idx)


@pytest.mark.parametrize("level,step", tuple(enumerate(SUBDIVISIONS, start=1)))
def test_every_character_is_valid_at_its_level(level, step):
    prefix = "".join(_valid_characters(previous_step)[0] for previous_step in SUBDIVISIONS[: level - 1])

    for character in _valid_characters(step):
        gid = prefix + character
        decoded_level, x_idx, y_idx = gid_to_indices(gid)
        assert decoded_level == level
        assert canonical_to_gid(decoded_level, x_idx, y_idx) == gid


def test_level_specific_character_validation_is_strict():
    # "6" is valid in a 5x5 step, but not in the second 2x2 step.
    with pytest.raises(InvalidGIDError):
        gid_to_indices("26")

    with pytest.raises(InvalidGIDError):
        gid_to_indices("2" * (MAX_LEVEL + 1))

    with pytest.raises(InvalidGIDError):
        gid_to_indices(None)  # type: ignore[arg-type]


def test_projected_root_edges_use_closed_outer_bounds(grid):
    root = grid.profile.root_bounds
    level = 4
    count = side_cell_count(level)
    side = cell_side_m(level)

    southwest = grid.canonical_from_projected(root.min_x, root.min_y, level)
    northeast = grid.canonical_from_projected(root.max_x, root.max_y, level)
    assert (southwest.x_idx, southwest.y_idx) == (0, 0)
    assert (northeast.x_idx, northeast.y_idx) == (count - 1, count - 1)

    boundary_x = root.min_x + side
    on_boundary = grid.canonical_from_projected(boundary_x, root.min_y, level)
    just_before = grid.canonical_from_projected(math.nextafter(boundary_x, root.min_x), root.min_y, level)
    assert on_boundary.x_idx == 1
    assert just_before.x_idx == 0

    with pytest.raises(OutOfDomainError):
        grid.canonical_from_projected(root.min_x - 1, root.min_y, level)
    with pytest.raises(OutOfDomainError):
        grid.canonical_from_projected(root.max_x + 1, root.max_y, level)


def test_level_zero_maps_every_valid_root_coordinate_to_the_root(grid):
    root = grid.profile.root_bounds
    assert grid.canonical_from_projected(root.min_x, root.min_y, 0) == CanonicalCell("TS", 0, 0, 0)
    assert grid.canonical_from_projected(root.max_x, root.max_y, 0) == CanonicalCell("TS", 0, 0, 0)


@pytest.mark.parametrize("level", range(MAX_LEVEL))
def test_parent_and_children_are_exact_inverses(grid, level):
    count = side_cell_count(level)
    parent = CanonicalCell("TS", level, min(count - 1, count // 2), min(count - 1, count // 3))
    children = grid.children(parent)
    expected_child_count = SUBDIVISIONS[level] ** 2

    assert len(children) == expected_child_count
    assert set(grid.parent(child) for child in children) == {parent}
    assert {grid.gid_from_canonical(child)[:-1] for child in children} == {grid.gid_from_canonical(parent)}


def test_root_has_no_parent_and_leaf_has_no_children(grid):
    root = CanonicalCell("TS", 0, 0, 0)
    leaf = CanonicalCell("TS", MAX_LEVEL, 0, 0)

    with pytest.raises(ValidationError):
        grid.parent(root)
    with pytest.raises(ValidationError):
        grid.children(leaf)


@pytest.mark.parametrize("level", range(MAX_LEVEL + 1))
def test_packed_int64_round_trip_matches_canonical_identity(grid, level):
    for x_idx, y_idx in _representative_indices(level):
        cell = CanonicalCell("TS", level, x_idx, y_idx)
        packed = grid.pack(cell)

        assert 0 <= packed < 2**63
        assert unpack_int64(packed) == (7, level, x_idx, y_idx)
        assert grid.unpack(packed) == cell
        assert pack_int64(7, level, x_idx, y_idx) == packed


def test_packed_int64_rejects_invalid_values():
    with pytest.raises(ValidationError):
        pack_int64(0, 0, 0, 0)
    with pytest.raises(InvalidPackedIDError):
        unpack_int64(0)  # domain ID zero
    with pytest.raises(InvalidPackedIDError):
        unpack_int64(1)  # reserved bit one
    with pytest.raises(InvalidPackedIDError):
        unpack_int64(2**63)  # signed bit one
    with pytest.raises(InvalidPackedIDError):
        unpack_int64((1 << 54) | (15 << 50))  # level above V2 maximum
    with pytest.raises(InvalidPackedIDError):
        unpack_int64((1 << 54) | (1 << 1))  # unused root path bit
    with pytest.raises(InvalidPackedIDError):
        unpack_int64((1 << 54) | (1 << 50) | (25 << 1))  # invalid 5x5 child code


def test_neighbours_rings_and_disks_use_integer_offsets(grid):
    center = CanonicalCell("TS", 3, 10, 10)
    assert grid.neighbor(center, 1, -1) == CanonicalCell("TS", 3, 11, 9)
    assert grid.neighbor(center, 0, 0) == center
    assert grid.neighbor(CanonicalCell("TS", 3, 0, 0), -1, 0) is None

    assert grid.k_ring(center, 0) == (center,)
    assert len(grid.k_ring(center, 1)) == 8
    assert len(grid.k_ring(center, 2)) == 16
    assert len(grid.k_disk(center, 0)) == 1
    assert len(grid.k_disk(center, 1)) == 9
    assert len(grid.k_disk(center, 2)) == 25

    corner = CanonicalCell("TS", 3, 0, 0)
    assert len(grid.k_ring(corner, 1)) == 3
    assert len(grid.k_disk(corner, 1)) == 4


def test_neighbourhood_inputs_must_be_integer_values(grid):
    cell = CanonicalCell("TS", 3, 10, 10)
    with pytest.raises(ValidationError):
        grid.neighbor(cell, True, 0)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        grid.k_ring(cell, -1)
    with pytest.raises(ValidationError):
        grid.k_disk(cell, 1.5)  # type: ignore[arg-type]


def test_same_level_grid_distance_is_projected_euclidean_distance(grid):
    first = CanonicalCell("TS", 9, 100, 200)
    second = CanonicalCell("TS", 9, 103, 204)
    expected = math.hypot(3, 4) * cell_side_m(9)

    assert grid.distance_m(first, first) == 0
    assert grid.distance_m(first, second) == pytest.approx(expected)

    with pytest.raises(ValidationError):
        grid.distance_m(first, CanonicalCell("TS", 10, 200, 400))


def test_projected_bounds_and_geometry_are_exact_squares(grid):
    cell = CanonicalCell("TS", 6, 20, 30)
    bounds = grid.projected_bounds(cell)
    geometry = projected_cell_geometry(grid, cell)

    assert bounds.width == pytest.approx(cell_side_m(cell.level))
    assert bounds.height == pytest.approx(cell_side_m(cell.level))
    assert bounds.width == bounds.height
    assert geometry.bounds == (bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)
    assert geometry.area == pytest.approx(bounds.width * bounds.height)
    assert tuple(geometry.exterior.coords) == bounds.ring()


def test_grid_rejects_non_finite_projected_coordinates(grid):
    with pytest.raises(ValidationError):
        grid.canonical_from_projected(float("nan"), 0, 4)
    with pytest.raises(ValidationError):
        grid.canonical_from_projected(0, float("inf"), 4)
