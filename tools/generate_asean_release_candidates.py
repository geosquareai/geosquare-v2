#!/usr/bin/env python3
"""Generate an unsigned 11-domain ASEAN GeoSquare release candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyproj
from pyproj import CRS, Transformer

from evaluate_priority_profiles import boundary_rings, sampled_boundary
from geosquare_v2.db import MigrationTool

ROOT = Path(__file__).resolve().parents[1]
BOUNDARIES = ROOT / "release" / "boundaries"
PROFILES = ROOT / "release" / "profiles"
SCALE = ROOT / "release" / "scale"
DB_ROOT = ROOT / "src" / "geosquare_v2" / "db"
DOMAIN_CANDIDATES = PROFILES / "ASEAN_DOMAIN_CANDIDATES.json"
INITIAL_CANDIDATES = SCALE / "ASEAN_PROJECTION_CANDIDATES.json"
PRIORITY_REVIEW = SCALE / "ASEAN_PRIORITY_PROFILE_REVIEW.json"
PRIORITY_DECISIONS = PROFILES / "ASEAN_PRIORITY_PROFILE_DECISIONS.json"
METADATA = BOUNDARIES / "ASEAN_BOUNDARY_METADATA.json"
MANIFEST = ROOT / "release" / "registry.v2.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def selected_candidates() -> list[dict[str, Any]]:
    domains = json.loads(DOMAIN_CANDIDATES.read_text(encoding="utf-8"))["domains"]
    initial = {item["domain_code"]: item for item in json.loads(INITIAL_CANDIDATES.read_text(encoding="utf-8"))}
    priority = json.loads(PRIORITY_REVIEW.read_text(encoding="utf-8"))
    decisions = json.loads(PRIORITY_DECISIONS.read_text(encoding="utf-8"))["profiles"]
    priority_by_key = {(item["domain_code"], item["candidate"]): item for item in priority}
    decisions_by_code = {item["domain_code"]: item for item in decisions}
    result = []
    for domain in domains:
        code = domain["domain_code"]
        decision = decisions_by_code.get(code)
        if decision:
            candidate = priority_by_key[(code, decision["recommended_candidate"])]
            candidate_name = decision["recommended_candidate"]
        else:
            candidate = initial[code]
            candidate_name = candidate["projection_family"]
        result.append({**domain, "candidate": candidate, "candidate_name": candidate_name})
    return result


def profile_crs(candidate: dict[str, Any], code: str, name: str, candidate_name: str) -> tuple[str, str]:
    wkt = candidate["crs_wkt2"]
    if candidate_name == "existing_profile":
        authority = json.loads((PROFILES / f"{code}.v2.json").read_text(encoding="utf-8"))["crs_authority"]
        return authority, wkt
    safe_name = candidate_name.upper().replace("-", "_")
    authority = f"GEOSQUARE:{code}_{safe_name}_V2"
    if 'PROJCRS["unknown"' in wkt:
        wkt = wkt.replace(
            'PROJCRS["unknown"',
            f'PROJCRS["Geosquare {name} / {candidate_name} V2"',
            1,
        )
    return authority, wkt


def make_scale_metadata(
    code: str,
    boundary_path: Path,
    crs_wkt2: str,
) -> dict[str, Any]:
    rings = boundary_rings(boundary_path)
    points = sampled_boundary(rings, max_vertices=20_000)
    crs = CRS.from_wkt(crs_wkt2)
    projection = pyproj.Proj(crs)
    maximum = (-1.0, None, None, None)
    for longitude, latitude in points:
        factors = projection.get_factors(longitude, latitude)
        error = 100 * max(abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1))
        if error > maximum[0]:
            maximum = (error, longitude, latitude, factors)
    error, longitude, latitude, factors = maximum
    transformer = Transformer.from_crs("OGC:CRS84", crs, always_xy=True)
    projected = [transformer.transform(lon, lat) for lon, lat in points]
    root_min = -25_000_000.0
    root_max = 25_000_000.0
    if not all(root_min <= x <= root_max and root_min <= y <= root_max for x, y in projected):
        raise ValueError(f"{code} boundary does not fit inside the V2 root")
    return {
        "domain_code": code,
        "algorithm": "projection_factors_max_directional_full_boundary_v2",
        "proj_version": pyproj.proj_version_str,
        "pyproj_version": pyproj.__version__,
        "boundary_sha256": sha256(boundary_path),
        "sample_count": len(points),
        "max_error_pct": error,
        "max_error_coordinate_crs84": [longitude, latitude],
        "meridional_scale": factors.meridional_scale,
        "parallel_scale": factors.parallel_scale,
    }


def main() -> None:
    metadata = {item["domain_code"]: item for item in json.loads(METADATA.read_text(encoding="utf-8"))}
    equal_area = CRS.from_epsg(8857)
    manifest_domains = []
    profiles = []

    for domain in selected_candidates():
        code = domain["domain_code"]
        name = domain["name"]
        candidate_name = domain["candidate_name"]
        candidate = domain["candidate"]
        boundary_path = BOUNDARIES / f"{code}_full.geojson"
        if not boundary_path.is_file():
            raise FileNotFoundError(boundary_path)
        crs_authority, crs_wkt2 = profile_crs(candidate, code, name, candidate_name)
        scale_path = SCALE / f"{code}_GRID_V2.json"
        scale_metadata = make_scale_metadata(code, boundary_path, crs_wkt2)
        write_json(scale_path, scale_metadata)

        existing_profile_path = PROFILES / f"{code}.v2.json"
        existing = json.loads(existing_profile_path.read_text(encoding="utf-8")) if existing_profile_path.is_file() else {}
        reference_epoch = existing.get("reference_epoch") if candidate_name == "existing_profile" else None
        boundary_record = metadata[code]
        profile = {
            "domain_id": domain["domain_id_candidate"],
            "domain_code": code,
            "name": name,
            "origin_x_m": -25_000_000.0,
            "origin_y_m": -25_000_000.0,
            "root_side_m": 50_000_000.0,
            "reference_epoch": reference_epoch,
            "grid_crs": crs_authority,
            "equal_area_crs": "EPSG:8857",
            "profile_version": "2.0.0-rc.2-asean",
            "crs_authority": crs_authority,
            "crs_wkt2": crs_wkt2,
            "equal_area_crs_authority": "EPSG:8857",
            "equal_area_crs_wkt2": equal_area.to_wkt("WKT2_2019"),
            "min_level": 0,
            "max_level": 14,
            "scale_error_max_pct": scale_metadata["max_error_pct"],
            "scale_error_method": scale_metadata["algorithm"],
            "scale_error_evaluation_metadata": f"../scale/{scale_path.name}",
            "scale_metadata_sha256": sha256(scale_path),
            "boundary_source_crs": "OGC:CRS84",
            "boundary_file": f"../boundaries/{boundary_path.name}",
            "boundary_sha256": sha256(boundary_path),
            "boundary_source": (
                f"geoBoundaries gbOpen {boundary_record['iso3']} ADM0, "
                f"{boundary_record['boundary_id']}, {boundary_record['boundary_year']}, "
                f"{boundary_record['boundary_license']}"
            ),
        }
        profile_path = PROFILES / f"{code}.v2.json"
        write_json(profile_path, profile)
        manifest_domains.append(
            {
                "domain_id": profile["domain_id"],
                "domain_code": code,
                "profile_file": f"profiles/{profile_path.name}",
                "profile_sha256": sha256(profile_path),
            }
        )
        profiles.append(profile)
        print(f"Generated {code}: {candidate_name}, scale error {scale_metadata['max_error_pct']:.4f}%")

    proj_db_path = Path(pyproj.datadir.get_data_dir()) / "proj.db"
    manifest = {
        "registry_version": "2.0.0",
        "release_status": "candidate",
        "proj_version_exact": pyproj.proj_version_str,
        "proj_db_sha256": sha256(proj_db_path),
        "required_proj_grids": [],
        "domains": manifest_domains,
    }
    write_json(MANIFEST, manifest)
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    destination = DB_ROOT / "registry.db"
    MigrationTool(ROOT / "release").migrate(destination, manifest_file=MANIFEST.name)
    print(f"Generated {len(profiles)}-domain unsigned registry: {destination}")
    print("Review all profiles and scale metadata before signing the database.")


if __name__ == "__main__":
    main()
