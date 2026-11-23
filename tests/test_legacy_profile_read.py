"""Datasets written by geosquare-v2 1.0.0 must still load. Their profile is 2.1.0-static-datum.

The fixtures in tests/fixtures/legacy_v1_0_0 were written with the 1.0.0 code. See
docs/profile-compatibility.md for the measurements behind the expected statuses.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import warnings

import pytest

from geosquare_v2 import (
    CellDataset,
    CellDatasetManifest,
    CellDatasetManifestError,
    DbRegistryLoader,
    GeosquareService,
    read_cell_dataset,
)
from geosquare_v2.errors import ValidationError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "legacy_v1_0_0"
BOUNDARY_ROOT = ROOT / "src/geosquare_v2/data/registry"
DOMAINS = sorted(path.name for path in FIXTURES.iterdir() if path.is_dir())
GID_CHANGED = frozenset(("LA", "VN"))


@pytest.fixture(scope="module")
def registry():
    keys = json.loads((ROOT / "release/registry-trust.json").read_text(encoding="utf-8"))
    trust = {key_id: base64.b64decode(value, validate=True) for key_id, value in keys.items()}
    return DbRegistryLoader(
        trust,
        ROOT / "src/geosquare_v2/db",
        boundary_root=BOUNDARY_ROOT,
        verify_boundaries=True,
    ).load()


@pytest.fixture(scope="module")
def service(registry):
    # Provisional domains (KH, MM, TH, TL, VN) need this opt-in. The tests compare GIDs, not release status.
    return GeosquareService(registry, boundary_root=BOUNDARY_ROOT, allow_candidate_crs=True)


def test_fixtures_cover_every_domain():
    assert DOMAINS == ["BN", "ID", "KH", "LA", "MM", "MY", "PH", "SG", "TH", "TL", "VN"]


@pytest.mark.parametrize("domain", DOMAINS)
def test_legacy_dataset_loads(registry, domain):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        dataset = read_cell_dataset(FIXTURES / domain, registry=registry)

    assert dataset.num_rows == 5
    assert dataset.manifest.profile_version == "2.1.0-static-datum"
    expected = "legacy_gids_differ" if domain in GID_CHANGED else "legacy_same_gids"
    assert dataset.manifest.profile_status == expected
    warned = any("GIDs differ" in str(item.message) for item in caught)
    assert warned == (domain in GID_CHANGED)


@pytest.mark.parametrize("domain", sorted(set(DOMAINS) - GID_CHANGED))
def test_gids_match_the_1_0_0_output_where_profiles_agree(service, domain):
    points = json.loads((FIXTURES / domain / "points.json").read_text(encoding="utf-8"))
    for point in points:
        assert service.point_to_cell(domain, point["lon"], point["lat"], 12).gid == point["gid"]


def test_vn_point_that_moved_between_profiles(service):
    # Full-precision coordinates. The 1.0.0 package gives H2Y3L4N5P593. The current profile gives H2Y3L4N5P5C2.
    assert service.point_to_cell("VN", 106.75489806793476, 9.556721344901272, 12).gid == "H2Y3L4N5P5C2"


def test_writers_refuse_the_legacy_profile(registry):
    legacy = read_cell_dataset(FIXTURES / "ID", registry=registry)
    document = legacy.manifest.to_dict()

    with pytest.raises(ValidationError, match="read-only"):
        CellDataset.from_table(legacy.table, document, registry=registry)


def test_unknown_profile_versions_are_still_rejected(registry):
    document = read_cell_dataset(FIXTURES / "ID", registry=registry).manifest.to_dict()
    document["profile_version"] = "2.0.0-unknown"

    with pytest.raises(CellDatasetManifestError, match="does not match trusted profile"):
        CellDatasetManifest.from_dict(document, registry=registry)
