# GeoSquare V2 documentation

GeoSquare V2 is a country-scoped hierarchical metric grid. It gives stable square-grid IDs for points, polygons, tables and datasets.

Start with the [root README](../README.md) for install and the first run. This page lists the public docs. Pages under "Project internals" are for maintainers.

## Start here

Read these in order if you are new.

1. [Concepts](concepts.md): the grid, levels, identity and CRS rules.
2. [Quick start](quickstart.md): install, encode, decode, polygons, tables and datasets.
3. [Service API](service-api.md): the recommended high-level calls.
4. [API guide](api.md): the registry setup and the full service and low-level API.
5. [Country profiles](country-profiles.md): what each domain profile means.
6. [Comparison](comparison.md): how GeoSquare compares with S2, H3, geohash, Plus Codes, Web Mercator and MGRS.
7. [Data and aggregation](data-and-aggregation.md): tables, value rules, weights and NULL handling.
8. [Time cube](time-cube.md): values per cell and time period.
9. [Dataset metadata](dataset-metadata.md): manifest 1.1 fields and rules (draft).
10. [Cell pyramid](cell-pyramid.md): levels stacked as static files (draft).
11. [Crosswalk format](crosswalk-format.md): maps source units, such as villages, to cells with weights. Written in Bahasa Indonesia.
12. [Licenses](data-licenses.md): code and boundary-data licenses.

### Reference

- [Profile compatibility](profile-compatibility.md): which 1.0.0 datasets still load, and where GIDs differ.
- [Cell dataset contract](cell-dataset-contract.md) and [manifest schema 1.0](../schemas/cell-dataset-manifest-v1.schema.json).
- [Data-to-grid contract](data-to-grid-contract.md).
- [Boundary policy](boundary-policy.md).
- [SQLite registry](sqlite-registry.md).
- [Runnable quickstart script](../examples/quickstart.py).

## Optional dependencies

The core package has no required runtime dependency. Pick the smallest set of extras you need:

| Extra | Enables | Add these when combined with |
|---|---|---|
| `registry` | Ed25519 verification, signed registry loading, and exact PROJ checks | point indexing through the verified registry |
| `geo` | PyProj and Shapely geometry and polyfill operations | `registry` for verified profile workflows |
| `batch` | NumPy, Pandas, and Arrow vectorized encoders | batch point and projected-coordinate processing |
| `table` | Pandas, Arrow, and XLSX table input and output, plus dataset APIs | `registry` for table point indexing |
| `analytics` | The `geo` and `batch` runtime dependencies | `registry` and or `table` as needed |
| `filesystem` | fsspec-backed dataset storage | `table` |
| `s3` | fsspec and s3fs S3 storage | `table` |
| `dev` | Pytest and Hypothesis | local development and validation |

For a full local development environment:

```zsh
python -m pip install -e ".[analytics,registry,table,filesystem,s3,dev]"
```

The distribution name is `geosquare-v2`. Python code imports `geosquare_v2`.

## Public API names

Use these names in new code:

```text
point_to_cell       polygon_to_cells       polygon_to_cell
line_to_cells       cell_to_geometry       cells_to_geometry
table_to_cells      aggregate_to_cells     cell_neighbours
cell_distance       describe
```

Older names remain compatibility aliases:

```text
index_point    -> point_to_cell
polyfill       -> legacy bare-GID or coverage output; use polygon_to_cells for GridCellRecord output
neighbourhood  -> cell_neighbours
distance       -> cell_distance
```

## Design rule

The canonical identity is:

```text
(domain_code, level, x_idx, y_idx)
```

GID, packed IDs and geometry are derived forms. Do not use a display label or a third-party index as the canonical identity.

## Project internals

These pages are for maintainers. They cover release gates, decisions and migration records.

- [Gate A support matrix](gate-a-support-matrix.md)
- [Gate B boundary decision](gate-b-decision.md)
- [Gate B license-family review](gate-b-license-review.md)
- [Gate C contract freeze](gate-c-contract-freeze.md)
- [National CRS plan](national-crs-plan.md)
- [Release guide](release.md)
- [Automated publishing](release-automation.md)
- [GitHub About and release checklist](github-release.md)
- [V1 to V2 migration](migration-v1-v2.md)
- [Boundaries and migration](boundaries-and-migration.md)
- [Feature index](features.md)
