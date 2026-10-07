"""Lossless non-negative signed Int64 packing for V2 canonical cells."""

from __future__ import annotations

from .codec import SUBDIVISIONS, validate_indices, validate_level
from .errors import InvalidPackedIDError, ValidationError

_PATH_MASK = (1 << 49) - 1
_SIGNED_INT64_LIMIT = 1 << 63


def pack_int64(domain_id: int, level: int, x_idx: int, y_idx: int) -> int:
    """Pack a canonical identity into the normative non-negative signed Int64."""
    if type(domain_id) is not int or not 1 <= domain_id <= 511:
        raise ValidationError("domain_id must be an integer in [1, 511]")
    validate_indices(level, x_idx, y_idx)

    codes: list[int] = []
    x, y = x_idx, y_idx
    for step in reversed(SUBDIVISIONS[:level]):
        codes.append((y % step) * step + (x % step))
        x //= step
        y //= step

    path_bits = 0
    for step, code in zip(SUBDIVISIONS[:level], reversed(codes)):
        path_bits = (path_bits << (5 if step == 5 else 2)) | code
    return (domain_id << 54) | (level << 50) | (path_bits << 1)


def unpack_int64(value: int) -> tuple[int, int, int, int]:
    """Decode ``value`` as ``(domain_id, level, x_idx, y_idx)``."""
    if type(value) is not int or not 0 <= value < _SIGNED_INT64_LIMIT:
        raise InvalidPackedIDError("packed value must be a non-negative signed Int64")
    if value & 1:
        raise InvalidPackedIDError("packed value has reserved bit 0 set")

    domain_id = (value >> 54) & 0x1FF
    level = (value >> 50) & 0x0F
    if not 1 <= domain_id <= 511:
        raise InvalidPackedIDError("packed value has invalid domain ID")
    try:
        validate_level(level)
    except ValidationError as exc:
        raise InvalidPackedIDError("packed value has invalid level") from exc

    path_field = (value >> 1) & _PATH_MASK
    path_width = sum(5 if step == 5 else 2 for step in SUBDIVISIONS[:level])
    if path_field >> path_width:
        raise InvalidPackedIDError("packed value has non-zero unused path bits")
    if level == 0:
        return domain_id, 0, 0, 0

    parts: list[tuple[int, int, int]] = []
    path = path_field
    for step in reversed(SUBDIVISIONS[:level]):
        width = 5 if step == 5 else 2
        code = path & ((1 << width) - 1)
        if code >= step * step:
            raise InvalidPackedIDError("packed value contains an invalid child code")
        row, column = divmod(code, step)
        parts.append((step, row, column))
        path >>= width

    x_idx = y_idx = 0
    for step, row, column in reversed(parts):
        x_idx = x_idx * step + column
        y_idx = y_idx * step + row
    return domain_id, level, x_idx, y_idx
