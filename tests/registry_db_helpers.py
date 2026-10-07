"""Shared helpers for building temporary signed registry databases in tests.

The production JSON registry (``registry.v2.json`` + ``profiles/*.json`` +
``scale/*.json``) was removed once the SQLite migration was finalized (Requirement 5.1).
Tests therefore build their own small, synthetic legacy-format JSON tree on the fly and
migrate *that* into a database, rather than depending on removed production files.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import NamedTuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import pyproj
from pyproj import CRS

from geosquare_v2.db import DbRegistryLoader, MigrationTool

# Kept for reference by any future test that needs the real boundary GeoJSON files
# (which remain on disk, unaffected by the SQLite migration).
PRODUCTION_BOUNDARY_ROOT = Path(__file__).parents[1] / "src" / "geosquare_v2" / "data" / "registry"

_TS_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
}

_DOMAIN_CODES = ("TS", "TX")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_legacy_json_registry(root: Path, domain_codes: tuple[str, ...] = _DOMAIN_CODES) -> Path:
    """Write a minimal, valid legacy-format JSON registry tree under ``root``.

    Produces ``registry.v2.json`` (unsigned), ``profiles/<CODE>.v2.json``,
    ``scale/<CODE>_GRID_V2.json``, and ``boundaries/<CODE>.geojson`` for each requested
    domain code. Returns ``root``.
    """
    (root / "profiles").mkdir(parents=True, exist_ok=True)
    (root / "scale").mkdir(parents=True, exist_ok=True)
    (root / "boundaries").mkdir(parents=True, exist_ok=True)

    grid_crs_wkt2 = CRS.from_epsg(3857).to_wkt("WKT2_2019")
    equal_area_crs_wkt2 = CRS.from_epsg(6933).to_wkt("WKT2_2019")

    domains = []
    for index, code in enumerate(domain_codes, start=1):
        boundary_path = root / "boundaries" / f"{code}.geojson"
        _write_json(boundary_path, _TS_BOUNDARY)

        scale_path = root / "scale" / f"{code}_GRID_V2.json"
        _write_json(
            scale_path,
            {
                "domain_code": code,
                "algorithm": "test-algorithm",
                "proj_version": "9.5.1",
                "pyproj_version": "3.7.2",
                "boundary_sha256": _sha256(boundary_path),
                "sample_count": 4,
                "max_error_pct": 0.1 * index,
                "max_error_coordinate_crs84": [1.0 * index, 2.0 * index],
                "meridional_scale": 1.0,
                "parallel_scale": 1.0 + 0.01 * index,
            },
        )

        profile_path = root / "profiles" / f"{code}.v2.json"
        _write_json(
            profile_path,
            {
                "domain_id": index,
                "domain_code": code,
                "name": f"Test Domain {code}",
                "origin_x_m": -25_000_000.0,
                "origin_y_m": -25_000_000.0,
                "root_side_m": 50_000_000.0,
                "reference_epoch": 2000.0 + index,
                "grid_crs": "EPSG:3857",
                "equal_area_crs": "EPSG:6933",
                "profile_version": "test-1",
                "crs_authority": "EPSG:3857",
                "crs_wkt2": grid_crs_wkt2,
                "equal_area_crs_authority": "EPSG:6933",
                "equal_area_crs_wkt2": equal_area_crs_wkt2,
                "min_level": 0,
                "max_level": 14,
                "scale_error_max_pct": 0.1 * index,
                "scale_error_method": "test-algorithm",
                "scale_error_evaluation_metadata": f"../scale/{code}_GRID_V2.json",
                "scale_metadata_sha256": _sha256(scale_path),
                "boundary_source_crs": "OGC:CRS84",
                "boundary_file": f"../boundaries/{code}.geojson",
                "boundary_sha256": _sha256(boundary_path),
                "boundary_source": "synthetic test fixture",
            },
        )

        domains.append(
            {
                "domain_id": index,
                "domain_code": code,
                "profile_file": f"profiles/{code}.v2.json",
                "profile_sha256": _sha256(profile_path),
            }
        )

    proj_db_path = Path(pyproj.datadir.get_data_dir()) / "proj.db"
    _write_json(
        root / "registry.v2.json",
        {
            "registry_version": "2.0.0",
            "release_status": "candidate",
            "proj_version_exact": pyproj.proj_version_str,
            "proj_db_sha256": _sha256(proj_db_path),
            "required_proj_grids": [],
            "domains": domains,
        },
    )
    return root


class SignedTestKeypair(NamedTuple):
    key_id: str
    private_key: ed25519.Ed25519PrivateKey
    public_key_bytes: bytes


def generate_test_keypair(key_id: str = "test-key") -> SignedTestKeypair:
    """Generate an in-memory Ed25519 keypair for tests (never the real release key)."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return SignedTestKeypair(key_id=key_id, private_key=private_key, public_key_bytes=public_key_bytes)


def sign_database(db_path: Path, sig_path: Path, keypair: SignedTestKeypair) -> None:
    """Sign a built registry database file, writing the sidecar signature file."""
    digest = hashlib.sha256(db_path.read_bytes()).digest()
    signature = keypair.private_key.sign(digest)
    sidecar = {
        "algorithm": "Ed25519",
        "key_id": keypair.key_id,
        "value": base64.b64encode(signature).decode("ascii"),
        "sha256": digest.hex(),
    }
    sig_path.write_text(json.dumps(sidecar), encoding="utf-8")


def build_signed_registry_db(
    tmp_path: Path,
    source_root: Path | None = None,
    keypair: SignedTestKeypair | None = None,
    db_file: str = "registry.db",
    sig_file: str = "registry.db.sig",
) -> tuple[Path, dict[str, bytes], SignedTestKeypair]:
    """Build a synthetic legacy JSON registry (unless ``source_root`` is given), migrate,
    and sign the resulting database.

    Returns (db_dir, trusted_keys, keypair) suitable for constructing a DbRegistryLoader.
    The database is written directly inside ``tmp_path``, distinct from ``source_root`` (the
    directory that was migrated *from*), so callers must pass a matching ``boundary_root``
    to ``DbRegistryLoader`` (defaulting to ``source_root`` when it was auto-generated here).
    """
    keypair = keypair or generate_test_keypair()
    if source_root is None:
        source_root = build_legacy_json_registry(tmp_path / "legacy_source")
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path = db_dir / db_file
    MigrationTool(source_root).migrate(db_path)
    sign_database(db_path, db_dir / sig_file, keypair)
    return db_dir, {keypair.key_id: keypair.public_key_bytes}, keypair


def load_signed_registry_db(
    tmp_path: Path,
    source_root: Path | None = None,
    boundary_root: Path | None = None,
):
    """Build, sign, and load a registry database from a synthetic legacy JSON tree."""
    if source_root is None:
        source_root = build_legacy_json_registry(tmp_path / "legacy_source")
    db_dir, trusted_keys, _ = build_signed_registry_db(tmp_path, source_root=source_root)
    loader = DbRegistryLoader(trusted_keys, db_dir, boundary_root=boundary_root or source_root)
    return loader.load()
