# Phase 4 query-performance benchmark

This benchmark measures the vectorized GeoSquare encoding path and DuckDB query workloads over a deterministic one-million-point Indonesia candidate dataset. Packed-Int64 and GID-text aggregation are measured separately from a DuckDB Spatial `ST_Within` polygon predicate; the workloads are not algorithmically equivalent and are not presented as a direct speedup claim.

- Run ID: `20261008T013349Z`
- Repository commit: `2120f1fd6d9412b6cb59ce883d87964a5e7b5ffb` (working tree dirty: `True`)
- Points: `1,000,000`; level: `12`; seed: `20260315`
- DuckDB threads: `1`; warmups: `2`; measured repetitions: `10`
- JSON artifact SHA-256: `c7c07cb066712bfde43c6d5958872589272e1e6b8d30b41f8f3e460e666bc94b`

## Preparation stages

| Stage | Time (ms) |
|---|---:|
| point_generation_and_encoding | 1202.522 |
| dataframe_materialization | 58.209 |
| duckdb_table_and_geometry_materialization | 129.555 |

Preparation and table materialisation are excluded from the SQL timings below.

## Timed workloads

| Workload | Rows returned | Median (ms) | p95 (ms) | Peak RSS delta (MiB) |
|---|---:|---:|---:|---:|
| `packed_int64_groupby` | 252,617 | 68.898 | 69.593 | 0.00 |
| `gid_text_groupby` | 252,617 | 93.025 | 94.688 | 0.00 |
| `spatial_st_within_zone` | 1 | 159.854 | 160.618 | 0.00 |

## Correctness checks

- Every aggregation accounts for `1,000,000` input rows.
- Packed and GID aggregations have matching group counts: `True`.
- The spatial predicate returns the deterministic zone count `100,000`.
- Packed/GID total-value agreement: `True`.

## Reproducibility and interpretation

The point population is generated in ten fixed 8 km by 8 km projected clusters centred on Indonesian cities. The spatial workload uses a transformed, densified projected square around the first cluster, not a national legal boundary. Timings include query execution and result materialisation (`fetchall`) but exclude point generation, CRS transformation, GeoSquare encoding, table loading, geometry construction, and serialization. Peak RSS is the process-level resource maximum; the per-workload delta is diagnostic rather than an allocator-isolated measurement.

- Input hash: `7775f0ef476a44fc574837a5579c7c76769214d8fc7127f54dd361da82f96d19`
- Profile SHA-256: `95eb601ad1ff85d99d4efb63409f3e7567c6994aa71fcde6910b81228b1ea29a`
- Grid WKT2 SHA-256: `07b43d2bfd04139015ebd4207200d2013ebcddf0c5f4dd11a01ef88c3de36cf9`
- Spatial-zone WKT SHA-256: `a69ef32af22b512e2b005ff9f9ff556178066bbfa9b0b46fe738278f9424a1e3`

The JSON artifact is the authoritative source for all values in this report.

To reproduce the comparison environment without changing project runtime dependencies, install the exact benchmark-only package with `.venv/bin/python -m pip install duckdb==1.4.3`, then run `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python tools/benchmark_query_performance.py` from the repository root.
