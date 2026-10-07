This guide follows the storage rules in [CELL_DATASET_CONTRACT.md](cell-dataset-contract.md). The machine-readable manifest schema is [schemas/cell-dataset-manifest-v1.schema.json](../schemas/cell-dataset-manifest-v1.schema.json).

GeoSquare data work has two separate steps:

```text
input geometry or table
  → assign cells
  → aggregate values
```

Do not hide both steps inside one unclear function.

## 1. Geometry to cells

### Point

A point maps to one cell.

Use:

```python
service.point_to_cell(domain, longitude, latitude, level)
```

### Polygon to many cells

Use:

```python
records = service.polygon_to_cells(
    domain,
    polygon,
    source_crs,
    level,
    coverage_mode="EQUAL_AREA",
)
```

Each record has:

```text
cell
gid
uri
coverage_ratio
```

`coverage_ratio` is the fraction of the cell covered by the input polygon.

Coverage modes:

- `GRID_PLANAR`: measure in the grid CRS;
- `EQUAL_AREA`: measure in the profile equal-area CRS.

Use `EQUAL_AREA` for published statistics and coastal work.

### Polygon to one cell

Use:

```python
record = service.polygon_to_cell(
    domain,
    polygon,
    source_crs,
    level,
    selection="centroid",
)
```

Options:

- `centroid`: fastest;
- `representative_point`: chooses a point inside the polygon;
- `largest_overlap`: chooses the cell with the largest polygon overlap.

A one-cell assignment is not a replacement for polygon coverage. Use it only when the application wants one representative cell.

### Line to cells

Use:

```python
records = service.line_to_cells(
    domain,
    line,
    source_crs,
    level,
)
```

Each record has `length_ratio`.

The ratio is the line length inside the cell divided by the clipped input line length. Current line length uses the projected grid CRS.

## 2. Geometry output

Geometry is optional because it can be expensive.

```python
records = service.polygon_to_cells(
    "ID",
    polygon,
    "EPSG:4326",
    level=12,
    output_geometry=True,
    geometry_crs="EPSG:4326",
    geometry_format="wkt",
)
```

Output formats:

```text
shapely
wkt
wkb
```

Output CRS choices:

```text
grid
projected
EPSG:4326
OGC:CRS84
any CRS accepted by PyProj
```

The projected grid square remains the authoritative geometry.

## 3. Tables to cells

Use:

```python
assigned = service.table_to_cells(
    "points.parquet",
    "ID",
    level=12,
    longitude_column="longitude",
    latitude_column="latitude",
    keep_columns=["asset_id", "value", "timestamp"],
)
```

If `keep_columns` is omitted, all input fields are kept.

Supported formats:

- CSV;
- XLSX;
- Parquet; and
- Pandas DataFrame.

For large CSV files:

```python
from geosquare_v2.table import table_to_cells_chunks

for chunk in table_to_cells_chunks(
    "large_points.csv",
    service,
    "ID",
    level=12,
    chunksize=100_000,
    longitude_column="longitude",
    latitude_column="latitude",
):
    write_chunk(chunk)
```

The cell columns are added. Original value fields are not removed.

## 4. Boundary filtering for tables

Point tables use `COVERS_POINT`.

```python
assigned = service.table_to_cells(
    "points.csv",
    "ID",
    level=12,
    boundary_policy="COVERS_POINT",
    drop_outside_boundary=False,
)
```

With `drop_outside_boundary=False`, the output includes a boolean boundary column.

With `drop_outside_boundary=True`, outside rows are removed.

## 5. Numeric values

Declare the value meaning before aggregating.

```text
COUNT
TOTAL
DENSITY
MEASUREMENT
RATE
```

Use:

```python
summary = service.aggregate_to_cells(
    assigned,
    value_type="numeric",
    value_column="value",
    rule="weighted_mean",
    weight_column="coverage_ratio",
)
```

Numeric rules:

- `count`;
- `sum`;
- `weighted_sum`;
- `mean`;
- `weighted_mean`;
- `median`;
- `min`;
- `max`;
- `std`; and
- `quantile`.

Examples:

### Total value

If a polygon value is a total, allocate it by overlap:

```text
cell_total = source_total × coverage_ratio
```

Use `weighted_sum`.

### Density

A density is not a total.

Example:

```text
100 people per km²
```

Use an area-aware calculation. Do not sum density values as if they were counts.

### Measurements

For sensor values or measurements, use `mean`, `weighted_mean`, `median`, or another explicit rule.

## 6. Categories

Use:

```python
summary = service.aggregate_to_cells(
    assigned,
    value_type="categorical",
    value_column="land_use",
    rule="largest_overlap",
    weight_column="coverage_ratio",
)
```

Category rules:

- `largest_overlap`: choose the category with the largest weight;
- `majority_weighted`: weighted majority;
- `centroid_category`: category at the representative point;
- `priority_order`: use an explicit priority list;
- `all_categories`: return a category-to-share mapping.

Ties must use a deterministic rule.

## 7. Ordinal values

Ordinal values have order, but they are not normal measurements.

```python
summary = service.aggregate_to_cells(
    assigned,
    value_type="ordinal",
    value_column="risk",
    priority_order=["high", "medium", "low"],
    weight_column="coverage_ratio",
)
```

Do not average `low`, `medium`, and `high` as if they were ordinary numbers unless the application defines that mapping explicitly.

## 8. Ranges

Use a separate lower and upper field:

```python
summary = service.aggregate_to_cells(
    assigned,
    value_type="range",
    lower_column="min_value",
    upper_column="max_value",
    rule="full_range",
)
```

Range rules:

- `weighted_mean`;
- `min`;
- `max`;
- `full_range`; and
- `distribution`.

`full_range` returns the minimum lower bound and maximum upper bound in each cell.

## 9. Fast and accurate modes

### Fast mode

Use:

- point or centroid assignment;
- no geometry output;
- spatial indexes;
- chunked table processing.

### Accurate mode

Use:

- exact polygon intersection;
- `EQUAL_AREA` coverage;
- length-weighted line coverage;
- explicit value semantics; and
- coverage metadata.

Always record the chosen mode with published results.

## 10. Output quality fields

For auditable work, retain:

```text
source_id
profile_version
boundary_version or boundary_sha256
level
coverage_ratio or length_ratio
assignment_rule
aggregation_rule
value_semantics
```

These fields explain why two datasets may produce different grid values.
