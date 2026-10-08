# GeoSquare V2 documentation

GeoSquare V2 is a country-scoped hierarchical metric grid for stable square-grid addresses. It supports point indexing, geometry conversion, table and dataset workflows, aggregation, neighbours, distance, migration, and signed country profiles.

Start with the [root README](../README.md) for installation and the runnable checkout quickstart. This index is the public documentation path; architecture, research, benchmark, review, and handover material stays under [`internal/`](../internal/).

## Start here

1. [Concepts and overview](concepts.md) — the grid model, hierarchy, identity, and CRS rules.
2. [Service API](service-api.md) — the recommended high-level application interface.
3. [API guide](api.md) — verified registry setup and the complete service/low-level API.
4. [Data conversion and aggregation](data-and-aggregation.md) — tables, geometry contributions, weights, and value semantics.
5. [Boundaries and migration](boundaries-and-migration.md) — explicit boundary policies and migration from earlier identifiers.
6. [Country profiles](country-profiles.md) — domain metadata and profile interpretation.
7. [Interoperability and comparisons](comparison.md) — relationship to other spatial identifiers.
8. [Release and security](release.md) — candidate status, reproducibility, attribution, and release gates.
9. [Gate A support matrix](gate-a-support-matrix.md) — per-domain option-2 support classification.
10. [Gate B boundary decision](gate-b-decision.md) — provenance, attribution, and redistribution decision record.
11. [Automated publishing](release-automation.md) — GitHub Actions, trusted publishing, and manual upload commands.
12. [GitHub About and release checklist](github-release.md) — repository description, release notes, and PyPI promotion.

## Contracts and operational guides

- [Boundary policy](boundary-policy.md)
- [Cell dataset contract](cell-dataset-contract.md)
- [Cell dataset manifest schema](../schemas/cell-dataset-manifest-v1.schema.json)
- [Data-to-grid contract](data-to-grid-contract.md)
- [V1 to V2 migration](migration-v1-v2.md)
- [SQLite registry](sqlite-registry.md)
- [Gate B boundary decision](gate-b-decision.md) — PH and overall boundary attribution decision.
- [Gate B license-family review](gate-b-license-review.md) — approved non-PH license-family scopes.
- [Gate C contract freeze](gate-c-contract-freeze.md) — frozen 0.2.0 identity, API, migration, and version rules.
- [Code and boundary-data licenses](data-licenses.md)
- [Runnable quickstart](../examples/quickstart.py)

## Optional dependencies

The package keeps the scalar core dependency-free. Select the smallest extra set that covers the feature you use:

| Extra | Enables | Add these when combined with |
|---|---|---|
| `registry` | Ed25519 verification, signed registry loading, and exact PROJ checks | point indexing through the verified candidate registry |
| `geo` | PyProj and Shapely geometry/polyfill operations | `registry` for verified profile workflows |
| `batch` | NumPy, Pandas, and Arrow vectorized encoders | batch point/projected-coordinate processing |
| `table` | Pandas, Arrow, and XLSX table input/output plus dataset APIs | `registry` for table point indexing |
| `analytics` | The `geo` and `batch` runtime dependencies | `registry` and/or `table` as needed; it does not include them |
| `filesystem` | fsspec-backed dataset storage | `table` |
| `s3` | fsspec and s3fs S3 storage | `table` |
| `dev` | Pytest and Hypothesis | local development and validation |

For a full local development environment:

```zsh
python -m pip install -e ".[analytics,registry,table,filesystem,s3,dev]"
```

The published distribution name is `geosquare-v2`; Python code imports `geosquare_v2`.

## Current status

The stable-release candidate is `0.2.0`, prepared in an isolated worktree and not published. It contains all 11 ASEAN domains under option 2: BN, ID, LA, MY, PH, SG, and VN are production-ready within the GeoSquare support scope, while KH, MM, TH, and TL remain explicitly provisional. Gate A, Gate B, and Gate C records are prepared; Gate D validation and registry signing remain before publication.

## Public API names

Use these names in new code:

```text
point_to_cell       polygon_to_cells       polygon_to_cell
line_to_cells       cell_to_geometry       cells_to_geometry
table_to_cells      aggregate_to_cells     cell_neighbours
cell_distance       describe
```

Older names remain compatibility aliases for now:

```text
index_point    -> point_to_cell
polyfill       -> legacy bare-GID/coverage output; use polygon_to_cells for GridCellRecord output
neighbourhood  -> cell_neighbours
distance       -> cell_distance
```

## Design rule

The canonical identity is always:

```text
(domain_code, level, x_idx, y_idx)
```

GID, packed IDs, and geometry are derived forms. Do not make a display label or a third-party index the canonical identity.
