"""Spec 2.0 conformance vectors: drift, coverage, and independent re-checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path

import pytest

from geosquare_v2.codec import SUBDIVISIONS, canonical_to_gid, cell_side_m, gid_to_indices
from geosquare_v2.detect import detect_table
from geosquare_v2.errors import GeosquareError
from geosquare_v2.packing import unpack_int64

REPO_ROOT = Path(__file__).resolve().parents[1]
VECTOR_DIR = REPO_ROOT / "conformance" / "spec-2.0"
GENERATOR = REPO_ROOT / "tools" / "generate_conformance_vectors.py"
EXPECTED_DOMAIN_COUNT = 11


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_conformance_vectors", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _committed(name: str) -> dict:
    return json.loads((VECTOR_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generated() -> dict[str, bytes]:
    return _load_generator().build_all()


def test_committed_vectors_match_generator(generated):
    for name, payload in generated.items():
        committed = (VECTOR_DIR / name).read_bytes()
        assert committed == payload, f"{name} drifted; run python tools/generate_conformance_vectors.py"


def test_manifest_lists_every_vector_file_with_matching_hashes():
    manifest = _committed("manifest.json")
    vector_files = {path.name for path in VECTOR_DIR.glob("*.json")} - {"manifest.json"}
    assert set(manifest["files"]) == vector_files
    for name, entry in manifest["files"].items():
        payload = (VECTOR_DIR / name).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == entry["sha256"], name
        assert len(payload) == entry["bytes"], name


def test_manifest_declares_spec_and_all_domains():
    manifest = _committed("manifest.json")
    assert manifest["spec_version"] == "2.0"
    assert len(manifest["domains"]) == EXPECTED_DOMAIN_COUNT
    provisional = {d["domain_code"] for d in manifest["domains"] if not d["production_ready"]}
    assert provisional == {"KH", "MM", "TH", "TL"}


def test_codec_covers_every_level_with_round_trips():
    codec = _committed("codec.json")
    levels = {cell["level"] for cell in codec["cells"]}
    assert levels == set(range(len(SUBDIVISIONS) + 1))
    for cell in codec["cells"]:
        assert gid_to_indices(cell["gid"]) == (cell["level"], cell["x_idx"], cell["y_idx"])
        assert unpack_int64(int(cell["packed_id"])) == (
            codec["domain_id"], cell["level"], cell["x_idx"], cell["y_idx"],
        )


def test_invalid_inputs_are_rejected_by_reference():
    codec = _committed("codec.json")
    for case in codec["invalid_gids"]:
        with pytest.raises(GeosquareError):
            gid_to_indices(case["input"])
    for case in codec["invalid_packed_ids"]:
        with pytest.raises(GeosquareError):
            unpack_int64(int(case["packed_id"]))


def test_descendant_ranges_follow_child_counts():
    topology = _committed("topology.json")
    for record in topology["descendant_ranges"]:
        expected = 1
        for level in range(record["parent_level"], record["child_level"]):
            expected *= 25 if SUBDIVISIONS[level] == 5 else 4
        assert record["descendant_count"] == expected
        assert int(record["lo"]) < int(record["hi"])


def test_distances_match_square_root_formula():
    topology = _committed("topology.json")
    for record in topology["distances"]:
        assert record["cell_side_m"] == cell_side_m(record["level"])
        expected = math.sqrt(record["dx"] ** 2 + record["dy"] ** 2) * record["cell_side_m"]
        assert math.isclose(record["distance_m"], expected, rel_tol=1e-12)


def test_neighbour_rings_have_expected_sizes_away_from_edges():
    topology = _committed("topology.json")
    ring_sizes = {len(record["k_ring_1"]) for record in topology["neighbours"]}
    assert {8, 5, 3} <= ring_sizes
    for record in topology["neighbours"]:
        assert record["gid"] not in record["k_ring_1"]
        assert record["gid"] not in record["k_ring_2"]


def test_projected_cases_cover_every_domain_and_boundary_rule():
    projected = _committed("projected.json")
    domains = {case["domain_code"] for case in projected["cases"]}
    assert len(domains) == EXPECTED_DOMAIN_COUNT
    rejects = [case for case in projected["cases"] if case["expect"] == "reject"]
    accepts = [case for case in projected["cases"] if case["expect"] != "reject"]
    assert rejects and accepts
    for case in accepts:
        gid = case["expect"]["gid"]
        assert gid_to_indices(gid) == (case["level"], case["expect"]["x_idx"], case["expect"]["y_idx"])


def test_points_cover_every_domain_and_flag_provisional_ones():
    points = _committed("points.json")
    domains = {case["domain_code"] for case in points["cases"]}
    assert len(domains) == EXPECTED_DOMAIN_COUNT
    for case in points["cases"]:
        assert set(case["gids"]) == {"5", "7", "9", "12"}
        gids = case["gids"]
        assert len(gids["12"]) == 12
        assert gids["12"].startswith(gids["9"]) and gids["9"].startswith(gids["7"]) and gids["7"].startswith(gids["5"])
        assert case["production_ready"] == (case["domain_code"] not in {"KH", "MM", "TH", "TL"})


def test_packed_ids_by_domain_decode_to_their_own_domain():
    codec = _committed("codec.json")
    section = codec["packed_ids_by_domain"]
    domains = section["domains"]
    assert len(domains) == EXPECTED_DOMAIN_COUNT
    assert sorted(domains.values()) == list(range(1, EXPECTED_DOMAIN_COUNT + 1))
    assert section["cells"], "no cells in packed_ids_by_domain"
    for cell in section["cells"]:
        assert set(cell["packed_ids"]) == set(domains)
        assert gid_to_indices(cell["gid"]) == (cell["level"], cell["x_idx"], cell["y_idx"])
        for code, domain_id in domains.items():
            assert unpack_int64(int(cell["packed_ids"][code])) == (
                domain_id, cell["level"], cell["x_idx"], cell["y_idx"],
            ), code


def test_domain_ranges_lower_bound_is_a_descendant_of_the_parent():
    topology = _committed("topology.json")
    domains = _committed("codec.json")["packed_ids_by_domain"]["domains"]
    records = topology["descendant_ranges_by_domain"]["records"]
    assert records
    for record in records:
        assert set(record["ranges"]) == set(domains)
        for code, bounds in record["ranges"].items():
            domain_id, level, x_idx, y_idx = unpack_int64(int(bounds["lo"]))
            assert domain_id == domains[code]
            assert level == record["child_level"]
            assert canonical_to_gid(level, x_idx, y_idx).startswith(record["parent_gid"])
            assert int(bounds["lo"]) < int(bounds["hi"])


def test_domain_ranges_agree_with_id_ranges():
    topology = _committed("topology.json")
    id_ranges = {
        (r["parent_gid"], r["child_level"]): (r["lo"], r["hi"]) for r in topology["descendant_ranges"]
    }
    for record in topology["descendant_ranges_by_domain"]["records"]:
        key = (record["parent_gid"], record["child_level"])
        if "ID" in record["ranges"] and key in id_ranges:
            assert (record["ranges"]["ID"]["lo"], record["ranges"]["ID"]["hi"]) == id_ranges[key]


def test_detection_cases_match_reference_detector():
    detect = _committed("detect.json")
    assert len(detect["cases"]) >= 15
    for case in detect["cases"]:
        columns = {
            name: (spec["dtype"], [int(v) for v in spec["values"]] if spec["dtype"] == "int64" else spec["values"])
            for name, spec in case["columns"].items()
        }
        results = {
            result.column: result
            for result in detect_table(columns, domain_code=case.get("domain_code"), level=case.get("level"))
        }
        for key, expected in case["expect"].items():
            result = results[key]
            assert result.kind == expected["kind"], (case["name"], key)
            assert result.status == expected["status"], (case["name"], key)
            if "domain_codes" in expected:
                assert list(result.domain_codes) == expected["domain_codes"], (case["name"], key)
            if "domain_ids" in expected:
                assert list(result.domain_ids) == expected["domain_ids"], (case["name"], key)
            if "levels" in expected:
                assert list(result.levels) == expected["levels"], (case["name"], key)
