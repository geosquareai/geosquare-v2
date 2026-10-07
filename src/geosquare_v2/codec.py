"""Strict mixed-radix V2 canonical/GID codec."""

from __future__ import annotations

import math

from .errors import InvalidGIDError, ValidationError
from .model import CanonicalCell

ROOT_SIDE_M = 50_000_000.0
SUBDIVISIONS: tuple[int, ...] = (5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2)
MAX_LEVEL = len(SUBDIVISIONS)

BASE_5_MATRIX: tuple[tuple[str, ...], ...] = (
    ("2", "3", "4", "5", "6"),
    ("7", "8", "9", "C", "E"),
    ("F", "G", "H", "J", "L"),
    ("M", "N", "P", "Q", "R"),
    ("T", "V", "W", "X", "Y"),
)
BASE_2_MATRIX: tuple[tuple[str, ...], ...] = (("2", "3"), ("4", "5"))

_POSITION_BY_STEP: dict[int, dict[str, tuple[int, int]]] = {
    step: {
        char: (row, column)
        for row, chars in enumerate(matrix)
        for column, char in enumerate(chars)
    }
    for step, matrix in ((5, BASE_5_MATRIX), (2, BASE_2_MATRIX))
}


def validate_level(level: int) -> None:
    if type(level) is not int or not 0 <= level <= MAX_LEVEL:
        raise ValidationError(f"level must be an integer in [0, {MAX_LEVEL}]; received {level!r}")


def side_cell_count(level: int) -> int:
    """Return the number of cells along a root edge at ``level``."""
    validate_level(level)
    return math.prod(SUBDIVISIONS[:level]) if level else 1


def cell_side_m(level: int) -> float:
    """Return the exact grid-CRS edge length at ``level`` in metres."""
    return ROOT_SIDE_M / side_cell_count(level)


def validate_indices(level: int, x_idx: int, y_idx: int) -> None:
    validate_level(level)
    count = side_cell_count(level)
    if type(x_idx) is not int or not 0 <= x_idx < count:
        raise ValidationError(f"x_idx must be an integer in [0, {count - 1}]; received {x_idx!r}")
    if type(y_idx) is not int or not 0 <= y_idx < count:
        raise ValidationError(f"y_idx must be an integer in [0, {count - 1}]; received {y_idx!r}")


def canonical_to_gid(level: int, x_idx: int, y_idx: int) -> str:
    """Encode canonical Cartesian indices to a V2 bare GID."""
    validate_indices(level, x_idx, y_idx)
    chars: list[str] = []
    current_x, current_y = x_idx, y_idx
    for step in reversed(SUBDIVISIONS[:level]):
        column = current_x % step
        row = current_y % step
        matrix = BASE_5_MATRIX if step == 5 else BASE_2_MATRIX
        chars.append(matrix[row][column])
        current_x //= step
        current_y //= step
    return "".join(reversed(chars))


def gid_to_indices(gid: str) -> tuple[int, int, int]:
    """Decode a V2 bare GID into ``(level, x_idx, y_idx)``."""
    if type(gid) is not str or len(gid) > MAX_LEVEL:
        raise InvalidGIDError(f"GID must be a string of at most {MAX_LEVEL} characters")
    level = len(gid)
    x_idx = y_idx = 0
    for position, (step, char) in enumerate(zip(SUBDIVISIONS[:level], gid), start=1):
        try:
            row, column = _POSITION_BY_STEP[step][char]
        except KeyError as exc:
            raise InvalidGIDError(
                f"character {char!r} is invalid at level {position} (base {step})"
            ) from exc
        x_idx = x_idx * step + column
        y_idx = y_idx * step + row
    return level, x_idx, y_idx


def gid_to_canonical(domain_code: str, gid: str) -> CanonicalCell:
    """Decode a V2 bare GID within its explicit domain context."""
    level, x_idx, y_idx = gid_to_indices(gid)
    return CanonicalCell(domain_code, level, x_idx, y_idx)


def cell_to_gid(cell: CanonicalCell) -> str:
    """Encode a canonical cell to its V2 bare GID."""
    return canonical_to_gid(cell.level, cell.x_idx, cell.y_idx)
