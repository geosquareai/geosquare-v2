#!/usr/bin/env python3
"""Build a staged static national-datum GeoSquare successor candidate.

This tool intentionally copies the repository into an ignored staging directory
and never edits the published 0.1.0rc1 release inputs under release/ or src/.
It rebuilds only the domains with usable static EPSG geographic datum bases.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pyproj
from pyproj import CRS, Proj, Transformer
from pyproj.crs import ProjectedCRS
from pyproj.crs.coordinate_operation import (
    EquidistantCylindricalConversion,
    LambertConformalConic2SPConversion,
    TransverseMercatorConversion,
)

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "release" / "artifacts" / "phase-datum-rc2"
PROJECT = STAGING / "project"
RELEASE = PROJECT / "release"
PROFILES = RELEASE / "profiles"
SCALE = RELEASE / "scale"
BOUNDARIES = RELEASE / "boundaries"
DB = PROJECT / "src" / "geosquare_v2" / "db" / "registry.db"
SIG = PROJECT / "src" / "geosquare_v2" / "db" / "registry.db.sig"
PRIVATE_KEY = Path(
    "/Users/sawungrana/Documents/map/geosquare/geosquare-system-v2/"
    "_gsq_v2/geosquare-registry-private.pem"
)
KEY_ID = "geosquare-registry-2026-09"
PROFILE_VERSION = "2.1.0-rc2-static-datum"
PACKAGE_VERSION = "0.1.0rc2"

# These geographic datum bases are available as EPSG/PROJ definitions and are
# suitable for a static technical candidate. The projection parameters are
# retained from the current GeoSquare candidate and rebuilt against the new base.
DATUM_BASES: dict[str, tuple[int, str, str]] = {
    "BN": (5246, "GDBD2009", "GEOSQUARE:BN_GDBD2009_LCC_V2"),
    "ID": (9470, "SRGI2013 static realization 2012.0", "GEOSQUARE:ID_SRGI2013_STATIC2012_LCC_V2"),
    "LA": (4678, "Lao 1997", "GEOSQUARE:LA_LAO1997_LCC_V2"),
    "MY": (4742, "GDM2000", "GEOSQUARE:MY_GDM2000_LCC_V2"),
    "PH": (4683, "PRS92", "GEOSQUARE:PH_PRS92_LCC_V2"),
    "SG": (4757, "SVY21", "GEOSQUARE:SG_SVY21_TM_V2"),
}
STATIC_REFERENCE_EPOCHS = {"ID": 2012.0}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def copy_ignore(src: str, names: list[str]) -> set[str]:
    source = Path(src)
    ignored: set[str] = set()
    for name in names:
        path = source / name
        if name in {".git", ".venv", ".pytest_cache", ".hypothesis", ".mypy_cache", ".ruff_cache", "build", ".DS_Store"}:
            ignored.add(name)
        elif name.endswith(".egg-info"):
            ignored.add(name)
        elif path == ROOT / "release" / "artifacts":
            ignored.add(name)
    return ignored


def copy_repository() -> None:
    if STAGING.exists():
        raise SystemExit(f"staging directory already exists; remove or rename it first: {STAGING}")
    shutil.copytree(ROOT, PROJECT, ignore=copy_ignore)


def parameter_map(crs: CRS) -> dict[int, float]:
    result: dict[int, float] = {}
    operation = crs.coordinate_operation.to_json_dict()
    for parameter in operation["parameters"]:
        identifier = parameter.get("id", {})
        code = identifier.get("code")
        if code is not None:
            result[int(code)] = float(parameter["value"])
    return result


def static_geodetic_base(code: str, base_code: int) -> CRS:
    base = CRS.from_epsg(base_code)
    if code != "ID":
        return base
    # EPSG:9470 is dynamic and declares FRAMEEPOCH[2012]. For this
    # candidate, materialize a named static realization at that epoch.
    wkt = base.to_wkt("WKT2_2019")
    wkt = wkt.replace(
        'GEOGCRS["SRGI2013",DYNAMIC[FRAMEEPOCH[2012]],',
        'GEOGCRS["SRGI2013 static realization 2012.0",',
        1,
    )
    wkt = wkt.replace(',ID["EPSG",9470]]', "]", 1)
    return CRS.from_wkt(wkt)


def custom_projected_crs(code: str, profile: dict[str, Any]) -> CRS:
    base_code, base_name, authority = DATUM_BASES[code]
    current = CRS.from_wkt(profile["crs_wkt2"])
    params = parameter_map(current)
    operation_name = current.coordinate_operation.method_name
    base = static_geodetic_base(code, base_code)

    if operation_name == "Lambert Conic Conformal (2SP)":
        conversion = LambertConformalConic2SPConversion(
            latitude_first_parallel=params[8823],
            latitude_second_parallel=params[8824],
            latitude_false_origin=params[8821],
            longitude_false_origin=params[8822],
            easting_false_origin=params[8826],
            northing_false_origin=params[8827],
        )
    elif operation_name == "Transverse Mercator":
        conversion = TransverseMercatorConversion(
            latitude_natural_origin=params[8801],
            longitude_natural_origin=params[8802],
            false_easting=params[8806],
            false_northing=params[8807],
            scale_factor_natural_origin=params[8805],
        )
    elif operation_name == "Equidistant Cylindrical":
        conversion = EquidistantCylindricalConversion(
            latitude_first_parallel=params[8823],
            latitude_natural_origin=params.get(8801, 0.0),
            longitude_natural_origin=params[8802],
            false_easting=params[8806],
            false_northing=params[8807],
        )
    else:
        raise ValueError(f"unsupported projection method for {code}: {operation_name}")

    return ProjectedCRS(
        conversion,
        name=f"GeoSquare {code} / {base_name} custom metric V2",
        geodetic_crs=base,
    )


def make_scale_metadata(code: str, boundary_path: Path, crs_wkt2: str) -> dict[str, Any]:
    # Import the existing review sampler without changing its implementation.
    sys.path.insert(0, str(ROOT / "tools"))
    from evaluate_priority_profiles import boundary_rings, sampled_boundary

    rings = boundary_rings(boundary_path)
    points = sampled_boundary(rings, max_vertices=20_000)
    crs = CRS.from_wkt(crs_wkt2)
    projection = Proj(crs)
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


def update_profiles() -> list[dict[str, Any]]:
    manifest = json.loads((RELEASE / "registry.v2.json").read_text(encoding="utf-8"))
    manifest_domains: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for entry in manifest["domains"]:
        code = entry["domain_code"]
        profile_path = RELEASE / entry["profile_file"]
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["profile_version"] = PROFILE_VERSION
        if code in DATUM_BASES:
            crs = custom_projected_crs(code, profile)
            profile["grid_crs"] = DATUM_BASES[code][2]
            profile["crs_authority"] = DATUM_BASES[code][2]
            profile["crs_wkt2"] = crs.to_wkt("WKT2_2019")
            profile["reference_epoch"] = STATIC_REFERENCE_EPOCHS.get(code, profile.get("reference_epoch"))
            profile["datum_base_authority"] = f"EPSG:{DATUM_BASES[code][0]}"
            profile["epoch_policy"] = "static_realization"
            if code == "ID":
                profile["input_coordinate_policy"] = (
                    "Coordinates must be pre-normalized to the SRGI2013 static realization at epoch 2012.0; "
                    "runtime does not perform dynamic epoch transformation."
                )
            boundary_path = RELEASE / "boundaries" / f"{code}_full.geojson"
            scale_path = SCALE / f"{code}_GRID_V2.json"
            scale = make_scale_metadata(code, boundary_path, profile["crs_wkt2"])
            write_json(scale_path, scale)
            profile["scale_error_max_pct"] = scale["max_error_pct"]
            profile["scale_metadata_sha256"] = sha256(scale_path)
            results.append(
                {
                    "domain": code,
                    "datum_base": DATUM_BASES[code][0],
                    "authority": DATUM_BASES[code][2],
                    "scale_error_max_pct": scale["max_error_pct"],
                }
            )
        else:
            results.append(
                {
                    "domain": code,
                    "datum_base": None,
                    "authority": profile["crs_authority"],
                    "scale_error_max_pct": profile["scale_error_max_pct"],
                }
            )
        write_json(profile_path, profile)
        manifest_domains.append(
            {
                "domain_id": profile["domain_id"],
                "domain_code": code,
                "profile_file": entry["profile_file"],
                "profile_sha256": sha256(profile_path),
            }
        )

    manifest["domains"] = manifest_domains
    manifest["release_status"] = "candidate"
    write_json(RELEASE / "registry.v2.json", manifest)
    return results


def update_package_version() -> None:
    pyproject = PROJECT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8").replace('version = "0.1.0rc1"', 'version = "0.1.0rc2"', 1)
    pyproject.write_text(text, encoding="utf-8")
    init_path = PROJECT / "src" / "geosquare_v2" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8").replace('__version__ = "0.1.0rc1"', '__version__ = "0.1.0rc2"', 1)
    init_path.write_text(init_text, encoding="utf-8")


def build_registry() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from geosquare_v2.db import MigrationTool

    MigrationTool(RELEASE).migrate(PROJECT / "src" / "geosquare_v2" / "db" / "registry.db")
    subprocess.run(
        [
            sys.executable,
            str(PROJECT / "tools" / "sign_registry_db.py"),
            "--private-key",
            str(PRIVATE_KEY),
            "--db",
            str(DB),
            "--output",
            str(SIG),
            "--key-id",
            KEY_ID,
        ],
        check=True,
    )


def main() -> None:
    copy_repository()
    results = update_profiles()
    update_package_version()
    build_registry()
    print(f"Staged successor project: {PROJECT}")
    print(f"Profile version: {PROFILE_VERSION}; package version: {PACKAGE_VERSION}")
    for result in results:
        print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
