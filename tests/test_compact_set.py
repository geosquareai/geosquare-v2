"""cell_compact_set: committed vectors and independent checks of the reference rules."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from geosquare_v2.codec import canonical_to_gid
from geosquare_v2.compact import CompactSetError, canonicalize, child_gids, contains, expand, validate_compact_set
from geosquare_v2.errors import InvalidGIDError

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = REPO_ROOT / "conformance" / "spec-2.0" / "compact-set.json"
GENERATOR = REPO_ROOT / "tools" / "generate_conformance_vectors.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_conformance_vectors", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _vectors() -> dict:
    return json.loads(VECTOR_FILE.read_text(encoding="utf-8"))


def test_committed_cases_match_reference_rules():
    data = _vectors()
    assert data["dataset_type"] == "cell_compact_set"
    evaluate = _load_generator().evaluate_compact_case
    for case in data["cases"]:
        assert evaluate(case) == case["expect"], case["name"]


def test_case_names_are_unique_and_cover_every_operation():
    cases = _vectors()["cases"]
    names = [case["name"] for case in cases]
    assert len(names) == len(set(names))
    assert {case["operation"] for case in cases} == {"canonicalize", "expand", "contains", "validate"}


def test_expansion_counts_are_products_of_child_counts():
    root = canonical_to_gid(0, 0, 0)
    assert len(expand([root], 1)) == 25
    assert len(expand([root], 2)) == 25 * 4
    assert len(expand([root], 3)) == 25 * 4 * 25
    assert len(expand([root], 4)) == 25 * 4 * 25 * 4


def test_canonicalize_is_idempotent():
    level1 = [canonical_to_gid(1, x, y) for y in range(5) for x in range(5)]
    once = canonicalize(level1[:-1] + [canonical_to_gid(2, 0, 0)])
    assert canonicalize(once) == once


def test_canonicalize_output_passes_validation():
    level2 = [canonical_to_gid(2, x, y) for y in range(10) for x in range(10)]
    compact = canonicalize(level2[:-1])
    # 24 complete level-1 groups become level-1 cells. The last group keeps its 3 level-2 cells.
    assert len(compact) == 24 + 3
    validate_compact_set((gid, len(gid)) for gid in compact)


def test_membership_agrees_with_expansion_for_every_level_two_cell():
    stored = [canonical_to_gid(1, 0, 0), canonical_to_gid(2, 2, 0)]
    expanded = expand(stored, 2)
    for x in range(10):
        for y in range(10):
            gid = canonical_to_gid(2, x, y)
            assert contains(stored, gid) == (gid in expanded), gid


def test_ancestor_lookup_and_expansion_join_match():
    stored = [canonical_to_gid(1, 0, 0), canonical_to_gid(2, 2, 0)]
    dataset_gids = [canonical_to_gid(2, x, y) for y in range(10) for x in range(10)]
    via_expansion = {gid for gid in dataset_gids if gid in expand(stored, 2)}
    via_lookup = {gid for gid in dataset_gids if contains(stored, gid)}
    assert via_expansion == via_lookup
    assert len(via_lookup) == 5


def test_level_fourteen_has_no_children():
    with pytest.raises(CompactSetError):
        child_gids("2" * 14)


def test_invalid_gid_is_rejected():
    with pytest.raises(InvalidGIDError):
        contains([], "A")
