"""SQLite-backed registry storage: schema, migration, and verified loading.

This module replaces the legacy JSON registry (``registry.v2.json`` + ``profiles/*.json``
+ ``scale/*.json``) with a single SQLite database file trusted via a detached Ed25519
signature computed over the raw database file bytes. Boundary files
(``boundaries/*.geojson``) remain on disk, unchanged, and are only referenced by relative
path + SHA-256 from the database.

``DomainRegistry`` (``registry.py``) and ``ReleaseProfile`` (``release.py``) are reused
unmodified: :class:`DbRegistryLoader` produces the exact same value objects that the
legacy JSON-backed ``RegistryLoader`` produces.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import (
    ArtifactHashMismatchError,
    ManifestSignatureError,
    ManifestValidationError,
    ProjResourceVerificationError,
    RegistryDependencyError,
)
from .registry import DomainRegistry
from .release import ReleaseProfile

SCHEMA_VERSION = 1

CREATE_SCHEMA_SQL = """
CREATE TABLE manifest (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    registry_version    TEXT NOT NULL,
    release_status      TEXT NOT NULL,
    proj_version_exact  TEXT NOT NULL,
    proj_db_sha256      TEXT NOT NULL
);

CREATE TABLE required_proj_grids (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    path   TEXT NOT NULL,
    sha256 TEXT NOT NULL
);

CREATE TABLE domains (
    domain_id       INTEGER PRIMARY KEY,
    domain_code     TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    origin_x_m      REAL NOT NULL,
    origin_y_m      REAL NOT NULL,
    root_side_m     REAL NOT NULL,
    reference_epoch REAL,
    grid_crs        TEXT,
    equal_area_crs  TEXT
);

CREATE TABLE profiles (
    domain_id                 INTEGER PRIMARY KEY REFERENCES domains(domain_id),
    profile_version           TEXT NOT NULL,
    crs_authority             TEXT NOT NULL,
    crs_wkt2                  TEXT NOT NULL,
    equal_area_crs_authority  TEXT NOT NULL,
    equal_area_crs_wkt2       TEXT NOT NULL,
    min_level                 INTEGER NOT NULL,
    max_level                 INTEGER NOT NULL,
    scale_error_max_pct       REAL NOT NULL,
    scale_error_method        TEXT NOT NULL,
    scale_metadata_sha256     TEXT NOT NULL,
    boundary_source_crs       TEXT NOT NULL,
    boundary_file             TEXT NOT NULL,
    boundary_sha256           TEXT NOT NULL,
    boundary_source           TEXT NOT NULL
);

CREATE TABLE scale_metadata (
    domain_id                       INTEGER PRIMARY KEY REFERENCES domains(domain_id),
    algorithm                       TEXT NOT NULL,
    proj_version                    TEXT NOT NULL,
    pyproj_version                  TEXT NOT NULL,
    boundary_sha256                 TEXT NOT NULL,
    sample_count                    INTEGER NOT NULL,
    max_error_pct                   REAL NOT NULL,
    max_error_coordinate_crs84_lon  REAL NOT NULL,
    max_error_coordinate_crs84_lat  REAL NOT NULL,
    meridional_scale                REAL NOT NULL,
    parallel_scale                  REAL NOT NULL
);
"""

_SHA256_HEX = frozenset("0123456789abcdef")


def _dependency(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise RegistryDependencyError(
            "signed registry loading requires the 'registry' optional dependency group"
        ) from exc


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestValidationError(f"cannot read valid JSON {label}: {path}") from exc
    if not isinstance(document, dict):
        raise ManifestValidationError(f"{label} must be a JSON object")
    return document


def _safe_path(root: Path, base: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ManifestValidationError("artifact path must be a non-empty relative string")
    candidate = (base / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ManifestValidationError("artifact path escapes registry root")
    return candidate


def _verify_hash(path: Path, expected_hash: str, label: str) -> None:
    if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(
        char not in _SHA256_HEX for char in expected_hash
    ):
        raise ManifestValidationError(f"{label} hash must be a lowercase SHA-256 digest")
    try:
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ArtifactHashMismatchError(f"cannot read {label} artifact: {path}") from exc
    if actual_hash != expected_hash:
        raise ArtifactHashMismatchError(f"{label} SHA-256 mismatch: {path}")


def _require_string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestValidationError(f"{key} must be a non-empty string")
    return value


def _require_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise ManifestValidationError(f"{key} must be an array")
    return value


def _canonical_scale_metadata_json(row: Mapping[str, Any]) -> bytes:
    """Build the canonical JSON serialization a scale_metadata row is hashed from.

    This reconstructs the legacy ``scale/<CODE>_GRID_V2.json`` document shape (including
    ``max_error_coordinate_crs84`` as a two-element ``[lon, lat]`` array) so the resulting
    hash is self-consistent with the row data it protects, independent of any file on disk.
    """
    document = {
        "domain_code": row["domain_code"],
        "algorithm": row["algorithm"],
        "proj_version": row["proj_version"],
        "pyproj_version": row["pyproj_version"],
        "boundary_sha256": row["boundary_sha256"],
        "sample_count": row["sample_count"],
        "max_error_pct": row["max_error_pct"],
        "max_error_coordinate_crs84": [
            row["max_error_coordinate_crs84_lon"],
            row["max_error_coordinate_crs84_lat"],
        ],
        "meridional_scale": row["meridional_scale"],
        "parallel_scale": row["parallel_scale"],
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class _ValidatedDomain:
    """A fully hash-verified (domain, profile, scale metadata) triple ready to persist."""

    domain: dict[str, Any]
    profile: dict[str, Any]
    scale_metadata: dict[str, Any]


class MigrationTool:
    """Builds a fresh Registry_Database from legacy JSON registry artifacts."""

    def __init__(self, source_root: str | Path) -> None:
        self._root = Path(source_root).resolve()
        if not self._root.is_dir():
            raise ManifestValidationError(f"registry source root is not a directory: {self._root}")

    def migrate(self, destination_db_path: str | Path, manifest_file: str = "registry.v2.json") -> int:
        """Validate the legacy JSON registry and write a fresh SQLite database.

        Returns the number of domains written. Raises without creating or leaving behind
        any file at ``destination_db_path`` if validation fails at any point.
        """
        manifest_path = _safe_path(self._root, self._root, manifest_file)
        manifest = _load_json(manifest_path, "manifest")

        entries = _require_list(manifest, "domains")
        if not entries:
            raise ManifestValidationError("manifest must declare at least one domain")

        required_proj_grids = _require_list(manifest, "required_proj_grids")
        for grid in required_proj_grids:
            if not isinstance(grid, dict) or not isinstance(grid.get("path"), str) or not isinstance(
                grid.get("sha256"), str
            ):
                raise ManifestValidationError("required_proj_grids entries must have path and sha256")

        validated: list[_ValidatedDomain] = []
        seen_ids: set[int] = set()
        seen_codes: set[str] = set()
        for entry in entries:
            item = self._validate_domain_entry(entry)
            domain_id = item.domain["domain_id"]
            domain_code = item.domain["domain_code"]
            if domain_id in seen_ids or domain_code in seen_codes:
                raise ManifestValidationError("manifest contains duplicate domain ID or code")
            seen_ids.add(domain_id)
            seen_codes.add(domain_code)
            validated.append(item)

        destination = Path(destination_db_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._write_database(destination, manifest, required_proj_grids, validated)
        return len(validated)

    def _validate_domain_entry(self, entry: Any) -> _ValidatedDomain:
        if not isinstance(entry, dict):
            raise ManifestValidationError("domain entry must be an object")
        domain_id, domain_code = entry.get("domain_id"), entry.get("domain_code")
        profile_file, profile_hash = entry.get("profile_file"), entry.get("profile_sha256")
        if (
            type(domain_id) is not int
            or not isinstance(domain_code, str)
            or not isinstance(profile_file, str)
            or not isinstance(profile_hash, str)
        ):
            raise ManifestValidationError("domain entry has invalid required fields")

        profile_path = _safe_path(self._root, self._root, profile_file)
        _verify_hash(profile_path, profile_hash, "profile")
        profile = _load_json(profile_path, "profile")
        if profile.get("domain_id") != domain_id or profile.get("domain_code") != domain_code:
            raise ManifestValidationError("profile identity does not match manifest entry")

        scale_relative = _require_string(profile, "scale_error_evaluation_metadata")
        scale_path = _safe_path(self._root, profile_path.parent, scale_relative)
        _verify_hash(scale_path, _require_string(profile, "scale_metadata_sha256"), "scale metadata")
        scale_metadata = _load_json(scale_path, "scale metadata")
        if scale_metadata.get("domain_code") != domain_code:
            raise ManifestValidationError("scale metadata identity does not match manifest entry")

        # The legacy profile stores boundary_file relative to the profiles/ directory
        # (e.g. "../boundaries/ID.geojson"). Normalize it to be relative to the registry
        # root so DbRegistryLoader can resolve it against a boundary root independent of
        # where the SQLite database file itself lives.
        boundary_relative = _require_string(profile, "boundary_file")
        boundary_path = _safe_path(self._root, profile_path.parent, boundary_relative)
        _verify_hash(boundary_path, _require_string(profile, "boundary_sha256"), "boundary")
        normalized_profile = dict(profile)
        normalized_profile["boundary_file"] = boundary_path.relative_to(self._root).as_posix()

        return _ValidatedDomain(domain=normalized_profile, profile=normalized_profile, scale_metadata=scale_metadata)

    def _write_database(
        self,
        destination: Path,
        manifest: dict[str, Any],
        required_proj_grids: list[Any],
        validated: list[_ValidatedDomain],
    ) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=str(destination.parent), suffix=".tmp-registry.db")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            connection = sqlite3.connect(str(tmp_path))
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executescript(CREATE_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO manifest (id, registry_version, release_status, proj_version_exact, "
                    "proj_db_sha256) VALUES (1, ?, ?, ?, ?)",
                    (
                        _require_string(manifest, "registry_version"),
                        _require_string(manifest, "release_status"),
                        _require_string(manifest, "proj_version_exact"),
                        _require_string(manifest, "proj_db_sha256"),
                    ),
                )
                connection.executemany(
                    "INSERT INTO required_proj_grids (path, sha256) VALUES (?, ?)",
                    [(grid["path"], grid["sha256"]) for grid in required_proj_grids],
                )
                for item in validated:
                    self._insert_domain(connection, item)
                connection.commit()
            finally:
                connection.close()
            os.replace(tmp_path, destination)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _insert_domain(connection: sqlite3.Connection, item: _ValidatedDomain) -> None:
        domain = item.domain
        profile = item.profile
        scale_metadata = item.scale_metadata

        connection.execute(
            "INSERT INTO domains (domain_id, domain_code, name, origin_x_m, origin_y_m, root_side_m, "
            "reference_epoch, grid_crs, equal_area_crs) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                domain["domain_id"],
                domain["domain_code"],
                domain.get("name"),
                domain.get("origin_x_m"),
                domain.get("origin_y_m"),
                domain.get("root_side_m"),
                domain.get("reference_epoch"),
                domain.get("grid_crs"),
                domain.get("equal_area_crs"),
            ),
        )

        max_error_coordinate = scale_metadata.get("max_error_coordinate_crs84")
        if not isinstance(max_error_coordinate, list) or len(max_error_coordinate) != 2:
            raise ManifestValidationError("scale metadata max_error_coordinate_crs84 must be a 2-element array")
        canonical_hash = hashlib.sha256(
            _canonical_scale_metadata_json(
                {
                    "domain_code": scale_metadata.get("domain_code"),
                    "algorithm": scale_metadata.get("algorithm"),
                    "proj_version": scale_metadata.get("proj_version"),
                    "pyproj_version": scale_metadata.get("pyproj_version"),
                    "boundary_sha256": scale_metadata.get("boundary_sha256"),
                    "sample_count": scale_metadata.get("sample_count"),
                    "max_error_pct": scale_metadata.get("max_error_pct"),
                    "max_error_coordinate_crs84_lon": max_error_coordinate[0],
                    "max_error_coordinate_crs84_lat": max_error_coordinate[1],
                    "meridional_scale": scale_metadata.get("meridional_scale"),
                    "parallel_scale": scale_metadata.get("parallel_scale"),
                }
            )
        ).hexdigest()

        connection.execute(
            "INSERT INTO profiles (domain_id, profile_version, crs_authority, crs_wkt2, "
            "equal_area_crs_authority, equal_area_crs_wkt2, min_level, max_level, scale_error_max_pct, "
            "scale_error_method, scale_metadata_sha256, boundary_source_crs, boundary_file, "
            "boundary_sha256, boundary_source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                domain["domain_id"],
                profile.get("profile_version"),
                profile.get("crs_authority"),
                profile.get("crs_wkt2"),
                profile.get("equal_area_crs_authority"),
                profile.get("equal_area_crs_wkt2"),
                profile.get("min_level"),
                profile.get("max_level"),
                profile.get("scale_error_max_pct"),
                profile.get("scale_error_method"),
                canonical_hash,
                profile.get("boundary_source_crs"),
                profile.get("boundary_file"),
                profile.get("boundary_sha256"),
                profile.get("boundary_source"),
            ),
        )

        connection.execute(
            "INSERT INTO scale_metadata (domain_id, algorithm, proj_version, pyproj_version, boundary_sha256, "
            "sample_count, max_error_pct, max_error_coordinate_crs84_lon, max_error_coordinate_crs84_lat, "
            "meridional_scale, parallel_scale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                domain["domain_id"],
                scale_metadata.get("algorithm"),
                scale_metadata.get("proj_version"),
                scale_metadata.get("pyproj_version"),
                scale_metadata.get("boundary_sha256"),
                scale_metadata.get("sample_count"),
                scale_metadata.get("max_error_pct"),
                max_error_coordinate[0],
                max_error_coordinate[1],
                scale_metadata.get("meridional_scale"),
                scale_metadata.get("parallel_scale"),
            ),
        )


@dataclass(frozen=True, slots=True)
class RegistryDomainSummary:
    """A lightweight, unverified summary row for listing domains in a Registry_Database.

    This is intentionally not a trust decision: it does not verify the database's
    signature, PROJ resources, boundary hashes, or CRS definitions. Use it to inspect
    which domains exist in a ``registry.db`` file (e.g. for a CLI listing or a quick
    sanity check). Use :class:`DbRegistryLoader` when you need verified profiles to
    build a :class:`~geosquare_v2.registry.DomainRegistry` for actual application use.
    """

    domain_id: int
    domain_code: str
    name: str
    profile_version: str
    min_level: int
    max_level: int


def list_registry_domains(
    db_path: str | Path | None = None, db_file: str = "registry.db"
) -> tuple[RegistryDomainSummary, ...]:
    """List the domains present in a Registry_Database, without verifying its signature.

    ``db_path`` may be either the database file itself or the directory containing it
    (in which case ``db_file`` is joined onto it, matching :class:`DbRegistryLoader`'s
    directory-based convention). Defaults to :data:`DEFAULT_DB_DIR` (``src/geosquare_v2/db``) when
    omitted. Raises :class:`ManifestValidationError` if the file is missing or is not a
    readable SQLite database with the expected schema.
    """
    candidate = Path(db_path).resolve() if db_path is not None else DEFAULT_DB_DIR
    resolved = candidate / db_file if candidate.is_dir() else candidate
    if not resolved.is_file():
        raise ManifestValidationError(f"registry database is missing: {resolved}")

    try:
        connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True)
    except sqlite3.DatabaseError as exc:
        raise ManifestValidationError(f"registry database cannot be opened: {resolved}") from exc

    try:
        cursor = connection.execute(
            "SELECT d.domain_id, d.domain_code, d.name, p.profile_version, p.min_level, p.max_level "
            "FROM domains d LEFT JOIN profiles p ON p.domain_id = d.domain_id "
            "ORDER BY d.domain_id"
        )
        rows = cursor.fetchall()
    except sqlite3.DatabaseError as exc:
        raise ManifestValidationError(f"registry database schema is invalid or corrupt: {resolved}") from exc
    finally:
        connection.close()

    return tuple(
        RegistryDomainSummary(
            domain_id=domain_id,
            domain_code=domain_code,
            name=name,
            profile_version=profile_version or "",
            min_level=min_level if min_level is not None else 0,
            max_level=max_level if max_level is not None else 0,
        )
        for domain_id, domain_code, name, profile_version, min_level, max_level in rows
    )


#: Default directory searched for the registry database when no ``db_dir`` is given to
#: :class:`DbRegistryLoader` or :func:`list_registry_domains`. Resolves to
#: ``src/geosquare_v2/db``, a subdirectory living inside the installable package itself
#: (rather than ``src/geosquare_v2/db``, which sits outside the package tree) so the database ships
#: as ordinary package data.
DEFAULT_DB_DIR = Path(__file__).resolve().parent / "db"


class DbRegistryLoader:
    """Load a Registry_Database only after its detached signature verifies.

    Trusted public keys are supplied by the application, never read from the database or
    its signature file. Each mapping value is a raw 32-byte Ed25519 public key.

    Boundary GeoJSON files are not used by any grid calculation (indexing, encoding,
    geometry, or polyfill all operate purely on the profile's CRS/origin/level fields).
    They exist only so a release reviewer can confirm which operational boundary was
    used when a profile's scale metadata was computed. Pass ``verify_boundaries=False``
    (or leave it at its default) to skip checking them entirely, which lets you ship just
    ``registry.db`` and ``registry.db.sig`` without the ``boundaries/*.geojson`` files or
    ``boundary_root``.

    ``db_dir`` defaults to :data:`DEFAULT_DB_DIR` (``src/geosquare_v2/db``) so ``DbRegistryLoader(trust)``
    works out of the box for the bundled candidate database. Pass an explicit ``db_dir``
    to load a database from anywhere else (e.g. in tests).
    """

    def __init__(
        self,
        trusted_public_keys: Mapping[str, bytes],
        db_dir: str | Path | None = None,
        boundary_root: str | Path | None = None,
        verify_boundaries: bool = False,
    ) -> None:
        self._db_dir = Path(db_dir).resolve() if db_dir is not None else DEFAULT_DB_DIR
        if not self._db_dir.is_dir():
            raise ManifestValidationError(f"registry database directory is not a directory: {self._db_dir}")
        self._verify_boundaries = verify_boundaries
        if verify_boundaries:
            self._boundary_root = Path(boundary_root).resolve() if boundary_root is not None else self._db_dir
            if not self._boundary_root.is_dir():
                raise ManifestValidationError(f"boundary root is not a directory: {self._boundary_root}")
        else:
            self._boundary_root = None
        self._trusted_keys = dict(trusted_public_keys)
        for key_id, public_key in self._trusted_keys.items():
            if not isinstance(key_id, str) or not key_id or not isinstance(public_key, bytes) or len(public_key) != 32:
                raise ManifestValidationError("trusted keys must map non-empty IDs to 32-byte Ed25519 public keys")

    def load(self, db_file: str = "registry.db", sig_file: str = "registry.db.sig") -> DomainRegistry:
        db_path = self._db_dir / db_file
        if not db_path.is_file():
            raise ManifestValidationError(f"registry database is missing: {db_path}")

        db_bytes = db_path.read_bytes()
        self._verify_signature(db_bytes, self._db_dir / sig_file)

        connection = self._open_readonly(db_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            manifest_row = self._fetch_manifest(connection)
            required_proj_grids = self._fetch_required_proj_grids(connection)
            self._verify_proj_resources(manifest_row, required_proj_grids)
            profiles = self._load_profiles(connection)
        finally:
            connection.close()

        if not profiles:
            raise ManifestValidationError("registry database must declare at least one domain")
        return DomainRegistry.from_verified_profiles(profiles)

    def _verify_signature(self, db_bytes: bytes, sig_path: Path) -> None:
        if not sig_path.is_file():
            raise ManifestValidationError(f"registry signature file is missing: {sig_path}")
        sidecar = _load_json(sig_path, "signature sidecar")
        if sidecar.get("algorithm") != "Ed25519":
            raise ManifestValidationError("registry database signature must use Ed25519")
        key_id = sidecar.get("key_id")
        encoded_value = sidecar.get("value")
        expected_hash = sidecar.get("sha256")
        if not isinstance(key_id, str) or key_id not in self._trusted_keys:
            raise ManifestSignatureError("registry database signature key is absent or untrusted")
        if not isinstance(encoded_value, str) or not isinstance(expected_hash, str):
            raise ManifestValidationError("registry database signature sidecar is malformed")

        actual_hash = hashlib.sha256(db_bytes).hexdigest()
        if actual_hash != expected_hash.lower():
            raise ManifestSignatureError("registry database SHA-256 does not match the signed digest")

        try:
            signature_bytes = base64.b64decode(encoded_value, validate=True)
        except ValueError as exc:
            raise ManifestSignatureError("registry database signature is not valid base64") from exc

        ed25519 = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(self._trusted_keys[key_id]).verify(
                signature_bytes, bytes.fromhex(actual_hash)
            )
        except ImportError as exc:
            raise RegistryDependencyError(
                "signed registry loading requires the 'registry' optional dependency group"
            ) from exc
        except Exception as exc:
            raise ManifestSignatureError("registry database Ed25519 signature verification failed") from exc

    @staticmethod
    def _open_readonly(db_path: Path) -> sqlite3.Connection:
        try:
            uri = f"file:{db_path.as_posix()}?mode=ro"
            return sqlite3.connect(uri, uri=True)
        except sqlite3.DatabaseError as exc:
            raise ManifestValidationError(f"registry database cannot be opened: {db_path}") from exc

    @staticmethod
    def _fetch_manifest(connection: sqlite3.Connection) -> dict[str, Any]:
        try:
            cursor = connection.execute(
                "SELECT registry_version, release_status, proj_version_exact, proj_db_sha256 "
                "FROM manifest WHERE id = 1"
            )
            row = cursor.fetchone()
        except sqlite3.DatabaseError as exc:
            raise ManifestValidationError("registry database schema is invalid or corrupt") from exc
        if row is None:
            raise ManifestValidationError("registry database is missing its manifest row")
        registry_version, release_status, proj_version_exact, proj_db_sha256 = row
        if registry_version != "2.0.0":
            raise ManifestValidationError("registry_version must be '2.0.0'")
        return {
            "registry_version": registry_version,
            "release_status": release_status,
            "proj_version_exact": proj_version_exact,
            "proj_db_sha256": proj_db_sha256,
        }

    @staticmethod
    def _fetch_required_proj_grids(connection: sqlite3.Connection) -> list[dict[str, str]]:
        try:
            cursor = connection.execute("SELECT path, sha256 FROM required_proj_grids")
            rows = cursor.fetchall()
        except sqlite3.DatabaseError as exc:
            raise ManifestValidationError("registry database schema is invalid or corrupt") from exc
        return [{"path": path, "sha256": sha256} for path, sha256 in rows]

    def _verify_proj_resources(self, manifest_row: dict[str, Any], required_proj_grids: list[dict[str, str]]) -> None:
        pyproj = _dependency("pyproj")
        expected_version = manifest_row.get("proj_version_exact")
        if not isinstance(expected_version, str) or pyproj.proj_version_str != expected_version:
            raise ProjResourceVerificationError("installed PROJ version does not match signed registry database")
        expected_db_hash = manifest_row.get("proj_db_sha256")
        if not isinstance(expected_db_hash, str):
            raise ManifestValidationError("proj_db_sha256 is required")
        data_dir = Path(pyproj.datadir.get_data_dir())
        _verify_hash(data_dir / "proj.db", expected_db_hash, "PROJ database")
        for resource in required_proj_grids:
            relative_path = resource.get("path")
            expected_hash = resource.get("sha256")
            if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
                raise ManifestValidationError("required_proj_grids entry requires path and sha256")
            _verify_hash(_safe_path(data_dir, data_dir, relative_path), expected_hash, "PROJ grid")

    def _load_profiles(self, connection: sqlite3.Connection) -> list[ReleaseProfile]:
        try:
            cursor = connection.execute(
                "SELECT d.domain_id, d.domain_code, d.name, d.origin_x_m, d.origin_y_m, d.root_side_m, "
                "d.reference_epoch, d.grid_crs, d.equal_area_crs, "
                "p.profile_version, p.crs_authority, p.crs_wkt2, p.equal_area_crs_authority, "
                "p.equal_area_crs_wkt2, p.min_level, p.max_level, p.scale_error_max_pct, "
                "p.scale_error_method, p.scale_metadata_sha256, p.boundary_source_crs, p.boundary_file, "
                "p.boundary_sha256, p.boundary_source, "
                "s.algorithm, s.proj_version, s.pyproj_version, s.boundary_sha256, s.sample_count, "
                "s.max_error_pct, s.max_error_coordinate_crs84_lon, s.max_error_coordinate_crs84_lat, "
                "s.meridional_scale, s.parallel_scale "
                "FROM domains d "
                "INNER JOIN profiles p ON p.domain_id = d.domain_id "
                "INNER JOIN scale_metadata s ON s.domain_id = d.domain_id "
                "ORDER BY d.domain_id"
            )
            rows = cursor.fetchall()
            domain_row_count = connection.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            raise ManifestValidationError("registry database schema is invalid or corrupt") from exc

        if len(rows) != domain_row_count:
            raise ManifestValidationError("registry database has a domain missing its profile or scale_metadata row")

        profiles: list[ReleaseProfile] = []
        for row in rows:
            profiles.append(self._build_profile(row))
        return profiles

    def _build_profile(self, row: tuple[Any, ...]) -> ReleaseProfile:
        (
            domain_id,
            domain_code,
            name,
            origin_x_m,
            origin_y_m,
            root_side_m,
            reference_epoch,
            grid_crs,
            equal_area_crs,
            profile_version,
            crs_authority,
            crs_wkt2,
            equal_area_crs_authority,
            equal_area_crs_wkt2,
            min_level,
            max_level,
            scale_error_max_pct,
            scale_error_method,
            scale_metadata_sha256,
            boundary_source_crs,
            boundary_file,
            boundary_sha256,
            boundary_source,
            algorithm,
            proj_version,
            pyproj_version,
            scale_boundary_sha256,
            sample_count,
            max_error_pct,
            max_error_lon,
            max_error_lat,
            meridional_scale,
            parallel_scale,
        ) = row

        canonical_hash = hashlib.sha256(
            _canonical_scale_metadata_json(
                {
                    "domain_code": domain_code,
                    "algorithm": algorithm,
                    "proj_version": proj_version,
                    "pyproj_version": pyproj_version,
                    "boundary_sha256": scale_boundary_sha256,
                    "sample_count": sample_count,
                    "max_error_pct": max_error_pct,
                    "max_error_coordinate_crs84_lon": max_error_lon,
                    "max_error_coordinate_crs84_lat": max_error_lat,
                    "meridional_scale": meridional_scale,
                    "parallel_scale": parallel_scale,
                }
            )
        ).hexdigest()
        if canonical_hash != scale_metadata_sha256:
            raise ArtifactHashMismatchError(f"scale metadata SHA-256 mismatch for domain {domain_code!r}")

        if self._verify_boundaries:
            boundary_path = _safe_path(self._boundary_root, self._boundary_root, boundary_file)
            _verify_hash(boundary_path, boundary_sha256, "boundary")

        self._verify_profile_crs(crs_wkt2, equal_area_crs_wkt2, domain_code)

        return ReleaseProfile(
            domain_id=domain_id,
            domain_code=domain_code,
            name=name,
            origin_x_m=origin_x_m,
            origin_y_m=origin_y_m,
            root_side_m=root_side_m,
            reference_epoch=reference_epoch,
            grid_crs=grid_crs,
            equal_area_crs=equal_area_crs,
            profile_version=profile_version,
            crs_authority=crs_authority,
            crs_wkt2=crs_wkt2,
            equal_area_crs_authority=equal_area_crs_authority,
            equal_area_crs_wkt2=equal_area_crs_wkt2,
            min_level=min_level,
            max_level=max_level,
            scale_error_max_pct=scale_error_max_pct,
            scale_error_method=scale_error_method,
            scale_error_evaluation_metadata=f"db:scale_metadata:{domain_code}",
            scale_metadata_sha256=scale_metadata_sha256,
            boundary_source_crs=boundary_source_crs,
            boundary_file=boundary_file,
            boundary_sha256=boundary_sha256,
            boundary_source=boundary_source,
        )

    @staticmethod
    def _verify_profile_crs(crs_wkt2: str, equal_area_crs_wkt2: str, domain_code: str) -> None:
        pyproj = _dependency("pyproj")
        try:
            grid = pyproj.CRS.from_wkt(crs_wkt2)
            equal_area = pyproj.CRS.from_wkt(equal_area_crs_wkt2)
        except Exception as exc:
            raise ManifestValidationError(f"domain {domain_code!r} has an invalid CRS WKT2 definition") from exc
        if not grid.is_projected or not equal_area.is_projected:
            raise ManifestValidationError(f"domain {domain_code!r} grid and equal-area CRSs must be projected")
