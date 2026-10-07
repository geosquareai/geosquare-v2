# V1 to V2 migration

V1 and V2 are different ID systems.

There is no safe string conversion from a V1 GID to a V2 GID.

Use `geosquare_v2.migration.V1MigrationAdapter` instead.

## Point migration

If the original coordinates exist, use them. This is the preferred method.

```python
from pyproj import CRS, Transformer

from geosquare_v2.migration import V1MigrationAdapter

to_grid = Transformer.from_crs(
    CRS.from_epsg(4326),
    CRS.from_user_input(profile.crs_wkt2),
    always_xy=True,
)

adapter = V1MigrationAdapter(grid, to_grid)
record = adapter.migrate_point(
    source_gid="J3N2M3T8M342",
    longitude=106.894082,
    latitude=-6.26109,
    target_level=12,
)

print(record.target_uri)
print(record.method)  # source_coordinates
```

If only a V1 GID exists, the adapter decodes the legacy cell and uses its centroid.

```python
record = adapter.migrate_point(
    source_gid="H",
    target_level=9,
)

print(record.method)  # v1_cell_centroid
```

This is an approximation. The result records the method and the legacy bounds.

## Area migration

A V1 cell can become many V2 cells.

```python
records = adapter.migrate_area(
    "H",
    target_level=9,
    coverage_mode="EQUAL_AREA",
    min_coverage=0.01,
)

for record in records:
    print(record.target_uri, record.coverage_ratio)
```

The adapter:

1. decodes the V1 cell;
2. builds its legacy cell geometry;
3. runs the V2 polyfill; and
4. returns one record per target V2 cell.

## Provenance

Every `MigrationRecord` keeps:

- source system and version;
- source V1 GID;
- target V2 URI;
- target domain and profile version;
- target level;
- migration method;
- source CRS;
- representative point;
- legacy bounds;
- coverage mode; and
- coverage ratio.

Store these fields with the migrated data. Do not keep only the replacement GID.

## Important limits

- V1’s coordinate space is legacy behavior. It is not a modern CRS contract.
- A V1 GID without original coordinates has lower confidence.
- Area migration can produce one-to-many results.
- Country boundary filtering is not automatic. Apply a named V2 boundary policy after migration.
- V1 level 15 / 1 m does not map to a V2 level. Choose a V2 target level explicitly.
