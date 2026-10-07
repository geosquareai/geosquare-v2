# Boundaries and V1 migration

## 1. Country boundaries

A boundary is an operational filter.

It does not define the mathematical cell ID.

This separation keeps IDs stable and lets different applications choose different boundary rules.

## 2. Boundary policies

### `COVERS_POINT`

Use for points.

The boundary must cover the point. A point on the boundary is accepted.

### `CENTROID_COVERED`

Use for cells.

The cell center must be inside the boundary.

### `INTERSECTS`

Use for general maps and discovery.

The cell is kept if it touches or overlaps the boundary.

### `MIN_COVERAGE`

Use for controlled analysis.

The cell is kept only when its inside-boundary area reaches the selected threshold.

The current implementation measures this ratio in the grid CRS.

For high-accuracy statistics, also use equal-area polygon coverage and record the choice.

## 3. Load a verified boundary

```python
from geosquare_v2 import OperationalBoundary

boundary = OperationalBoundary.from_profile(
    grid,
    boundary_root="src/geosquare_v2/data/registry",
)
```

`from_profile()` checks the boundary SHA-256 stored in the verified profile.

You can also load a file directly:

```python
boundary = OperationalBoundary.from_file(
    "boundaries/ID.geojson",
    source_crs="OGC:CRS84",
    grid_crs=profile.crs_wkt2,
    expected_sha256=profile.boundary_sha256,
)
```

## 4. Boundary-aware operations

Point:

```python
cell = service.point_to_cell(
    "ID",
    106.8456,
    -6.2088,
    level=12,
    boundary_policy="COVERS_POINT",
)
```

Polygon:

```python
records = service.polygon_to_cells(
    "ID",
    polygon,
    "EPSG:4326",
    level=12,
    boundary_policy="INTERSECTS",
)
```

Neighbourhood:

```python
cells = service.cell_neighbours(
    cell.uri,
    1,
    boundary_policy="INTERSECTS",
)
```

The mathematical ring is calculated first. The boundary filter is applied second.

## 5. Boundary source rules

Boundary files must record:

- source URL;
- source organization;
- boundary year or version;
- license;
- SHA-256;
- simplification status; and
- legal or operational scope.

Simplified boundaries are useful for planning and display. They are not automatically suitable for legal or statistical work.

## 6. V1 and V2 are different systems

V1 and V2 use different:

- roots;
- level meanings;
- alphabets;
- coordinate behavior; and
- CRS assumptions.

Never convert a V1 GID by changing its prefix or characters.

## 7. Point migration

Use original coordinates whenever possible:

```python
record = adapter.migrate_point(
    source_gid="J3N2M3T8M342",
    longitude=106.894082,
    latitude=-6.26109,
    target_level=12,
)
```

If original coordinates are missing, the adapter uses the V1 cell centroid:

```python
record = adapter.migrate_point(
    source_gid="H",
    target_level=9,
)
```

This is approximate. The record stores the method and legacy bounds.

## 8. Area migration

One V1 cell can become many V2 cells:

```python
records = adapter.migrate_area(
    "H",
    target_level=9,
    coverage_mode="EQUAL_AREA",
    min_coverage=0.01,
)
```

Each output record contains:

- source V1 ID;
- target V2 URI;
- target domain and level;
- migration method;
- source CRS;
- representative point;
- legacy bounds;
- coverage mode; and
- coverage ratio.

## 9. Migration storage

Do not store only the replacement ID.

Keep a mapping record with:

```text
source_system
source_version
source_gid
target_system
target_version
target_uri
target_profile_version
target_level
migration_method
coverage_mode
coverage_ratio
provenance
```

## 10. Migration limits

- A V1 GID without coordinates has lower confidence.
- A V1 area can create many V2 cells.
- V1 level 15 / 1 m has no direct V2 equivalent.
- Boundary filtering must be selected explicitly after migration.
- The legacy V1 coordinate behavior is not a modern CRS guarantee.
