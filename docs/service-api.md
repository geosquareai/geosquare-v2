# Simple V2 service API

Use `GeosquareService` for normal application code.

It hides:

- profile lookup;
- CRS transformer setup;
- `always_xy=True`;
- GID encoding;
- versioned URI creation; and
- boundary loading.

## Setup

```python
import base64
import json
from pathlib import Path

from geosquare_v2 import DbRegistryLoader, GeosquareService

root = Path(".")
keys = json.loads((root / "release/registry-trust.json").read_text())
trust = {key_id: base64.b64decode(value) for key_id, value in keys.items()}

registry = DbRegistryLoader(
    trust,
    root / "src/geosquare_v2/db",
    boundary_root=root / "src/geosquare_v2/data/registry",
).load()

service = GeosquareService(
    registry,
    boundary_root=root / "src/geosquare_v2/data/registry",
)
```

## Index a point

```python
cell = service.point_to_cell(
    "ID",
    longitude=106.8456,
    latitude=-6.2088,
    level=9,
)

print(cell.uri)
print(cell.gid)
print(cell.cell_edge_m)
print(cell.projected_bounds)
print(cell.scale_error_max_pct)
```

The result contains the canonical cell and useful profile metadata.

## Apply the country boundary

Boundary filtering is opt-in.

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

If the point is outside the operational boundary, the service raises
`OutsideOperationalBoundaryError`.

## Decode a cell

Use a full URI in stored data:

```python
cell = service.describe("geosquare:v2:ID:2G4M3N8P")
```

A bare GID needs an explicit domain:

```python
cell = service.describe("2G4M3N8P", domain_code="ID")
```

## Neighbours and distance

```python
neighbours = service.cell_neighbours(cell.uri, 1)
distance_m = service.cell_distance(cell.uri, neighbours[0].uri)
```

The distance API currently requires cells from the same domain and level.

For boundary-aware results:

```python
neighbours = service.cell_neighbours(
    cell.uri,
    1,
    boundary_policy=BoundaryPredicate.INTERSECTS,
)
```

## Polyfill

```python
cells = service.polygon_to_cells(
    "ID",
    polygon,
    "EPSG:4326",
    level=9,
    boundary_policy=BoundaryPredicate.INTERSECTS,
    coverage_mode="EQUAL_AREA",
)
```

The result is a tuple of `(bare_gid, coverage_ratio)` pairs. Use the domain and V2 version from the request when storing the result, or wrap each GID as a full URI.

## Low-level API

`GeosquareGrid` remains available for GIS, batch, and warehouse code.

Use `GeosquareService` for application code. Use `GeosquareGrid` when you need direct control over profiles, transformers, or projected coordinates.

## Geometry conversion names

Use the names that describe the input and output:

```python
service.point_to_cell(...)
service.polygon_to_cells(...)
service.polygon_to_cell(...)
service.line_to_cells(...)
service.cell_to_geometry(...)
service.cells_to_geometry(...)
```

`polygon_to_cells()` returns area ratios.

`line_to_cells()` returns length ratios.

Use `output_geometry=True` when cell geometry is needed.

## Tables

```python
result = service.table_to_cells(
    "points.parquet",
    "ID",
    level=12,
    longitude_column="lon",
    latitude_column="lat",
    keep_columns=["asset_id", "value", "lon", "lat"],
    output_geometry=False,
)
```

The original fields stay in the result. Cell fields are added.

Supported input files:

- CSV;
- XLSX; and
- Parquet.

Use `table_to_cells_chunks()` for large CSV files.

## Aggregation

```python
result = service.aggregate_to_cells(
    result,
    value_type="numeric",
    value_column="value",
    rule="weighted_mean",
    weight_column="coverage_ratio",
)
```

Other value types are:

```text
categorical
ordinal
range
```

The aggregation rule must match the meaning of the value. A total, density, rate, and measurement are not interchangeable.
