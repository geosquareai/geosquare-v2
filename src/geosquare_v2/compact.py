"""Reference rules for the ``cell_compact_set`` dataset type.

A compact set is a set of V2 GIDs that may mix levels. The area it covers is
the union of its cells. Parent and child cells come from the codec, so this
module adds no grid rules of its own.
"""

from __future__ import annotations

from collections.abc import Iterable

from .codec import MAX_LEVEL, SUBDIVISIONS, canonical_to_gid, gid_to_indices, validate_level
from .errors import ValidationError


class CompactSetError(ValidationError):
    """A compact set row or set breaks a rule in the ``cell_compact_set`` contract."""


def parent_gid(gid: str) -> str | None:
    """Return the parent GID, or ``None`` for the level-0 root."""
    level, x_idx, y_idx = gid_to_indices(gid)
    if level == 0:
        return None
    step = SUBDIVISIONS[level - 1]
    return canonical_to_gid(level - 1, x_idx // step, y_idx // step)


def child_gids(gid: str) -> tuple[str, ...]:
    """Return the direct children of a GID, in row-major order."""
    level, x_idx, y_idx = gid_to_indices(gid)
    if level == MAX_LEVEL:
        raise CompactSetError(f"level {MAX_LEVEL} has no children")
    step = SUBDIVISIONS[level]
    return tuple(
        canonical_to_gid(level + 1, x_idx * step + dx, y_idx * step + dy)
        for dy in range(step)
        for dx in range(step)
    )


def _ancestors(gid: str) -> Iterable[str]:
    current = parent_gid(gid)
    while current is not None:
        yield current
        current = parent_gid(current)


def canonicalize(gids: Iterable[str]) -> tuple[str, ...]:
    """Return the canonical compact form of ``gids``, sorted.

    Descendants of a present ancestor are removed. Then every complete child
    group is replaced by its parent, from the deepest level up. The result is
    the antichain with no complete child group left.
    """
    present = set(gids)
    for gid in present:
        gid_to_indices(gid)
    kept = {gid for gid in present if not any(ancestor in present for ancestor in _ancestors(gid))}
    by_level: dict[int, set[str]] = {level: set() for level in range(MAX_LEVEL + 1)}
    for gid in kept:
        by_level[gid_to_indices(gid)[0]].add(gid)
    for level in range(MAX_LEVEL, 0, -1):
        for parent in {parent_gid(gid) for gid in by_level[level]}:
            children = child_gids(parent)
            if all(child in by_level[level] for child in children):
                by_level[level].difference_update(children)
                by_level[level - 1].add(parent)
    return tuple(sorted(gid for cells in by_level.values() for gid in cells))


def validate_compact_set(rows: Iterable[tuple[str, int]]) -> None:
    """Raise ``CompactSetError`` unless ``rows`` is a canonical compact set.

    Each row is ``(gid, level)``. The reader rejects; it does not canonicalize.
    """
    gids: set[str] = set()
    for gid, level in rows:
        decoded_level = gid_to_indices(gid)[0]
        if type(level) is not int or level != decoded_level:
            raise CompactSetError(f"level {level!r} does not match GID {gid!r} at level {decoded_level}")
        if gid in gids:
            raise CompactSetError(f"duplicate row for GID {gid!r}")
        gids.add(gid)
    for gid in gids:
        covering = next((ancestor for ancestor in _ancestors(gid) if ancestor in gids), None)
        if covering is not None:
            raise CompactSetError(f"GID {gid!r} is inside row {covering!r}")
    if canonicalize(gids) != tuple(sorted(gids)):
        raise CompactSetError("set is not canonical: a complete child group must be replaced by its parent")


def expand(gids: Iterable[str], level: int) -> frozenset[str]:
    """Return every level-``level`` descendant of the rows, de-duplicated.

    A target level below any row's level is an error, not a roll-up.
    """
    validate_level(level)
    cells: set[str] = set()
    for gid in gids:
        row_level = gid_to_indices(gid)[0]
        if level < row_level:
            raise CompactSetError(f"target level {level} is below row level {row_level} for GID {gid!r}")
        frontier = [gid]
        for _ in range(row_level, level):
            frontier = [child for cell in frontier for child in child_gids(cell)]
        cells.update(frontier)
    return frozenset(cells)


def contains(gids: Iterable[str], gid: str) -> bool:
    """Return whether ``gid`` is covered: stored exactly, or under a stored ancestor."""
    gid_to_indices(gid)
    members = set(gids)
    if gid in members:
        return True
    return any(ancestor in members for ancestor in _ancestors(gid))
