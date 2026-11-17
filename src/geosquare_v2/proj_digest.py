"""Content digest for the PROJ database that pyproj bundles.

Wheels for one PROJ release can ship ``proj.db`` files whose bytes differ. For example,
the macOS and Linux builds of pyproj 3.7.2 (PROJ 9.5.1) hold the same tables and rows,
but their file hashes differ. This module hashes the rows instead, so one digest
verifies the database on every platform.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from functools import lru_cache
from pathlib import Path

from .errors import ArtifactHashMismatchError, ManifestValidationError

_HEX_DIGITS = frozenset("0123456789abcdef")


def proj_db_content_digest(path: str | Path) -> str:
    """Return the lowercase SHA-256 of the user tables in a SQLite file.

    Tables are read in name order. Each table becomes one JSON document holding its name,
    its column names and all rows sorted by every column. Page size, file layout and free
    pages do not change the result. The result is cached per file identity (path, inode,
    size, and timestamps), so repeated verification in one process costs nothing extra.
    """
    db_path = Path(path).resolve()
    stat = db_path.stat()
    identity = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    return _cached_digest(str(db_path), identity)


@lru_cache(maxsize=8)
def _cached_digest(db_path: str, identity: tuple[int, int, int, int, int]) -> str:
    del identity  # part of the cache key only
    connection = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
    try:
        digest = hashlib.sha256()
        table_names = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
            if not row[0].startswith("sqlite_")
        ]
        for table in table_names:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table)})")]
            order_by = ", ".join(_quote(column) for column in columns)
            rows = [
                [{"blob": value.hex()} if isinstance(value, bytes) else value for value in row]
                for row in connection.execute(f"SELECT * FROM {_quote(table)} ORDER BY {order_by}")
            ]
            document = {"table": table, "columns": columns, "rows": rows}
            digest.update(json.dumps(document, separators=(",", ":")).encode("utf-8") + b"\n")
        return digest.hexdigest()
    finally:
        connection.close()


def verify_proj_database(path: str | Path, expected_digest: str) -> None:
    """Raise unless the PROJ database at ``path`` has ``expected_digest``."""
    if not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(
        char not in _HEX_DIGITS for char in expected_digest
    ):
        raise ManifestValidationError("PROJ database digest must be a lowercase SHA-256 digest")
    try:
        actual_digest = proj_db_content_digest(path)
    except (OSError, sqlite3.Error) as exc:
        raise ArtifactHashMismatchError(f"cannot read PROJ database content: {path}") from exc
    if actual_digest != expected_digest:
        raise ArtifactHashMismatchError(f"PROJ database content digest mismatch: {path}")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
