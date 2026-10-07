"""Fail-closed signed release registry loader for Geosquare V2."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
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


class RegistryLoader:
    """Load a V2 registry only after all signatures and artifacts verify.

    Trusted public keys are deliberately supplied by the application, never read from
    the manifest. Each mapping value is a raw 32-byte Ed25519 public key.
    """

    def __init__(self, artifact_root: str | Path, trusted_public_keys: Mapping[str, bytes]) -> None:
        self._root = Path(artifact_root).resolve()
        if not self._root.is_dir():
            raise ManifestValidationError(f"artifact root is not a directory: {self._root}")
        self._trusted_keys = dict(trusted_public_keys)
        for key_id, public_key in self._trusted_keys.items():
            if not isinstance(key_id, str) or not key_id or not isinstance(public_key, bytes) or len(public_key) != 32:
                raise ManifestValidationError("trusted keys must map non-empty IDs to 32-byte Ed25519 public keys")

    def load(self, manifest_file: str = "registry.v2.json") -> DomainRegistry:
        manifest_path = self._safe_path(self._root, manifest_file)
        manifest = self._load_json(manifest_path, "manifest")
        self._verify_manifest_signature(manifest)
        self._verify_proj_resources(manifest)

        entries = self._require_list(manifest, "domains")
        profiles: list[ReleaseProfile] = []
        seen_ids: set[int] = set()
        seen_codes: set[str] = set()
        for entry in entries:
            profile = self._load_profile(entry)
            if profile.domain_id in seen_ids or profile.domain_code in seen_codes:
                raise ManifestValidationError("manifest contains duplicate domain ID or code")
            seen_ids.add(profile.domain_id)
            seen_codes.add(profile.domain_code)
            profiles.append(profile)
        if not profiles:
            raise ManifestValidationError("manifest must declare at least one domain")
        return DomainRegistry.from_verified_profiles(profiles)

    def _verify_manifest_signature(self, manifest: dict[str, Any]) -> None:
        if manifest.get("registry_version") != "2.0.0":
            raise ManifestValidationError("registry_version must be '2.0.0'")
        signature = self._require_mapping(manifest, "signature")
        if signature.get("algorithm") != "Ed25519" or signature.get("canonicalization") != "RFC8785":
            raise ManifestValidationError("manifest signature must use Ed25519 and RFC8785")
        key_id = signature.get("key_id")
        encoded_value = signature.get("value")
        if not isinstance(key_id, str) or key_id not in self._trusted_keys or not isinstance(encoded_value, str):
            raise ManifestSignatureError("manifest signature key is absent or untrusted")
        try:
            signature_bytes = base64.b64decode(encoded_value, validate=True)
        except ValueError as exc:
            raise ManifestSignatureError("manifest signature is not valid base64") from exc
        unsigned = dict(manifest)
        unsigned.pop("signature", None)
        rfc8785 = self._dependency("rfc8785")
        try:
            canonical_bytes = rfc8785.dumps(unsigned)
        except Exception as exc:
            raise ManifestValidationError("manifest cannot be RFC8785 canonicalized") from exc
        try:
            ed25519 = importlib.import_module("cryptography.hazmat.primitives.asymmetric.ed25519")
            ed25519.Ed25519PublicKey.from_public_bytes(self._trusted_keys[key_id]).verify(signature_bytes, canonical_bytes)
        except Exception as exc:
            raise ManifestSignatureError("manifest Ed25519 signature verification failed") from exc

    def _verify_proj_resources(self, manifest: dict[str, Any]) -> None:
        pyproj = self._dependency("pyproj")
        expected_version = manifest.get("proj_version_exact")
        if not isinstance(expected_version, str) or pyproj.proj_version_str != expected_version:
            raise ProjResourceVerificationError("installed PROJ version does not match signed manifest")
        expected_db_hash = manifest.get("proj_db_sha256")
        if not isinstance(expected_db_hash, str):
            raise ManifestValidationError("proj_db_sha256 is required")
        data_dir = Path(pyproj.datadir.get_data_dir())
        self._verify_hash(data_dir / "proj.db", expected_db_hash, "PROJ database")
        for resource in self._require_list(manifest, "required_proj_grids"):
            if not isinstance(resource, dict):
                raise ManifestValidationError("required_proj_grids entries must be objects")
            relative_path = resource.get("path")
            expected_hash = resource.get("sha256")
            if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
                raise ManifestValidationError("PROJ resource requires path and sha256")
            self._verify_hash(self._safe_path(data_dir, relative_path), expected_hash, "PROJ grid")

    def _load_profile(self, entry: Any) -> ReleaseProfile:
        if not isinstance(entry, dict):
            raise ManifestValidationError("domain entry must be an object")
        domain_id, domain_code = entry.get("domain_id"), entry.get("domain_code")
        profile_file, profile_hash = entry.get("profile_file"), entry.get("profile_sha256")
        if type(domain_id) is not int or not isinstance(domain_code, str) or not isinstance(profile_file, str) or not isinstance(profile_hash, str):
            raise ManifestValidationError("domain entry has invalid required fields")
        profile_path = self._safe_path(self._root, profile_file)
        self._verify_hash(profile_path, profile_hash, "profile")
        document = self._load_json(profile_path, "profile")
        if document.get("domain_id") != domain_id or document.get("domain_code") != domain_code:
            raise ManifestValidationError("profile identity does not match manifest entry")
        self._verify_profile_crs(document)
        boundary_path = self._safe_path(profile_path.parent, self._require_string(document, "boundary_file"))
        self._verify_hash(boundary_path, self._require_string(document, "boundary_sha256"), "boundary")
        boundary = self._load_json(boundary_path, "boundary")
        if boundary.get("type") not in {"Feature", "FeatureCollection", "Polygon", "MultiPolygon"}:
            raise ManifestValidationError("boundary must be GeoJSON polygonal content")
        scale_path = self._safe_path(profile_path.parent, self._require_string(document, "scale_error_evaluation_metadata"))
        self._verify_hash(scale_path, self._require_string(document, "scale_metadata_sha256"), "scale metadata")
        self._load_json(scale_path, "scale metadata")
        try:
            return ReleaseProfile(**document)
        except TypeError as exc:
            raise ManifestValidationError("profile has unsupported fields") from exc

    def _verify_profile_crs(self, document: dict[str, Any]) -> None:
        pyproj = self._dependency("pyproj")
        try:
            grid = pyproj.CRS.from_wkt(self._require_string(document, "crs_wkt2"))
            equal_area = pyproj.CRS.from_wkt(self._require_string(document, "equal_area_crs_wkt2"))
        except Exception as exc:
            raise ManifestValidationError("profile contains an invalid CRS WKT2 definition") from exc
        if not grid.is_projected or not equal_area.is_projected:
            raise ManifestValidationError("grid and equal-area CRSs must be projected")

    @staticmethod
    def _dependency(module_name: str) -> Any:
        try:
            return importlib.import_module(module_name)
        except ImportError as exc:
            raise RegistryDependencyError(
                "signed registry loading requires the 'registry' optional dependency group"
            ) from exc

    def _safe_path(self, base: Path, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path:
            raise ManifestValidationError("artifact path must be a non-empty relative string")
        candidate = (base / relative_path).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise ManifestValidationError("artifact path escapes registry root")
        return candidate

    @staticmethod
    def _load_json(path: Path, label: str) -> dict[str, Any]:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ManifestValidationError(f"cannot read valid JSON {label}: {path}") from exc
        if not isinstance(document, dict):
            raise ManifestValidationError(f"{label} must be a JSON object")
        return document

    @staticmethod
    def _verify_hash(path: Path, expected_hash: str, label: str) -> None:
        if not isinstance(expected_hash, str) or len(expected_hash) != 64 or any(char not in "0123456789abcdef" for char in expected_hash):
            raise ManifestValidationError(f"{label} hash must be a lowercase SHA-256 digest")
        try:
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ArtifactHashMismatchError(f"cannot read {label} artifact: {path}") from exc
        if actual_hash != expected_hash:
            raise ArtifactHashMismatchError(f"{label} SHA-256 mismatch: {path}")

    @staticmethod
    def _require_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
        value = document.get(key)
        if not isinstance(value, dict):
            raise ManifestValidationError(f"{key} must be an object")
        return value

    @staticmethod
    def _require_list(document: dict[str, Any], key: str) -> list[Any]:
        value = document.get(key)
        if not isinstance(value, list):
            raise ManifestValidationError(f"{key} must be an array")
        return value

    @staticmethod
    def _require_string(document: dict[str, Any], key: str) -> str:
        value = document.get(key)
        if not isinstance(value, str) or not value:
            raise ManifestValidationError(f"{key} must be a non-empty string")
        return value
