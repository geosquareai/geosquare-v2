# GeoSquare V2 API guide

This is the normal application API.

Use `GeosquareService` when you want simple calls. Use `GeosquareGrid` when you need direct control over CRS and projected coordinates.

## 1. Install

Core and registry:

```zsh
python -m pip install -e ".[registry]"
```

All geometry, table, batch, and test features:

```zsh
python -m pip install -e ".[analytics,registry,table,dev]"
```

## 2. Load a verified registry

```python
import base64
import json
from pathlib import Path

from geosquare_v2 import DbRegistryLoader, GeosquareService

project_root = Path(".")
encoded_keys = json.loads((project_root / "release/registry-trust.json").read_text())
trust = {
    key_id: base64.b64decode(value, validate=True)
    for key_id, value in encoded_keys.items()
}

registry = DbRegistryLoader(
    trust,
    project_root / "src/geosquare_v2/db",
    boundary_root=project_root / "src/geosquare_v2/data/registry",
    verify_boundaries=True,
).load()

service = GeosquareService(
    registry,
    boundary_root=project_root / "src/geosquare_v2/data/registry",
)
```

The loader checks:

- the detached database signature;
- profile and scale hashes;
- boundary hashes when enabled;
- CRS definitions; and
- the pinned PROJ environment.

A local PROJ resource mismatch is a release-environment problem. Do not bypass it for production.

## 3. Point to cell

```python
cell = service.point_to_cell(
    "ID",
    longitude=106.8456,
    latitude=-6.2088,
    level=9,
)
```

The result is an `IndexedCell` with:

```text
cell
 gid
 uri
 projected_bounds
 cell_edge_m
 profile_version
 scale_error_max_pct
 boundary_policy
```

Use the URI in durable data:

```python
print(cell.uri)
# geosquare:v2:ID:<gid>
```

The service creates the CRS transformer automatically. It uses `always_xy=True`.

## 4. Boundary-aware point indexing

```python
from geosquare_v2 import BoundaryPredicate

cell = service.point_to_cell(
    "ID",
    106.8456,
    -6.2088,
    level=9,
    boundary_policy=BoundaryPredicate.COVERS_POINT,
)
```

A point outside the operational boundary raises `OutsideOperationalBoundaryError`.

Without a boundary policy, the mathematical root is used.

## 5. Decode a cell

Full URI:

```python
cell = service.describe("geosquare:v2:ID:2G4M3N8P")
```

Bare GID with a domain:

```python
cell = service.describe("2G4M3N8P", domain_code="ID")
```

Parse a URI without loading a registry:

```python
from geosquare_v2 import parse_uri

domain, gid = parse_uri("geosquare:v2:ID:2G4M3N8P")
```

A parser only splits the URI. A registry-backed service is still needed to validate the GID for a real domain.

## 6. Geometry

One cell:

```python
geometry = service.cell_to_geometry(
    cell.uri,
    output_crs="EPSG:4326",
    geometry_format="wkt",
)
```

Many cells:

```python
geometries = service.cells_to_geometry(
    [cell.uri, other_cell.uri],
    output_crs="grid",
    geometry_format="shapely",
)
```

Supported output formats:

```text
shapely
wkt
wkb
```

Supported CRS choices include:

```text
grid
projected
EPSG:4326
OGC:CRS84
any valid CRS accepted by PyProj
```

## 7. Polygon and line conversion

Polygon to many cells:

```python
records = service.polygon_to_cells(
    "ID",
    polygon,
    "EPSG:4326",
    level=12,
    coverage_mode="EQUAL_AREA",
    output_geometry=False,
)
```

Each record contains a cell, URI, GID, and `coverage_ratio`.

Polygon to one cell:

```python
record = service.polygon_to_cell(
    "ID",
    polygon,
    "EPSG:4326",
    level=12,
    selection="largest_overlap",
)
```

Selection options:

```text
centroid
representative_point
largest_overlap
```

Line to many cells:

```python
records = service.line_to_cells(
    "ID",
    line,
    "EPSG:4326",
    level=12,
)
```

Line records contain `length_ratio`.

A line must have positive-length overlap with a cell. A corner touch does not count.

## 8. Neighbours and distance

```python
ring = service.cell_neighbours(cell.uri, 1)
disk = service.cell_neighbours(cell.uri, 2, kind="disk")
distance_m = service.cell_distance(cell.uri, ring[0].uri)
```

Rules:

- rings and disks are clipped to the mathematical root;
- boundary filtering is optional and explicit;
- distance requires the same domain and level;
- distance is Euclidean distance in the profile grid CRS.

## 9. Table data

```python
assigned = service.table_to_cells(
    "points.parquet",
    "ID",
    level=12,
    longitude_column="longitude",
    latitude_column="latitude",
    keep_columns=["asset_id", "value"],
)
```

Supported inputs:

- CSV;
- XLSX;
- Parquet; and
- Pandas DataFrame.

The output preserves selected source fields and adds:

```text
domain
level
x_idx
y_idx
gid
uri
packed_id
```

## 10. Aggregate values

```python
summary = service.aggregate_to_cells(
    assigned,
    value_type="numeric",
    value_column="value",
    rule="weighted_mean",
)
```

See [data-and-aggregation.md](data-and-aggregation.md) for value semantics and weighting rules.

## 11. Low-level API

Use `GeosquareGrid` when you already have a profile and transformer:

```python
cell = grid.canonical_from_projected(x_m, y_m, level=12)
parent = grid.parent(cell)
children = grid.children(parent)
ring = grid.k_ring(cell, 1)
distance_m = grid.distance_m(cell, ring[0])
```

Low-level methods are useful for batch and warehouse code. They do not automatically apply country boundaries.
