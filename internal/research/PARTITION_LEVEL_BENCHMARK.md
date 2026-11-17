# Partition level benchmark

**Date:** 2026-11-17
**Script:** `tools/benchmark_partition_levels.py`
**Spec:** 2.0, section 15 (cell dataset layout)
**Data:** `geosquare-risk/kyl/showcase/build/cell_features.parquet`, KYL Jakarta Barat

## 1. Question

Which GID prefix length should partition a cell dataset? The choice sets file size, file count, and how much a query must read.

## 2. What was measured

| Check | Result |
|---|---|
| Rows | 50,676 level-12 cells, 28 columns |
| GID uniqueness | Passed |
| Codec decode of every GID | Passed, all level 12 |
| Lon/lat to GID with the spec formula, all rows | 50,676 of 50,676 match |
| Parquet bytes per row, full table (28 columns, zstd) | 65.9 |
| Parquet bytes per row, thin table (`gid`, `packed_id`, `coverage_ratio`) | 5.5 |
| Row groups for a level-9 parent range (400 rows) | 1 of 7 touched, 8,192 rows per group |

The lon/lat check confirms that the file's GIDs match the spec formula on real coordinates. It does not prove the transform matches a second implementation.

## 3. Land cells per level, national

Counted against the signed ID boundary in the grid CRS. Land area is 1,889,873 km² in the equal-area CRS.

| Level | Cell side | Cells touching ID land | Method |
|---:|---:|---:|---|
| 3 | 1,000 km | 11 | Exact intersection |
| 4 | 500 km | 38 | Exact intersection |
| 5 | 100 km | 481 | Exact intersection |
| 6 | 50 km | 1,362 | Exact intersection |
| 7 | 10 km | 22,552 | Exact intersection |
| 8 | 5 km | 83,218 | Exact intersection |
| 9 | 1 km | about 1,889,873 | Land area divided by cell area |

Cells that only touch the coast count in full, so these counts run high at the edges.

## 4. Size per full partition, for 50 m data

A full partition holds every 50 m cell under one prefix. Rows and bytes come from the area ratio and the measured bytes per row.

| Level | Rows per partition | Full table, MiB | Thin table, MiB | Full table in 64-512 MiB | Thin table in 64-512 MiB |
|---:|---:|---:|---:|:---:|:---:|
| 3 | 400,000,000 | 25,148.9 | 2,082.5 | No | No |
| 4 | 100,000,000 | 6,287.2 | 520.6 | No | No (just above 512) |
| 5 | 4,000,000 | 251.5 | 20.8 | Yes | No |
| 6 | 1,000,000 | 62.9 | 5.2 | No (just below 64) | No |
| 7 | 40,000 | 2.5 | 0.2 | No | No |
| 8 | 10,000 | 0.6 | 0.1 | No | No |
| 9 | 400 | 0.0 | 0.0 | No | No |

## 5. What the small partitions look like

The Jakarta sample covers about 125 km². It cannot show national file sizes. It does show the cost of fine partitions:

| Level | Partitions in sample | Median file | Smallest file |
|---:|---:|---:|---:|
| 5 | 2 | 1.6 MiB | 0.4 MiB |
| 7 | 7 | 40.6 KiB | 30.2 KiB |
| 9 | 168 | 42.2 KiB | 15.6 KiB |

At level 9, most files hold about 400 rows and weigh about 40 KiB. Parquet metadata then costs more than the data.

## 6. Decision

1. **Full table (66 bytes per row).** Partition at level 5. Each full partition is about 252 MiB, and national 50 m data gives 481 land partitions.
2. **Thin table (5.5 bytes per row).** No level gives 64 to 512 MiB. Level 4 gives 521 MiB, just over the 512 MiB cap. Level 5 gives 21 MiB. Decided: level 4 (see section 8).
3. **National 1 km data.** The full table holds about 1.9 million rows. At 66 bytes per row that is about 119 MiB, under the cap. Write one file with no partition.
4. **Sort by `packed_id`.** A parent range is one contiguous block. The benchmark touched 1 of 7 row groups for a 1 km parent.

Spec 2.0 section 15 turns this into the rule. Choose the coarsest level whose full partition is at most 512 MiB.

## 7. Limits

- One city, one 28-column table. Bytes per row will change with the real columns, so measure them on each dataset.
- Land counts are upper bounds at the coast. Level 9 is an area estimate, not a count.
- The benchmark does not measure query time on S3, only partition count, file size, and row-group pruning.
- Row group size was fixed at 8,192 rows. Other sizes were not tried.

## 8. Decision

Thin 50 m tables use level 4. Decided on 2026-11-17.

- Files are about 521 MiB, about 2% over the 512 MiB cap. Few objects to list and read.
- The rejected option, level 5, gives about 21 MiB files under the 64 MiB floor, and 481 objects.

Reproduce with:

```zsh
.venv/bin/python tools/benchmark_partition_levels.py \
  --cells /path/to/cell_features.parquet \
  --out "$KIROCREW_SCRATCH/partition-benchmark"
```
