# GeoSquare V2

GeoSquare V2 maps the world in exact squares by using each country's projection. Our objective is to make spatial data intuitive and accessible to non-geospatial practitioners while retaining the rigor required for enterprise data platforms. Taking inspiration from the spatial simplicity of voxel environments like Minecraft, Geosquare discretizes geographic space into metric squares. A square provides an effortless navigational reference: moving through a 10~m square means advancing 10 metres and turning 90 degrees right for 10 metres. Geosquare pairs this intuitive geometry with an alternating 5x5 and 2x2 hierarchical subdivision over an invariant 50,000 km root, producing cell resolutions aligned with decimal metric habits: 50 km, 10 km, 5 km, 1 km, 500 m, 100 m, 50 m, 10 m, and 5 m.

Rather than relying on an inherently distorted global projection, Geosquare establishes country-specific projected Coordinate Reference Systems to keep squares square on the ground. We evaluate this architecture across all 11 Southeast Asian (ASEAN) nations. The results show that Geosquare maintains near-zero side anisotropy ($< 0.0001\%$) and stable ground area across the region. We also present an integer-based topology and distance formulation, compute-on-read geometry derivation, a cryptographically signed registry, and a roadmap for structured human-readable aliases that address the structural shortcomings of What3Words.

> **Release status: local technical candidate (`0.1.0rc1`).** The bundled registry contains 11 ASEAN domains, but its geodetic profiles and boundary data are not approved production or legal-boundary data. Do not upload this candidate or treat it as production without the release approvals described in [the release guide](docs/release.md).

## Install

The public distribution name is `geosquare-v2`; the Python import name is `geosquare_v2`.

For the current checkout:

```zsh
# Verified registry loading and the point-indexing quickstart
python -m pip install -e ".[registry]"

# Geometry, batch, table/dataset, remote-storage, and test support
python -m pip install -e ".[analytics,registry,table,filesystem,s3,dev]"
```

After an approved publication, the same extras can be installed from the package index:

```zsh
python -m pip install "geosquare-v2[registry]"
```

Python 3.11 or newer is required.

## Quickstart

The verified checkout example loads the signed candidate registry, verifies its packaged boundaries, and indexes a WGS84 point through the high-level service API:

```zsh
python examples/quickstart.py
```

Read the complete example at [`examples/quickstart.py`](examples/quickstart.py). It uses `release/registry-trust.json` as a public-key example for the bundled candidate. Production applications must manage and approve their trusted public keys independently.

The essential application call is:

```python
cell = service.point_to_cell(
    "ID",
    longitude=106.8456,
    latitude=-6.2088,
    level=9,
)

print(cell.uri)              # geosquare:v2:ID:<gid>
print(cell.gid)
print(cell.projected_bounds)
```

`GeosquareService` creates the CRS transformer with `always_xy=True` and returns the canonical cell together with version, scale, and geometry metadata. Boundary filtering is opt-in; use a named `BoundaryPredicate` when an operational-boundary decision is required.

## Core model and API

The durable identity is always:

```text
(domain_code, level, x_idx, y_idx)
```

A GID, packed integer, and geometry are derived representations. Store the versioned URI (`geosquare:v2:<domain>:<gid>`) in durable data rather than a bare GID.

The high-level service API includes:

```text
point_to_cell       polygon_to_cells       polygon_to_cell
line_to_cells       cell_to_geometry       cells_to_geometry
table_to_cells      aggregate_to_cells     cell_neighbours
cell_distance       describe
```

Use `GeosquareGrid` directly for low-level projected-coordinate, hierarchy, packing, and neighbour operations. Use the service for normal application code so profile lookup and CRS setup are consistent.

## Optional dependencies

The core package has no mandatory runtime dependency. Install only the capability groups you need:

| Extra | Features | Typical combination |
|---|---|---|
| `registry` | Signed registry verification and exact PROJ-resource checks | `registry` |
| `geo` | PyProj and Shapely geometry/polyfill operations | `geo,registry` |
| `batch` | NumPy, Pandas, and Apache Arrow vectorized adapters | `batch` |
| `table` | CSV, XLSX, Parquet, and DataFrame table APIs; includes Pandas and Arrow | `table,registry` |
| `analytics` | Combined geometry and batch runtime support; does not include registry or table | `analytics,registry,table` |
| `filesystem` | fsspec-backed dataset storage | `table,filesystem` |
| `s3` | S3-backed dataset storage through fsspec/s3fs | `table,s3` |
| `dev` | Pytest and Hypothesis test tooling | add to a development install |

The `registry` extra is needed for `DbRegistryLoader`; it also supplies PyProj for the point-indexing service. Add `geo` when Shapely or geometry/polyfill operations are used. Add `table` for dataset APIs, and add `filesystem` or `s3` for the corresponding remote storage backends.

## Domains and candidate data

The signed candidate registry currently includes:

`BN`, `KH`, `ID`, `LA`, `MY`, `MM`, `PH`, `SG`, `TH`, `TL`, and `VN`.

Each profile declares its grid CRS, equal-area coverage CRS, root extent, scale metadata, reference-epoch policy, and operational-boundary metadata. The exact values are in the signed SQLite registry, not in this summary. The registry database and detached signature are packaged at `src/geosquare_v2/db/`; boundary GeoJSON files are packaged under `src/geosquare_v2/data/registry/boundaries/`.

## Documentation

- [Documentation index](docs/README.md)
- [Concepts and overview](docs/concepts.md)
- [Service API](docs/service-api.md)
- [Full API guide](docs/api.md)
- [Data conversion and aggregation](docs/data-and-aggregation.md)
- [Boundaries and migration](docs/boundaries-and-migration.md)
- [Cell datasets and manifests](docs/cell-dataset-contract.md)
- [Country profiles and comparisons](docs/country-profiles.md)
- [Release and security](docs/release.md)
- [Automated publishing](docs/release-automation.md)
- [Boundary source attribution](src/geosquare_v2/data/registry/boundaries/SOURCES.md)
- [Code and boundary-data licenses](docs/data-licenses.md)

Architecture, research, benchmarks, reviews, and local handover material remain under [`internal/`](internal/) and are not part of the public onboarding path.

## Validation for maintainers

Use the repository environment described in [the release guide](docs/release.md):

```zsh
.venv/bin/python -m compileall -q src tools tests examples
.venv/bin/python -B -m pytest -q -W error::DeprecationWarning
.venv/bin/python -m pip check
```

Build and metadata checks are intentionally separate from publication approval. No TestPyPI, PyPI, or Conda upload is authorized for this candidate until the release blockers in `HANDOVER.md` are closed.

## Repository layout

```text
src/geosquare_v2/                 Package source and signed runtime resources
examples/                          Checkout-runnable public examples
docs/                              Public concepts, API, data, dataset, and release guides
release/                           Release inputs and candidate trust material
tools/                             Maintainer scripts for registry and boundary workflows
tests/                             Conformance and integration tests
internal/                          Architecture, research, review, and handover notes
```
