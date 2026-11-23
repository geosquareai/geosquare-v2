# Dataset metadata and space aggregation (manifest 1.1)

**Status:** draft for review (Phase 5, step 5a, spec item S8).
**Schema:** [schemas/cell-dataset-manifest-v1.1.schema.json](../schemas/cell-dataset-manifest-v1.1.schema.json)
**Applies to:** `cell_values` and `cell_contributions` datasets, as in the 1.0 schema.

Manifest 1.0 stays valid. Readers pick the schema from `manifest_version`.

## 1. Why

Phase 5 needs three things from each dataset:

1. How child cells combine into a parent cell when a map zooms out.
2. Which area the dataset covers, for the catalog and a coverage map.
3. Who may see the dataset, and how fresh it is.

Manifest 1.0 covers part of item 2. It covers none of items 1 and 3.

## 2. What 1.0 already has

| Block | What it records | Gap for Phase 5 |
|---|---|---|
| `coverage` | How source features were assigned to cells, and the boundary hash | Does not say which area is covered. Its name stays, so the area goes in a new `extent` block. |
| `value_fields[].aggregation_rule` | How source data became a cell value, for example `weighted_sum` | Does not say how cells combine into a parent. It keeps only the source-to-cell meaning. |
| `storage` | Row count, unique cell count, compression | No file hashes, so a snapshot cannot be pinned. |
| `provenance` | Created time, library version, generator | No spec version field. The spec version is only free text in `notes`. |
| `source` | Source format, CRS, row count | No owner, license, or sharing rule. |

The platform `csv_import` writes `aggregation_rule: "sum"` for COUNT fields. That import does no aggregation, so writers should write `null` instead. The platform fix belongs to L15.

## 3. What 1.1 adds

| Field | Type | Set by | Purpose |
|---|---|---|---|
| `value_fields[].space_aggregation` | enum | writer, default from `semantics` | Rule for the parent value. See section 4. |
| `value_fields[].space_weight` | string or null | writer | Weight for weighted rules. See section 4. |
| `value_fields[].null_share`, `min_value`, `max_value` | number or null | machine | Column statistics for the catalog. |
| `extent.bbox_wgs84` | 4 numbers or null | machine | Catalog search and map fit. Order: min lon, min lat, max lon, max lat. |
| `extent.compact_set_path` | relative path or null | machine | Compact cell set (E13) of the covered cells. |
| `governance.title`, `owner`, `source_name`, `license` | string or null | person | Catalog entry and license check. |
| `governance.share_policy` | `internal`, `k_anon_only`, `public` | person, default `internal` | Export rule. |
| `governance.refresh` | `once`, `daily`, `weekly`, `monthly`, `yearly`, `irregular` | person, default `once` | Stale badge. |
| `storage.data_files[]` | path, SHA-256, row count | machine | Change detection and snapshot pinning (L18). |
| `provenance.spec_version` | string | machine | Spec version the writer followed, for example `2.0`. |
| `provenance.derived_from` | string list | person or pipeline | Lineage: source dataset IDs, crosswalk IDs. |

**Last updated** uses `provenance.created_at`. Platform datasets are never overwritten, so the creation time is the last update. Add a separate field only if overwrites become allowed.

**Time coverage** is not added here. Time-value datasets already store `period_start` and `period_end`.

## 4. Space aggregation rules

When a map shows a parent cell, its value comes from its children. Each value field names one rule.

| `semantics` | Allowed `space_aggregation` | `space_weight` | Reason |
|---|---|---|---|
| COUNT | `sum`, `none` | null | Counts add up. |
| TOTAL | `sum`, `none` | null | Totals add up. |
| DENSITY | `weighted_mean`, `none` | `area` | Density is per area. Summing it is wrong. |
| MEASUREMENT | `weighted_mean`, `max`, `min`, `none` | required for `weighted_mean` | Use `max` for values such as flood depth. |
| RATE | `weighted_mean`, `none` | required | A rate needs its denominator. A 12% rate averaged without population weights gives a wrong parent rate. |
| CATEGORICAL | `majority_weighted`, `none` | null, `area`, or a COUNT field | Most common class wins. |
| ORDINAL | `max`, `min`, `none` | null | Order only. No mean. |
| RANGE | `none` | null | Not rolled up in 1.1. |

`space_weight` means:

- `null`: each child counts equally.
- `area`: each child counts by its cell area. Cells at one level have nearly equal area.
- A field name: another COUNT or TOTAL column in the same dataset. For example, `population` weights `unemployment_rate`.

`weighted_mean` without a weight is rejected. `none` opts a column out of rollup.

## 5. Rules outside the schema

The schema checks the shape of each file and the rule table in section 4. Readers must also check:

1. `space_weight` names another value field with semantics `COUNT` or `TOTAL`, or equals `area`.
2. `storage.row_count` equals the sum of `storage.data_files[].row_count`.
3. For `cell_values`, `unique_cell_count` equals the number of distinct GIDs.
4. `null_share`, `min_value`, and `max_value` match the data files.
5. `extent.bbox_wgs84` contains every cell in the dataset.

Items 1 and 2 are implemented in `src/geosquare_v2/cell_metadata.py`, with tests in `tests/test_cell_metadata.py`. Items 3 to 5 need the Parquet files, so they wait for the data-reading step.

Platform policy, not spec: an upload with `governance.license` set to null is refused.

## 6. Compatibility

- Cell IDs do not change. See [cell-dataset-contract.md](cell-dataset-contract.md), section 12.
- The platform keeps writing 1.0 until L15 ships. Catalog and rollup then treat every column as `none`, which is the safe default.
- Compact cell set and time-value manifests have their own contracts. This schema does not cover them yet (open decision 4).
- The examples in [cell-dataset-contract.md](cell-dataset-contract.md) use the placeholder `<sha256>`. The schema rejects that value. Those examples are not validated by a test.

## 7. Example (1.1)

Synthetic values. The SHA-256 values are placeholders of 64 zeros, so the example passes the pattern check.

```json
{
  "manifest_version": "1.1",
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
      "semantics": "COUNT",
      "unit": "persons",
      "nullable": false,
      "aggregation_rule": "weighted_sum",
      "space_aggregation": "sum",
      "space_weight": null,
      "null_share": 0.0,
      "min_value": 0,
      "max_value": 412
    },
    {
      "name": "unemployment_rate",
      "parquet_type": "double",
      "logical_type": "numeric",
      "semantics": "RATE",
      "unit": "percent",
      "nullable": true,
      "aggregation_rule": "weighted_mean",
      "space_aggregation": "weighted_mean",
      "space_weight": "population",
      "null_share": 0.04,
      "min_value": 0.0,
      "max_value": 18.5
    },
    {
      "name": "flood_depth_m",
      "parquet_type": "double",
      "logical_type": "numeric",
      "semantics": "MEASUREMENT",
      "unit": "m",
      "nullable": true,
      "aggregation_rule": "max",
      "space_aggregation": "max",
      "space_weight": null,
      "null_share": 0.61,
      "min_value": 0.0,
      "max_value": 1.8
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
    "boundary_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
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
  "extent": {
    "bbox_wgs84": [106.66, -6.26, 106.86, -6.1],
    "compact_set_path": "compact/cells.parquet"
  },
  "governance": {
    "title": "Synthetic example",
    "owner": "data team",
    "source_name": "synthetic",
    "license": "internal-test",
    "share_policy": "internal",
    "refresh": "once"
  },
  "storage": {
    "parquet_compression": "zstd",
    "geometry_column": null,
    "geometry_format": null,
    "geometry_crs": null,
    "partitioning": [],
    "sorted_by": ["gid"],
    "row_count": 830000,
    "unique_cell_count": 830000,
    "data_files": [
      {
        "path": "data/part-00000.parquet",
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "row_count": 830000
      }
    ]
  },
  "provenance": {
    "created_at": "2026-11-23T00:00:00Z",
    "created_by": "geosquare-v2 1.2.0",
    "generator": "aggregate_to_cells",
    "aggregation_rule": "weighted_sum",
    "value_semantics": null,
    "notes": null,
    "spec_version": "2.0",
    "derived_from": []
  }
}
```

## 8. Open decisions

1. Confirm the default rules in section 4, or change them.
2. Confirm the `share_policy` values and their meanings.
3. Confirm the `refresh` values.
4. Decide whether compact cell set and time-value manifests get `extent` and `governance` now or in a later step.
5. Confirm that the platform writes `aggregation_rule: null` for CSV import, before L15 starts.
