"""Tests for the content digest that verifies the PROJ database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pyproj
import pytest

from geosquare_v2.errors import ArtifactHashMismatchError, ManifestValidationError
from geosquare_v2.proj_digest import proj_db_content_digest, verify_proj_database


def _make_db(path: Path, rows: list[tuple[str, int]], *, page_size: int = 4096, value_column: str = "value") -> Path:
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"PRAGMA page_size = {page_size}")
        connection.execute(f"CREATE TABLE item (name TEXT, {value_column} INTEGER, payload BLOB)")
        connection.executemany("INSERT INTO item VALUES (?, ?, ?)", [(name, value, b"\x00\x01") for name, value in rows])
        connection.commit()
    finally:
        connection.close()
    return path


ROWS = [("alpha", 1), ("beta", 2), ("gamma", 3)]


def test_same_rows_in_different_file_layout_share_one_digest(tmp_path: Path) -> None:
    small_pages = _make_db(tmp_path / "small.db", ROWS, page_size=4096)
    large_pages = _make_db(tmp_path / "large.db", ROWS, page_size=8192)

    assert small_pages.read_bytes() != large_pages.read_bytes()
    assert proj_db_content_digest(small_pages) == proj_db_content_digest(large_pages)


def test_row_order_of_insertion_does_not_change_digest(tmp_path: Path) -> None:
    forward = _make_db(tmp_path / "forward.db", ROWS)
    reverse = _make_db(tmp_path / "reverse.db", list(reversed(ROWS)))

    assert proj_db_content_digest(forward) == proj_db_content_digest(reverse)


def test_changed_value_changes_digest(tmp_path: Path) -> None:
    original = _make_db(tmp_path / "original.db", ROWS)
    changed = _make_db(tmp_path / "changed.db", [("alpha", 1), ("beta", 2), ("gamma", 4)])

    assert proj_db_content_digest(original) != proj_db_content_digest(changed)


def test_changed_column_name_changes_digest(tmp_path: Path) -> None:
    original = _make_db(tmp_path / "original.db", ROWS)
    renamed = _make_db(tmp_path / "renamed.db", ROWS, value_column="amount")

    assert proj_db_content_digest(original) != proj_db_content_digest(renamed)


def test_digest_is_lowercase_sha256_hex(tmp_path: Path) -> None:
    digest = proj_db_content_digest(_make_db(tmp_path / "item.db", ROWS))

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_verify_accepts_matching_digest(tmp_path: Path) -> None:
    db_path = _make_db(tmp_path / "item.db", ROWS)

    verify_proj_database(db_path, proj_db_content_digest(db_path))


def test_verify_rejects_different_content(tmp_path: Path) -> None:
    expected = proj_db_content_digest(_make_db(tmp_path / "original.db", ROWS))
    other = _make_db(tmp_path / "other.db", [("alpha", 9)])

    with pytest.raises(ArtifactHashMismatchError, match="content digest mismatch"):
        verify_proj_database(other, expected)


def test_verify_rejects_missing_file(tmp_path: Path) -> None:
    expected = proj_db_content_digest(_make_db(tmp_path / "item.db", ROWS))

    with pytest.raises(ArtifactHashMismatchError, match="cannot read PROJ database"):
        verify_proj_database(tmp_path / "missing.db", expected)


@pytest.mark.parametrize("bad_digest", ["", "ABC", "A" * 64, "g" * 64, None])
def test_verify_rejects_malformed_expected_digest(tmp_path: Path, bad_digest: object) -> None:
    db_path = _make_db(tmp_path / "item.db", ROWS)

    with pytest.raises(ManifestValidationError, match="lowercase SHA-256"):
        verify_proj_database(db_path, bad_digest)  # type: ignore[arg-type]


def test_bundled_proj_database_digest_is_stable() -> None:
    proj_db = Path(pyproj.datadir.get_data_dir()) / "proj.db"

    first = proj_db_content_digest(proj_db)

    assert first == proj_db_content_digest(proj_db)
    assert len(first) == 64
