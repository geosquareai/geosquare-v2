# Features

This page lists the features built so far in the three GeoSquare repositories. It says where each feature lives, what it does, and what is still open.

| Repository | Role |
|---|---|
| `geosquare-v2` | Spec, rules, reference code, test vectors, and the Python package |
| `geosquare-engine` | Fast grid calculation in Rust, with Python, WebAssembly, DuckDB, the `gsq` tool, and a QGIS plugin |
| `geosquare-platform` | HTTP API that stores, checks, joins, and exports cell datasets |

Detail pages:

- Time cube: [time-cube.md](time-cube.md)
- Engine: [geosquare-engine docs](https://github.com/geosquareai/geosquare-engine/tree/main/docs)
- Platform: [geosquare-platform docs](https://github.com/geosquareai/geosquare-platform/tree/main/docs) (in Bahasa Indonesia)

## Spec and dataset types (geosquare-v2)

| Feature | What it does | Where |
|---|---|---|
| Spec 2.0 and test vectors | Defines GIDs, levels, the codec, packing, topology, and detection. Vectors check every implementation | `conformance/spec-2.0/` |
| `cell_values` | One value row per cell. GID unique | `docs/cell-dataset-contract.md` |
| `cell_contributions` | Source-to-cell rows, before aggregation | Same contract |
| `cell_compact_set` | Mixed-level set of cells that covers an area with fewer rows | Contract section 2 and `src/geosquare_v2/compact.py` |
| `cell_time_values` (time cube) | One row per cell and period, in UTC | [time-cube.md](time-cube.md) |
| Compact store | Writes and reads a compact set, and checks every read | `src/geosquare_v2/compact_store.py` |
| Time store | Writes and reads a time dataset, and checks every read | `src/geosquare_v2/time_store.py` |
| Signed registry | 11 domains with CRS and datum rules, signed with Ed25519 | `src/geosquare_v2/db/` |
| Polygon crosswalk builder | Turns polygons, such as village boundaries, into area weights per cell | `tools/build_polygon_crosswalk.py` |
| Crosswalk format | `sumber_id, gid, bobot`. Weights for each source sum to 1 | `docs/crosswalk-format.md` |
| V1 to V2 decoder | Reads V1 GIDs and migrates area by coverage | `LegacyV1Decoder`, `V1MigrationAdapter` |

## Grid engine (geosquare-engine)

| Feature | What it does | Status |
|---|---|---|
| Codec and grid functions | `encode`, `decode`, `parent`, `children`, `k_ring`, `k_disk`, `distance_m`, `cell_side_m` | Done |
| Packing | Domain ID and GID in one signed 64-bit integer | Done |
| Cell polygons in WGS 84 | Ring for a cell, with a segment limit. Candidate domains need opt-in | Done |
| Column detection | Finds which columns hold GIDs, packed IDs, or x and y | Done |
| CRS and datum | Explicit operation per domain. Six domains released, five candidate | Done |
| Python package | `geosquare-engine` 0.2.0 on PyPI. Python 3.11 or newer | Released |
| Compact helpers | `canonicalize`, `validate_compact_set`, `expand`, `contains` | Released in 0.2.0 |
| WebAssembly package | Same rules in the browser | Done |
| DuckDB extension | Grid functions and datasets inside DuckDB | Done |
| `gsq` command | Detect, rollup, join, and geometry export from the terminal | Done |
| QGIS plugin (E14) | GID column to polygon layer, and rollup to a coarser level. QGIS 4.0 or newer | Done. GUI check passed 14 of 14 |

## Platform API (geosquare-platform)

| Feature | What it does | Public? |
|---|---|---|
| Import check | Reads a CSV and reports its GID column and level. Stores nothing | Yes |
| Cell dataset upload | Checks every row, then stores a `cell_values` dataset with a manifest | Yes |
| Dataset read | Reads a dataset again and checks its manifest | Yes |
| Catalog | Lists dataset metadata from manifests | Yes |
| Cell profile | Values for one cell, its ancestors, and finer datasets. ID only | Yes |
| Map | Cells inside a WGS 84 box, and a map page | Yes |
| Crosswalks | Create, read, and apply a crosswalk. Checks that totals are conserved | Yes |
| Export with k-anonymity (L9) | Merges small cells until each has at least k people. Default k = 5, minimum 2 | Yes |
| Rollup | Sums per coarser cell. At the dataset's own level it returns each cell | Internal only |
| Join | Joins datasets and sums per coarser cell | Internal only |
| Compact upload and compact join (E13) | Stores a compact set, and sums values over the cells it covers | Upload: yes. Join: internal only |
| Time upload and time join (L7) | Stores time values, and joins two datasets by interval relation | Upload: yes. Join: internal only |
| V1 to V2 converter | Turns one caller-supplied V1 CSV into a V2 dataset. Refuses unsafe input | Command line |
| Demo | Runs upload, check, store, and manifest from the command line | Command line |

The internal routes answer 404 unless `GSQ_INTERNAL_ROUTES=1` is set. This is a route switch, not a login. See [privacy notes](https://github.com/geosquareai/geosquare-platform/blob/main/docs/privacy-and-internal-routes.md).

## Rules that apply everywhere

- Invalid input raises an error. Nothing is repaired.
- Cell dataset manifests written by the platform record the library versions that wrote them.
- A dataset is never overwritten. The same upload twice is refused.
- A stored dataset is checked again on every read.
- Grid rules live in the spec and the engine. The platform calls them and does not copy them.

## Not built yet

| Item | Why |
|---|---|
| Partitioning for time values | Needed when hourly data grows. Needs a rule in the spec first |
| JSON schema for the two new dataset types | Tools would check manifests without Python |
| k rule for time outputs | Not defined |
| Platform support for domains other than ID | Planned for Phase 5 |
| Aliases for cells (S7, L13) | Phase 5 |
| Tile server (L11) | Phase 5 |
| Cross-border crosswalk (L12) | Phase 5 |
| BigQuery and Snowflake functions (E15) | Phase 5 |
| Postgres extension (E17) | Phase 5 |
| Raster bridge and pipeline (E16, L14) | Phase 5 |
| Storage in S3 | Planned. Storage is local today |

## Release state

| Package | Version | Where |
|---|---|---|
| `geosquare-v2` | 1.2.0 | PyPI, tag `v1.2.0` |
| `geosquare-engine` | 0.2.0 | PyPI, tag `py-v0.2.0` |
| `geosquare-platform` | not published | Uses the two packages above |
