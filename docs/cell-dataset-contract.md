# GeoSquare cell dataset contract

**Status:** proposed dataset format  
**Format version:** `1.0`  
**Grid system:** GeoSquare V2  
**Purpose:** Parquet datasets for sharing, storing, querying, and reading GeoSquare cell data

This document defines the format before the S3 reader and writer are implemented.

## 1. Goal

A user should be able to:

```text
source data
  → assign cells
  → aggregate values
  → write Parquet to S3
  → client reads the dataset
  → client validates the manifest
  → client optionally builds geometry
```

The data file should stay small.

The manifest should carry the context needed to interpret the IDs.

## 2. Dataset types

### `cell_values`

A final cell table.

It has one row per cell.

The `gid` must be unique within the dataset.

Example:

```text
gid,value
2G4M3N8P,123.4
2G4M3N8Q,98.1
```

Use this for published or already-aggregated data.

### `cell_contributions`

A source-to-cell table.

One source feature can produce many rows. The same `gid` can appear many times.

Example:

```text
source_id,gid,coverage_ratio,value
parcel-001,2G4M3N8P,0.60,100
parcel-001,2G4M3N8Q,0.40,100
```

Use this before aggregation.

A contribution dataset must have a stable `source_id` or `source_row` field.

## 3. Dataset scope

One dataset must use one:

- grid system;
- grid version;
- country domain;
- level; and
- profile version.

Do not mix `ID` and `VN` in one cell table unless the manifest explicitly describes a dataset collection. The first format version does not support mixed-domain cell tables.

Do not mix levels in one dataset.

If an application needs several countries or levels, use separate dataset paths:

```text
s3://bucket/dataset/domain=ID/level=12/
s3://bucket/dataset/domain=VN/level=12/
s3://bucket/dataset/domain=ID/level=9/
```

## 4. Parquet columns

### 4.1 Required columns

Every cell dataset must contain:

| Column | Parquet type | Rules |
|---|---|---|
| `gid` | `string` / UTF-8 | Required. Non-null. Valid for the manifest domain and level. |

A `cell_values` dataset must have unique `gid` values.

A `cell_contributions` dataset may repeat `gid` values.

The minimum useful table is:

```text
gid + one or more user value columns
```

The value column does not have to be named `value`. The manifest declares the value fields.

### 4.2 Optional identity columns

These columns improve query speed. They are not required for compact storage.

| Column | Parquet type | Rules |
|---|---|---|
| `packed_id` | `int64` | Must decode to the same domain, level, and cell as `gid`. |
| `x_idx` | `int64` | Must match the decoded canonical cell. |
| `y_idx` | `int64` | Must match the decoded canonical cell. |
| `uri` | `string` | Optional convenience field. Must equal `geosquare:v2:<domain>:<gid>`. |

Recommended profiles:

### Compact dataset

```text
gid
value fields...
```

Best for storage and simple distribution.

### Query dataset

```text
gid
packed_id
x_idx
y_idx
value fields...
```

Best for rectangular queries, joins, and analytics.

### 4.3 Contribution columns

A `cell_contributions` dataset must include:

| Column | Parquet type | Rules |
|---|---|---|
| `source_id` or `source_row` | `string` or `int64` | Stable source reference. |
| `coverage_ratio` | `double` | Area contribution in `[0, 1]`, when the source is polygonal. |
| `length_ratio` | `double` | Line contribution in `[0, 1]`, when the source is linear. |
| `assignment_method` | `string` | Example: `INTERSECTS`, `CENTROID`, `largest_overlap`. |

A row normally has either `coverage_ratio` or `length_ratio`.

A point contribution does not need either ratio.

### 4.4 Optional geometry column

Geometry is not stored by default.

If geometry is included, use:

| Column | Parquet type | Rules |
|---|---|---|
| `geometry_wkb` | `binary` | WKB geometry in the CRS declared by the manifest. |

Do not use a WGS84 polygon as the cell identity.

The cell geometry can always be computed from `gid` and the verified profile.

## 5. User fields

All columns except reserved GeoSquare columns are user payload fields.

Reserved fields are:

```text
domain
level
gid
uri
packed_id
x_idx
y_idx
source_id
source_row
coverage_ratio
length_ratio
assignment_method
boundary_policy
geometry_wkb
```

User fields must not use these names.

The manifest lists every value field with:

- name;
- logical type;
- value semantics;
- unit, if any;
- nullable status; and
- aggregation rule, if the data was aggregated.

Supported value semantics are:

```text
COUNT
TOTAL
DENSITY
MEASUREMENT
RATE
ORDINAL
CATEGORICAL
RANGE
```

## 6. Manifest file

Every dataset directory must contain:

```text
manifest.json
data/*.parquet
```

The manifest is the canonical dataset description.

The same JSON should also be embedded in Parquet file metadata under:

```text
geosquare.manifest
```

The sidecar manifest is easier to discover. The embedded copy makes an individual Parquet file more portable.

## 7. Manifest fields

A manifest must contain:

```json
{
  "manifest_version": "1.0",
  "dataset_type": "cell_values",
  "grid_system": "geosquare",
  "grid_version": "v2",
  "domain_code": "ID",
  "domain_id": 1,
  "level": 12,
  "profile_version": "2.1.0-static-datum",
  "registry_version": "2.0.0",
  "value_fields": [],
  "identity": {},
  "coverage": {},
  "source": {},
  "storage": {},
  "provenance": {}
}
```

### 7.1 Identity metadata

```json
"identity": {
  "gid_column": "gid",
  "uri_prefix": "geosquare:v2:ID:",
  "packed_id_column": null,
  "x_idx_column": null,
  "y_idx_column": null,
  "unique_gid": true
}
```

For a query dataset:

```json
"identity": {
  "gid_column": "gid",
  "uri_prefix": "geosquare:v2:ID:",
  "packed_id_column": "packed_id",
  "x_idx_column": "x_idx",
  "y_idx_column": "y_idx",
  "unique_gid": true
}
```

### 7.2 Coverage metadata

```json
"coverage": {
  "assignment_method": "polygon_to_cells",
  "boundary_policy": "INTERSECTS",
  "boundary_sha256": "<sha256>",
  "coverage_mode": "EQUAL_AREA",
  "min_coverage": 0.01,
  "length_mode": null
}
```

For point data:

```json
"coverage": {
  "assignment_method": "point_to_cell",
  "boundary_policy": "COVERS_POINT",
  "boundary_sha256": "<sha256>",
  "coverage_mode": null,
  "min_coverage": null,
  "length_mode": null
}
```

### 7.3 Source metadata

```json
"source": {
  "format": "parquet",
  "geometry_type": "Point",
  "source_crs": "EPSG:4326",
  "source_id_column": "asset_id",
  "source_dataset": "s3://bucket/source/",
  "source_row_count": 100000
}
```

The source URI is optional. Do not put secrets or credentials in the manifest.

### 7.4 Storage metadata

```json
"storage": {
  "parquet_compression": "zstd",
  "geometry_column": null,
  "geometry_format": null,
  "geometry_crs": null,
  "partitioning": [],
  "sorted_by": ["gid"],
  "row_count": 100000,
  "unique_cell_count": 100000
}
```

A query dataset can use:

```json
"storage": {
  "parquet_compression": "zstd",
  "geometry_column": null,
  "geometry_format": null,
  "geometry_crs": null,
  "partitioning": ["domain_code", "level"],
  "sorted_by": ["x_idx", "y_idx"],
  "row_count": 100000,
  "unique_cell_count": 100000
}
```

### 7.5 Provenance metadata

```json
"provenance": {
  "created_at": "2026-09-18T00:00:00Z",
  "created_by": "geosquare-grid-v2 0.1.0",
  "generator": "table_to_cells",
  "aggregation_rule": "weighted_sum",
  "value_semantics": "TOTAL",
  "notes": null
}
```

## 8. Value field metadata

Example:

```json
"value_fields": [
  {
    "name": "population",
    "parquet_type": "int64",
    "logical_type": "numeric",
    "semantics": "TOTAL",
    "unit": "persons",
    "nullable": false,
    "aggregation_rule": "weighted_sum"
  }
]
```

Categorical example:

```json
"value_fields": [
  {
    "name": "land_use",
    "parquet_type": "string",
    "logical_type": "categorical",
    "semantics": "CATEGORICAL",
    "unit": null,
    "nullable": false,
    "aggregation_rule": "largest_overlap"
  }
]
```

Range example:

```json
"value_fields": [
  {
    "name": "temperature_range",
    "parquet_type": "struct<min:double,max:double>",
    "logical_type": "range",
    "semantics": "RANGE",
    "unit": "celsius",
    "nullable": false,
    "aggregation_rule": "full_range"
  }
]
```

## 9. Complete manifest example

```json
{
  "manifest_version": "1.0",
  "dataset_type": "cell_values",
  "grid_system": "geosquare",
  "grid_version": "v2",
  "domain_code": "ID",
  "domain_id": 1,
  "level": 12,
  "profile_version": "2.1.0-static-datum",
  "registry_version": "2.0.0",
  "value_fields": [
    {
      "name": "population",
      "parquet_type": "int64",
      "logical_type": "numeric",
      "semantics": "TOTAL",
      "unit": "persons",
      "nullable": false,
      "aggregation_rule": "weighted_sum"
    }
  ],
  "identity": {
    "gid_column": "gid",
    "uri_prefix": "geosquare:v2:ID:",
    "packed_id_column": null,
    "x_idx_column": null,
    "y_idx_column": null,
    "unique_gid": true
  },
  "coverage": {
    "assignment_method": "polygon_to_cells",
    "boundary_policy": "INTERSECTS",
    "boundary_sha256": "<sha256>",
    "coverage_mode": "EQUAL_AREA",
    "min_coverage": 0.01,
    "length_mode": null
  },
  "source": {
    "format": "parquet",
    "geometry_type": "Polygon",
    "source_crs": "EPSG:4326",
    "source_id_column": "district_id",
    "source_dataset": null,
    "source_row_count": 1200
  },
  "storage": {
    "parquet_compression": "zstd",
    "geometry_column": null,
    "geometry_format": null,
    "geometry_crs": null,
    "partitioning": [],
    "sorted_by": ["gid"],
    "row_count": 830000,
    "unique_cell_count": 830000
  },
  "provenance": {
    "created_at": "2026-09-18T00:00:00Z",
    "created_by": "geosquare-grid-v2 0.1.0",
    "generator": "aggregate_to_cells",
    "aggregation_rule": "weighted_sum",
    "value_semantics": "TOTAL",
    "notes": null
  }
}
```

## 10. S3 layout

A single-domain dataset:

```text
s3://bucket/population-id-level-12/
  manifest.json
  data/
    part-00000.parquet
    part-00001.parquet
```

A dataset collection:

```text
s3://bucket/population/
  manifest.json
  domain=ID/level=12/
    manifest.json
    data/part-00000.parquet
  domain=VN/level=12/
    manifest.json
    data/part-00000.parquet
```

The first implementation should support the single-domain layout first.

## 11. Validation rules

A reader must reject a dataset when:

- `manifest_version` is unsupported;
- `dataset_type` is unknown;
- `grid_system` is not `geosquare`;
- `grid_version` is not supported;
- `domain_code` is missing;
- `level` is outside V2 limits;
- `profile_version` does not match the trusted registry;
- `gid` is null or malformed;
- a decoded GID does not match the manifest domain or level;
- `packed_id`, `x_idx`, or `y_idx` disagree with `gid`;
- `cell_values` contains duplicate GIDs;
- coverage or length ratios fall outside `[0, 1]`; or
- required manifest fields are missing.

A reader should warn when:

- the dataset has no `source_id` for contributions;
- no boundary hash is recorded for boundary-filtered data;
- geometry is included but its CRS is missing;
- the dataset is not sorted or partitioned for the requested query; or
- value semantics are missing for a value field.

## 12. Versioning

The dataset manifest version and GeoSquare grid version are separate.

Example:

```text
manifest_version = 1.0
grid_version = v2
profile_version = 2.1.0-static-datum
```

A new manifest format can be released without changing cell IDs.

A change to grid identity rules needs a new grid version.

Do not silently reinterpret an old dataset with a new profile.
