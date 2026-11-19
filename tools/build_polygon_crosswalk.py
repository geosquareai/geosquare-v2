"""Build a source-unit to GeoSquare-cell crosswalk from polygons in a parquet file.

Input: a parquet file with one row per source unit, a WGS 84 polygon column in WKB
(GeoParquet `geometry`), and a source id column. Example: Dukcapil village boundaries.

Output (in --out-dir):
- crosswalk.csv: sumber_id, gid, bobot. Area shares in the grid CRS; each source sums to 1.
- crosswalk_manifest.json: format 1.0 metadata, checked by validate_crosswalk before writing.
- sources.csv: sumber_id and the chosen value column, unchanged.

Weights come from the signed registry's explicit datum pipeline. No PROJ lookup is used.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from shapely import wkb
from shapely.ops import transform

from geosquare_v2.crs import wgs84_to_grid_transformer
from geosquare_v2.crosswalk import polygon_crosswalk_rows, validate_crosswalk
from geosquare_v2.db import DbRegistryLoader
from geosquare_v2.grid import GeosquareGrid

ROOT = Path(__file__).parents[1]
WEIGHT_KINDS = ("luas", "bangunan", "populasi", "lainnya")
REGISTRY_VERSION = "2.0.0"  # the registry this tool loads, the same as geosquare-platform


def _registry():
    encoded = json.loads((ROOT / "release/registry-trust.json").read_text(encoding="utf-8"))
    trust = {key: base64.b64decode(value, validate=True) for key, value in encoded.items()}
    return DbRegistryLoader(
        trust,
        ROOT / "src/geosquare_v2/db",
        boundary_root=ROOT / "src/geosquare_v2/data/registry",
    ).load()


def _source_id(value) -> str:
    if value is None:
        raise ValueError("source id is empty")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"source id {value!r} is not a whole number")
        return str(int(value))
    return str(value).strip()


def build(args) -> dict:
    registry = _registry()
    profile = registry.get(args.domain)
    grid = GeosquareGrid(profile)
    to_grid = wgs84_to_grid_transformer(profile)

    table = pq.read_table(args.source, columns=[args.id_column, args.value_column, args.geometry_column])
    records = table.to_pylist()
    polygons = []
    values = []
    for record in records:
        source_id = _source_id(record[args.id_column])
        geometry = wkb.loads(record[args.geometry_column])
        polygons.append((source_id, transform(to_grid.transform, geometry)))
        values.append((source_id, record[args.value_column]))

    rows = polygon_crosswalk_rows(polygons, grid, args.level)
    manifest = {
        "format_version": "1.0",
        "spec_version": "2.0",
        "domain_code": args.domain,
        "level": args.level,
        "weight_kind": args.weight_kind,
        "source_description": args.description,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "registry_version": REGISTRY_VERSION,
    }
    counts = validate_crosswalk(rows, manifest)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "crosswalk.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("sumber_id", "gid", "bobot"))
        for row in rows:
            writer.writerow((row["sumber_id"], row["gid"], repr(row["bobot"])))
    (args.out_dir / "crosswalk_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (args.out_dir / "sources.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("sumber_id", args.value_column))
        writer.writerows(values)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="parquet file with WKB geometry in WGS 84")
    parser.add_argument("--id-column", required=True, help="source unit id column")
    parser.add_argument("--value-column", required=True, help="value column copied to sources.csv")
    parser.add_argument("--geometry-column", default="geometry")
    parser.add_argument("--domain", required=True, help="registry domain code, for example ID")
    parser.add_argument("--level", type=int, required=True, help="GID level of the output cells")
    parser.add_argument("--weight-kind", required=True, choices=WEIGHT_KINDS)
    parser.add_argument("--description", required=True, help="source_description written to the manifest")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    counts = build(args)
    print(f"sources {counts['sources']}, rows {counts['rows']}, cells {counts['cells']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
