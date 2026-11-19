from __future__ import annotations

import math

import pytest

from geosquare_v2.crosswalk import validate_crosswalk
from geosquare_v2.errors import ValidationError


@pytest.fixture
def manifest() -> dict[str, object]:
    return {
        "format_version": "1.0",
        "spec_version": "2.0",
        "domain_code": "ID",
        "level": 2,
        "weight_kind": "luas",
        "source_description": "Batas desa",
        "created_at": "2026-11-19T10:00:00Z",
        "registry_version": "2.0.0",
    }


def rows() -> list[dict[str, object]]:
    return [
        {"sumber_id": "DESA-001", "gid": "22", "bobot": 0.5},
        {"sumber_id": "DESA-001", "gid": "23", "bobot": 0.3},
        {"sumber_id": "DESA-001", "gid": "24", "bobot": 0.2},
        {"sumber_id": "DESA-002", "gid": "25", "bobot": 1.0},
    ]


def assert_invalid(rows_to_check, manifest_to_check, text: str) -> None:
    with pytest.raises(ValidationError, match=text):
        validate_crosswalk(rows_to_check, manifest_to_check)


def test_valid_table_returns_summary(manifest):
    assert validate_crosswalk(rows(), manifest) == {"sources": 2, "rows": 4, "cells": 4}


def test_weights_must_sum_to_one(manifest):
    bad_rows = rows()
    bad_rows[0]["bobot"] = 0.6
    assert_invalid(bad_rows, manifest, "DESA-001.*sum")


@pytest.mark.parametrize("weight", [0, -0.1])
def test_weight_must_be_positive(manifest, weight):
    bad_rows = [{"sumber_id": "DESA-001", "gid": "22", "bobot": weight}]
    assert_invalid(bad_rows, manifest, "DESA-001.*bobot")


@pytest.mark.parametrize("weight", [math.nan, math.inf, -math.inf])
def test_weight_must_be_finite(manifest, weight):
    bad_rows = [{"sumber_id": "DESA-001", "gid": "22", "bobot": weight}]
    assert_invalid(bad_rows, manifest, "DESA-001.*finite")


def test_duplicate_pair_is_refused(manifest):
    bad_rows = rows() + [{"sumber_id": "DESA-001", "gid": "22", "bobot": 0.1}]
    assert_invalid(bad_rows, manifest, "duplicate.*DESA-001")


def test_gid_at_wrong_level_is_refused(manifest):
    assert_invalid(
        [{"sumber_id": "DESA-001", "gid": "2", "bobot": 1.0}],
        manifest,
        "DESA-001.*level",
    )


def test_invalid_gid_string_is_refused(manifest):
    assert_invalid(
        [{"sumber_id": "DESA-001", "gid": "ZZ", "bobot": 1.0}],
        manifest,
        "DESA-001.*invalid gid",
    )


def test_empty_sumber_id_is_refused(manifest):
    assert_invalid(
        [{"sumber_id": "", "gid": "22", "bobot": 1.0}],
        manifest,
        "empty sumber_id",
    )


def test_unknown_weight_kind_is_refused(manifest):
    manifest["weight_kind"] = "tinggi"
    assert_invalid(rows(), manifest, "weight_kind")


def test_wrong_format_version_is_refused(manifest):
    manifest["format_version"] = "2.0"
    assert_invalid(rows(), manifest, "format_version")


def test_sum_within_tolerance_passes(manifest):
    almost_one = 1.0 - 1e-12
    assert validate_crosswalk(
        [{"sumber_id": "DESA-001", "gid": "22", "bobot": almost_one}], manifest
    ) == {"sources": 1, "rows": 1, "cells": 1}


def test_empty_table_is_refused(manifest):
    assert_invalid([], manifest, "no rows")


def test_unknown_domain_code_is_refused(manifest):
    manifest["domain_code"] = "XX"
    assert_invalid(rows(), manifest, "domain_code must be one of")


def test_every_registry_domain_is_accepted(manifest):
    for code in ("BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"):
        manifest["domain_code"] = code
        assert validate_crosswalk(rows(), manifest)["sources"] == 2
