#!/usr/bin/env python3
"""Legacy ID/VN release generator.

For the current 11-domain ASEAN candidate, use
``tools/generate_asean_release_candidates.py`` instead.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterator

import pyproj
from pyproj import CRS, Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from geosquare_v2.db import MigrationTool  # noqa: E402

REGISTRY = ROOT / "src" / "geosquare_v2" / "data" / "registry"
BOUNDARIES = REGISTRY / "boundaries"
DB_ROOT = ROOT / "src" / "geosquare_v2" / "db"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def polygon_positions(geometry: dict) -> Iterator[tuple[float, float]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    polygons = coordinates if geometry_type == "MultiPolygon" else [coordinates]
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"unsupported geometry type: {geometry_type!r}")
    for polygon in polygons:
        for ring in polygon:
            for position in ring:
                yield float(position[0]), float(position[1])


def boundary_positions(path: Path, max_samples: int = 20_000) -> list[tuple[float, float]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("type") == "FeatureCollection":
        geometries = [feature["geometry"] for feature in document.get("features", [])]
    elif document.get("type") == "Feature":
        geometries = [document["geometry"]]
    else:
        geometries = [document]
    positions = [point for geometry in geometries for point in polygon_positions(geometry)]
    if not positions:
        raise ValueError(f"boundary contains no polygon positions: {path}")
    stride = max(1, len(positions) // max_samples)
    sampled = positions[::stride]
    if positions[-1] != sampled[-1]:
        sampled.append(positions[-1])
    return sampled


def projected_crs(name: str, geodetic_epsg: int, proj4: str) -> CRS:
    """Build a named custom projected CRS while retaining the official base geodetic CRS."""
    generated = CRS.from_proj4(proj4).to_wkt(version="WKT2_2019")
    base_geodetic = CRS.from_epsg(geodetic_epsg).geodetic_crs.to_wkt(version="WKT2_2019")
    base_geodetic = base_geodetic.replace("GEOGCRS[", "BASEGEOGCRS[", 1)
    _, remainder = generated.split("],CONVERSION", 1)
    result = f'PROJCRS["{name}",{base_geodetic},CONVERSION{remainder}'
    return CRS.from_wkt(result)


def scale_metadata(domain: str, boundary_path: Path, crs: CRS) -> dict:
    points = boundary_positions(boundary_path)
    projection = pyproj.Proj(crs)
    maximum = (-1.0, None, None, None)
    for longitude, latitude in points:
        factors = projection.get_factors(longitude, latitude)
        error = 100 * max(abs(factors.meridional_scale - 1), abs(factors.parallel_scale - 1))
        if error > maximum[0]:
            maximum = (error, longitude, latitude, factors)
    error, lon, lat, factors = maximum
    return {
        "domain_code": domain,
        "algorithm": "projection_factors_max_directional_boundary_vertices_v1",
        "proj_version": pyproj.proj_version_str,
        "pyproj_version": pyproj.__version__,
        "boundary_sha256": sha256(boundary_path),
        "sample_count": len(points),
        "max_error_pct": error,
        "max_error_coordinate_crs84": [lon, lat],
        "meridional_scale": factors.meridional_scale,
        "parallel_scale": factors.parallel_scale,
    }


def ensure_root_covers(boundary_path: Path, crs: CRS, origin_x: float, origin_y: float) -> None:
    transformer = Transformer.from_crs("OGC:CRS84", crs, always_xy=True)
    root_max_x, root_max_y = origin_x + 50_000_000.0, origin_y + 50_000_000.0
    for longitude, latitude in boundary_positions(boundary_path):
        x, y = transformer.transform(longitude, latitude)
        if not (origin_x <= x <= root_max_x and origin_y <= y <= root_max_y):
            raise ValueError(f"root does not cover boundary point {(longitude, latitude)}")


def profile_document(
    *,
    staging_root: Path,
    domain_id: int,
    domain_code: str,
    name: str,
    reference_epoch: float,
    crs_authority: str,
    crs: CRS,
    boundary_file: str,
    boundary_source: str,
    origin_x: float = -25_000_000.0,
    origin_y: float = -25_000_000.0,
) -> dict:
    boundary_path = staging_root / "boundaries" / f"{domain_code}.geojson"
    ensure_root_covers(boundary_path, crs, origin_x, origin_y)
    scale_path = staging_root / "scale" / f"{domain_code}_GRID_V2.json"
    write_json(scale_path, scale_metadata(domain_code, boundary_path, crs))
    return {
        "domain_id": domain_id,
        "domain_code": domain_code,
        "name": name,
        "origin_x_m": origin_x,
        "origin_y_m": origin_y,
        "root_side_m": 50_000_000.0,
        "reference_epoch": reference_epoch,
        "grid_crs": crs_authority,
        "equal_area_crs": "EPSG:8857",
        "profile_version": "2.0.0-rc.1",
        "crs_authority": crs_authority,
        "crs_wkt2": crs.to_wkt(version="WKT2_2019"),
        "equal_area_crs_authority": "EPSG:8857",
        "equal_area_crs_wkt2": CRS.from_epsg(8857).to_wkt(version="WKT2_2019"),
        "min_level": 0,
        "max_level": 14,
        "scale_error_max_pct": json.loads(scale_path.read_text(encoding="utf-8"))["max_error_pct"],
        "scale_error_method": "projection_factors_max_directional_boundary_vertices_v1",
        "scale_error_evaluation_metadata": f"../scale/{scale_path.name}",
        "scale_metadata_sha256": sha256(scale_path),
        "boundary_source_crs": "OGC:CRS84",
        "boundary_file": boundary_file,
        "boundary_sha256": sha256(boundary_path),
        "boundary_source": boundary_source,
    }


def main() -> None:
    id_crs = projected_crs(
        "Geosquare Indonesia / SRGI2013 Equidistant Cylindrical V2",
        9470,
        "+proj=eqc +lat_ts=0 +lat_0=0 +lon_0=118 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +type=crs",
    )
    vn_crs = projected_crs(
        "Geosquare Vietnam / VN-2000 Lambert Conformal Conic V2",
        4756,
        "+proj=lcc +lat_1=11 +lat_2=21 +lat_0=16 +lon_0=107.5 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +type=crs",
    )

    with tempfile.TemporaryDirectory() as tmp_name:
        staging_root = Path(tmp_name)
        # Boundaries are a permanent on-disk asset (unchanged by the SQLite migration);
        # stage a copy alongside the freshly generated profiles/scale metadata so hash
        # verification and relative-path resolution behave exactly like the legacy layout.
        shutil.copytree(BOUNDARIES, staging_root / "boundaries")

        id_profile = profile_document(
            staging_root=staging_root,
            domain_id=1,
            domain_code="ID",
            name="Indonesia",
            reference_epoch=2012.0,
            crs_authority="GEOSQUARE:ID_SRGI2013_EQC_V2",
            crs=id_crs,
            boundary_file="../boundaries/ID.geojson",
            boundary_source="geoBoundaries gbOpen IDN ADM0, IDN-ADM0-11942859, 2017, ODbL",
        )
        vn_profile = profile_document(
            staging_root=staging_root,
            domain_id=2,
            domain_code="VN",
            name="Vietnam",
            reference_epoch=2000.0,
            crs_authority="GEOSQUARE:VN_VN2000_LCC_V2",
            crs=vn_crs,
            boundary_file="../boundaries/VN.geojson",
            boundary_source="geoBoundaries gbOpen VNM ADM0, VNM-ADM0-46766057, 2016, CC-BY-4.0",
        )
        id_path = staging_root / "profiles" / "ID.v2.json"
        vn_path = staging_root / "profiles" / "VN.v2.json"
        write_json(id_path, id_profile)
        write_json(vn_path, vn_profile)

        proj_db = Path(pyproj.datadir.get_data_dir()) / "proj.db"
        manifest = {
            "registry_version": "2.0.0",
            "release_status": "candidate",
            "proj_version_exact": pyproj.proj_version_str,
            "proj_db_sha256": sha256(proj_db),
            "required_proj_grids": [],
            "domains": [
                {"domain_id": 1, "domain_code": "ID", "profile_file": "profiles/ID.v2.json", "profile_sha256": sha256(id_path)},
                {"domain_id": 2, "domain_code": "VN", "profile_file": "profiles/VN.v2.json", "profile_sha256": sha256(vn_path)},
            ],
        }
        write_json(staging_root / "registry.v2.json", manifest)

        DB_ROOT.mkdir(parents=True, exist_ok=True)
        destination = DB_ROOT / "registry.db"
        MigrationTool(staging_root).migrate(destination)

    print(f"Generated unsigned release candidate database: {destination}")
    print("Run tools/sign_registry_db.py to produce registry.db.sig before distributing it.")


if __name__ == "__main__":
    main()
