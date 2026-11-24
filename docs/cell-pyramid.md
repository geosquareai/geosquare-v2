# Cell pyramid (level stack) spec

**Status:** draft for review (Phase 5, step 5c, spec item S9). The `gsq pyramid` command (E20) follows this spec.
**Applies to:** `cell_values` datasets with manifest 1.1. See [dataset-metadata.md](dataset-metadata.md).
**Related:** [cell-dataset-contract.md](cell-dataset-contract.md) (S3 layout, GID rules), [dataset-metadata.md](dataset-metadata.md) (rollup rules in section 4, content hash in section 3.1).

## 1. Why

A big dataset at a fine level, such as level 12 (50 m), is too many rows for a browser. A map at city zoom needs level 8 or 10.

A pyramid stores the same dataset at several coarser levels, like overviews in a COG raster. The browser then:

1. Picks the level that fits the map zoom.
2. Fetches only the files that cover the screen.

The result is plain static files on S3. No tile server is needed.

## 2. Levels

A pyramid has one base level and one or more coarser levels. The v2.0 default is base level 12 with coarser levels 10 and 8.

- Every pyramid level is a coarser ancestor of the base level.
- The base level is also stored in the pyramid, so the browser reads one layout for all levels.
- A reader refuses a level that is not coarser than the base.

## 3. Folder layout

```text
s3://bucket/<dataset-id>/pyramid/
  pyramid.json
  level=12/gid_prefix=<7 chars>/part-00000.parquet
  level=10/gid_prefix=<5 chars>/part-00000.parquet
  level=8/gid_prefix=<3 chars>/part-00000.parquet
```

- `pyramid.json` is the pyramid manifest (section 5).
- `level=<L>` holds one folder per pyramid level.
- `gid_prefix=<prefix>` holds one partition per spatial cell. The prefix is the GID cut to the partition level (section 4).
- Each partition has one file, `part-00000.parquet`. Its name does not change.
- Only non-empty partitions are written.

## 4. Spatial partition key

Each file holds all rows whose GID starts with the same prefix. The prefix is a cell at a fixed coarser level, the partition level.

| Pyramid level | Partition level | Prefix length | Cell size of the prefix |
|---:|---:|---:|---|
| 12 | 7 | 7 | 10 km |
| 10 | 5 | 5 | 100 km |
| 8 | 3 | 3 | 1000 km |

The rule is: partition level = pyramid level − 5. A level-7 cell holds 4 × 25 × 4 × 25 × 4 = 40,000 level-12 cells. Levels 10 and 8 give the same 40,000 bound with their own partition levels. So each file has at most 40,000 rows. This works because the GID is a string and the parent is the GID with its last character removed. Sorting by GID also keeps each partition in one contiguous range.

Any other pyramid level needs its own row in this table. A new row must keep the bound of 40,000 rows per file.

**How the browser finds the files on screen:**

1. Take the map bounding box in WGS 84.
2. Find the partition-level cells that cover the box. Use the grid's cover function with the partition level.
3. For each cover cell, look up its `gid_prefix` in the `files[]` list of `pyramid.json`.
4. Fetch the matching files. Skip prefixes not in the list, because those cells have no data.

The browser never lists the bucket. `pyramid.json` is the full index of files.

## 5. Pyramid manifest (`pyramid.json`)

```json
{
  "pyramid_version": "1.0",
  "grid_system": "geosquare",
  "grid_version": "v2",
  "domain_code": "ID",
  "profile_version": "2.1.0-static-datum",
  "registry_version": "2.0.0",
  "source": {
    "dataset_id": "population-id-level-12",
    "manifest_version": "1.1",
    "base_level": 12,
    "row_count": 49067,
    "content_sha256": "<64 hex>"
  },
  "share_column": "share_in_aoi",
  "columns": [
    {"name": "population", "parquet_type": "int64", "space_aggregation": "sum", "space_weight": null},
    {"name": "unemployment_rate", "parquet_type": "double", "space_aggregation": "weighted_mean", "space_weight": "population"},
    {"name": "flood_depth_m", "parquet_type": "double", "space_aggregation": "max", "space_weight": null}
  ],
  "levels": [
    {
      "level": 12,
      "partition_level": 7,
      "row_count": 49067,
      "content_sha256": "<64 hex>",
      "files": [
        {
          "gid_prefix": "1234567",
          "path": "level=12/gid_prefix=1234567/part-00000.parquet",
          "row_count": 20000,
          "gid_min": "...",
          "gid_max": "...",
          "content_sha256": "<64 hex>",
          "share_sha256": "<64 hex>"
        }
      ]
    }
  ],
  "created_at": "2026-11-24T00:00:00Z",
  "created_by": "gsq pyramid <version>"
}
```

Field rules:

- `source.dataset_id` and the grid fields copy the base manifest. A reader checks that they match.
- `source.content_sha256`: the digest rule in section 6.3, applied to the base dataset's data file hashes.
- `columns[]` lists the value fields that roll up. A value field with `space_aggregation: none` is left out. Each `space_aggregation` and `space_weight` copies the base manifest.
- `share_column` names the edge-share column (section 7). It is not a value field.
- `levels[].row_count` equals the sum of `files[].row_count`.
- `levels[].content_sha256`: the digest rule in section 6.3, applied to the file `content_sha256` values.
- `files[].content_sha256`: the content hash in [dataset-metadata.md](dataset-metadata.md) section 3.1, over `gid` and the value columns in `columns[]` order.
- `files[].share_sha256`: the same section 3.1 procedure, over `gid` and the share column only, typed `double`. This keeps the frozen section 3.1 unchanged.

## 6. Rollup

### 6.1 Rule

Every coarser level is computed from the base level cells. Coarser levels are never built from the child level's values. A pyramid level must equal the server rollup (L4) of the base level, using the same rules.

For one parent cell and one column:

| `space_aggregation` | Parent value |
|---|---|
| `sum` | Sum of the child values that are not null. Null if no child has a value. |
| `weighted_mean` | Sum of (value × weight) over children where both are not null, divided by the sum of weights over the same children. Null if the sum of weights is 0. |
| `median` | Median of the child values that are not null. Null if fewer than 3 children have a value. |
| `max` | Largest child value that is not null. Null if none. |
| `min` | Smallest child value that is not null. Null if none. |

`space_weight` follows [dataset-metadata.md](dataset-metadata.md) section 4:

- A field name: the child's value in that column is the weight.
- `area`: the child's weight is its grid cell area. At one level this is the same for every child, so the mean is the same as an unweighted mean.

A parent row exists when at least one base row lies under it. The parent value is null when the rule above gives no value. The parent row is still written, so that its share is kept (section 7).

`majority_weighted` is not a rule in v2.0. A base dataset with a CATEGORICAL column that uses it is refused by the pyramid writer.

### 6.2 Fan-in per level step

| From base level | To level | Children per parent | Base cells per parent |
|---:|---:|---:|---:|
| 12 | 10 | 4 × 25 = 100 | 100 |
| 12 | 8 | 4 × 25 × 4 × 25 = 10,000 | 10,000 |

A level 12 → 10 parent has 100 base cells. A level 12 → 8 parent has 10,000.

### 6.3 Digest of hashes

One rule is used for `source.content_sha256` and `levels[].content_sha256`:

1. Take the `content_sha256` of each file, in ascending order of `path` (UTF-8 bytes).
2. Write each hash in lowercase hex, followed by one line feed (0x0A).
3. Feed the bytes into SHA-256. Write the digest in lowercase hex.

## 7. Edge cells and `share_in_aoi`

A base cell can lie only partly inside the area of the dataset. The base row then carries `share_in_aoi`, a `double` in [0, 1]. It is the same value as `coverage_ratio` in [cell-dataset-contract.md](cell-dataset-contract.md).

Rules:

- A base cell with no row has share 0. So the base level must hold a row for every cell with share > 0, even if its values are null.
- A parent's share is the sum of the shares of its base cells, divided by the number of base cells under the parent (100 for level 10, 10,000 for level 8, when the base level is 12). Base cells are equal area in the grid, so this is the parent's area share in the dataset area.
- The parent value (section 6) uses only children with a value. The share does not change the value.

This keeps an edge parent visible on the map, with the share that tells how much of it is inside the area.

## 8. Readers must refuse

A reader refuses a pyramid when any of these holds:

1. `pyramid_version` is unknown.
2. `grid_system` is not `geosquare`, or `grid_version` or `profile_version` does not match the trusted registry.
3. A level is not coarser than `source.base_level`.
4. A GID length is not its level, or a GID does not start with its file's `gid_prefix`.
5. A file's GIDs are not sorted, or contain a duplicate.
6. A GID does not match the manifest domain.
7. A file is listed in `pyramid.json` but missing, or its hash does not match.
8. `levels[].row_count` or `source.row_count` does not match the file row counts.
9. `share_in_aoi` is outside [0, 1] or null in a file that lists it.
10. A `columns[]` entry uses an unknown `parquet_type` (see dataset-metadata 3.1), or a `space_aggregation` that is not in dataset-metadata section 4, or `majority_weighted`.
11. `space_weight` is a field name that is not a COUNT or TOTAL column in `columns[]`.

A reader does not recompute rollup values. That is the job of the conformance tests for E20.

## 9. Size guidance

- Rows per file: at most 40,000 by construction (section 4). Sparse partitions may be small. Do not pad them.
- Files per level: about one per non-empty partition-level cell. At level 12, a national dataset has many files. The index in `pyramid.json` stays a few MB at most. Check this on the full Indonesia data before fixing the rule.
- File size in bytes: not measured yet. E20 must measure it on the Jabodetabek and Jakarta Barat data and record the numbers here.

## 10. Worked example: Jakarta Barat

Base row counts come from [plan 11, section 5b](../../plan/11-rencana-fase5.md) (estimates from cell area, not measured).

| Level | Cell size | Rows (approx.) | Partition level | Files (approx.) |
|---:|---|---:|---:|---:|
| 12 (base) | 50 m | 49,067 | 7 | 2 to 3 |
| 10 | 500 m | about 491 (49,067 / 100) | 5 | 1 to 2 |
| 8 | 5 km | about 5 (49,067 / 10,000) | 3 | 1 to 2 |

The file counts follow from the 10 km and 100 km grid cells that touch Jakarta Barat. The exact count depends on where those cells fall. Coarse-level row counts are a little higher than the area estimate, because edge cells that touch the area also get a row.

Level 10 or 8 is the likely choice at city zoom. The zoom mapping is still open (section 11).

## 11. Open questions

1. **Base level copy.** This spec copies the base level into `pyramid/`, which costs about 1.3 times the storage. Alternative: point level 12 at the source dataset files. Decide before E20.
2. **Null rule for `sum`.** This spec gives null when no child has a value. Confirm this matches L4 on the server. The alternative is 0.
3. **`area` weight.** This spec uses grid cell area, which is equal for every child, so `area` gives an unweighted mean. Confirm this matches L4 and the DENSITY rule.
4. **`majority_weighted`.** [dataset-metadata.md](dataset-metadata.md) section 4 still lists it. The user says it is not a rule yet. That row needs to change, and CATEGORICAL columns stay out of pyramids until it is defined.
5. **`share_in_aoi` in the base manifest.** It is not in [dataset-metadata.md](dataset-metadata.md). Decide whether it becomes a field there, and whether the base level must hold zero-value cells inside the area (section 7 assumes yes).
6. **Share threshold.** Decide whether the map hides or marks parents with a low share, and at what value.
7. **Browser cell budget.** The level choice needs a cap on cells on screen. Plan 11 gives 1 to 2 million, and the default 500,000 is only a suggestion. Set it in E18 or L16.
8. **Zoom to level table.** The mapping from map zoom to pyramid level is not set. It belongs in the viewer, not in this spec.
9. **Partition level for other levels.** Only levels 12, 10 and 8 are in the table. Add rows when a new level is needed.
10. **Full file index size.** For a national level-12 dataset, `pyramid.json` may list many files. Check the size before deciding whether to split the index.
11. **Conformance vectors.** No pyramid vectors exist yet. E20 needs a small base dataset with known parent values for sum, weighted_mean, median, max and min, plus edge shares.
12. **Level set.** Levels 12, 10 and 8 come from plan 11 (K10). Confirm them after E20 tests show the file sizes.
