# GeoSquare Grid V2 Implementation and Release Plan

**Repository:** `geosquare-grid-v2`  
**Package:** `geosquare-grid-v2`  
**Python import:** `geosquare_v2`  
**Plan date:** 2026-10-01  
**Current profile:** `2.0.0-rc.2-asean`  
**Current package state:** Local release candidate work exists; the package has **not** been published to PyPI.

## 1. Purpose

This plan turns the handover into an ordered implementation and release workflow. The next major product area is the cell-dataset distribution layer:

```text
manifest
  → Parquet writer
  → local reader and validation
  → query
  → lazy geometry
  → geometry contributions
  → semantic aggregation
  → optional filesystem/S3 access
  → TestPyPI validation
  → PyPI release
```

The immediate goal is not another grid algorithm. It is a trustworthy, inspectable, and distributable dataset format that preserves grid identity, value semantics, provenance, and validation metadata.

**Phase 0 status:** Complete as of 2026-10-01; documentation changes are intentionally uncommitted for review.
**Phase 1 status:** Complete as of 2026-10-01 for the manifest contract, parser, schema packaging, and validation tests.
**Phase 2 status:** Complete as of 2026-10-01 for local Parquet storage and validation.
**Phase 3 status:** Complete as of 2026-10-01 for local query support over queryable datasets.
**Phase 4 status:** Complete as of 2026-10-01 for geometry-table contribution generation.
**Phase 5 status:** Complete as of 2026-10-01 for geometry-aware value allocation and aggregation.
**Phase 6 status:** Complete as of 2026-10-01 for optional fsspec filesystem support.

## 2. Current baseline

The Phase 0 repository verification found:

- The checkout is on branch `db_registry` at `7db4c6c`, tracking `origin/db_registry`.
- `main` and `origin/main` remain at `5b98c6d` (`Prepare ASEAN V2 release candidate`).
- The contract and schema files are already tracked; the older handover notes describing them as uncommitted were stale.
- At the start of verification, the only working-tree change was the new untracked `IMPLEMENTATION_PLAN.md`; the updated plan and handover are now intentional documentation changes awaiting review.
- `.DS_Store` and the existing `dist/` wheel/sdist are tracked and unchanged in this branch. Removing those tracked artifacts is a separate repository-hygiene decision, not part of Phase 0.
- `CELL_DATASET_CONTRACT.md` and `schemas/cell-dataset-manifest-v1.schema.json` are present and tracked.
- Local `query_cell_dataset` now supports trusted-profile bbox filtering for queryable datasets; S3 and remote filesystem access remain deferred.
- `geometry_table_to_cells` now converts supported geometry tables into auditable contribution rows; value allocation and aggregation are still deferred.
- Geometry-aware allocation and aggregation now support explicit totals, densities, measurements, rates, counts, categorical values, ordinal values, and ranges.
- The core grid, registry, conversion, table, aggregation, and migration functionality already exists.
- The historical baseline suite passed: `144 passed in 4.34s`.
- The current full suite collects 195 tests and is the release-hardening validation target.
- Dependency verification passes: `pip check` reports `No broken requirements found.`
- The `CellDatasetManifest` parser and runtime manifest validator now exist; Parquet row/schema validation is still part of Phase 2.
- There is no embedded Parquet manifest metadata implementation yet.
- There are 18 focused cell-manifest validation tests; Parquet round-trip, invalid-row, duplicate-GID, and S3/filesystem tests are still pending.
- There is no geometry-table conversion API yet.
- There is no geometry-aware allocation pipeline yet.
- PyArrow is available through the existing table-related optional dependency set.
- The package declares optional `filesystem` support through `fsspec==2025.7.0` and optional `s3` support through `fsspec==2025.7.0` plus `s3fs==2025.7.0`.
- The base package has no filesystem or S3 dependency.
- The runtime JSON schema is packaged under `src/geosquare_v2/data/` and included through `tool.setuptools.package-data`.
- The current tracked wheel and sdist are historical package artifacts with metadata for version `0.1.0`; fresh candidate artifacts must be built under `dist-candidate/` and must not reuse `dist/`.
- The package has not been uploaded to TestPyPI or production PyPI. No upload is authorized during this release-hardening task.
- No PEM paths were found in reachable Git history, and no sensitive PEM/private/secret filenames were found in the existing wheel or sdist. A final secret scan remains required before release.

The local private signing key must remain outside Git and outside all package artifacts. The old private key remains compromised and must never be reused.

## 3. Guiding principles

1. **Freeze the contract before implementing storage.** A writer and reader must share unambiguous semantics.
2. **Validate against the trusted registry.** A syntactically valid GID is not enough; domain, level, profile version, and registry identity must be checked.
3. **Keep compact and queryable layouts distinct.** A GID-only dataset is compact but cannot support efficient x/y spatial filtering.
4. **Keep contribution rows auditable.** Geometry assignment must be separate from final value allocation and aggregation.
5. **Make value meaning explicit.** A total, density, rate, measurement, and categorical value must not be treated as interchangeable numeric values.
6. **Make local Parquet authoritative.** S3 should provide access to the same format, not introduce a second format.
7. **Keep optional infrastructure optional.** Do not add `boto3` or S3 requirements to the core package without a clear need.
8. **Do not publish before clean-install verification.** TestPyPI must be used before production PyPI.

## 4. Phase 0 — Reconcile the baseline and approve scope

### Status: complete

Verified on 2026-10-01. The repository baseline, tracked release artifacts, package metadata, dependency state, test baseline, security scan inputs, and publication status were checked. The handover was updated to match the live branch pointers and working-tree state. The contract and schema files are approved as the starting point for Phase 1.

### Decisions

- Proceed with the cell-dataset distribution layer as the next development area.
- Treat the current registry and profiles as a technical candidate, not a final production geodetic release.
- Target `0.1.0rc1` for the eventual candidate release.
- Keep the current local `0.1.0` package metadata and artifacts unchanged until release preparation is complete.
- Do not upload to TestPyPI or PyPI during implementation. Publication is a later gated activity.
- Keep the new private signing key outside Git and all package artifacts.
- Defer cleanup of tracked `.DS_Store` and `dist/` artifacts as a separate repository-hygiene decision.

### Verification record

- `db_registry` and `origin/db_registry`: `7db4c6c`.
- `main` and `origin/main`: `5b98c6d`.
- Existing suite: `144 passed in 4.34s`.
- Dependency check: `pip check` reported `No broken requirements found.`
- Local wheel and sdist metadata: `geosquare-grid-v2==0.1.0`.
- No PEM paths in reachable Git history.
- No sensitive PEM/private/secret filenames in the existing wheel or sdist.
- No TestPyPI or PyPI publication, per the release-status confirmation.

### Exit criteria

- [x] The handover reflects the actual repository state.
- [x] The contract files and implementation scope are approved as the starting point.
- [x] The release target is explicitly identified as technical candidate `0.1.0rc1`.
- [x] No private signing key was found in the repository history or existing build artifacts; the final release scan remains required.

## 5. Phase 1 — Freeze and implement the cell-dataset manifest

### Status: complete

Completed on 2026-10-01. The manifest is implemented as a separate `CellDatasetManifest` type, with deterministic serialization, standard-library validation, trusted-profile checks, declared-column checks, packaged schema access, and 18 focused tests. The runtime schema is included in the package-data configuration and verified in a temporary wheel.

The following decisions are now frozen for the initial format:

- `domain` and `level` are reserved identity/context columns and cannot be value fields.
- `cell_values` manifests must declare `unique_gid: true`.
- Queryable identity metadata must declare `packed_id`, `x_idx`, and `y_idx` together.
- Numeric logical fields use `COUNT`, `TOTAL`, `DENSITY`, `MEASUREMENT`, or `RATE`; categorical, ordinal, and range fields use their matching semantics.
- Runtime validation uses the standard library; no `jsonschema` dependency is added in this phase.
- Trusted registry validation checks domain code, domain ID, profile version, and boundary hash when available.

### Relevant files

```text
CELL_DATASET_CONTRACT.md
schemas/cell-dataset-manifest-v1.schema.json
pyproject.toml
MANIFEST.in
src/geosquare_v2/
```

### Design decisions

#### 5.1 Manifest module

The existing `manifest.py` is associated with the signed registry manifest. Avoid conflating the two concepts. Use a separate module, preferably:

```text
src/geosquare_v2/cell_manifest.py
```

with a public object such as:

```python
CellDatasetManifest
```

#### 5.2 Manifest validation layers

The JSON schema validates structure, but Python runtime validation must also enforce:

- required and allowed fields;
- unique value-field names;
- valid dataset type;
- valid domain and level;
- profile and registry identity;
- value semantics and logical types;
- declared physical Parquet types;
- reserved versus user columns;
- conditional rules for `cell_values` and `cell_contributions`;
- coverage and length ratio bounds;
- query-column declarations;
- source and provenance metadata;
- row and unique-cell counts where declared.

`cell_values` must enforce unique GIDs. `cell_contributions` may allow repeated GIDs but must preserve source provenance such as `source_id` and `source_row`.

#### 5.3 Reserved columns

The current table workflow emits fields including:

```text
domain
level
x_idx
y_idx
gid
uri
packed_id
```

The contract must explicitly classify these as reserved identity/query columns or transient conversion columns. They must not accidentally become user value fields.

#### 5.4 Schema packaging

The runtime JSON schema must be present after `pip install`. Prefer placing the runtime schema under package data, for example:

```text
src/geosquare_v2/data/cell-dataset-manifest-v1.schema.json
```

Load it with `importlib.resources`. Keep the Markdown contract in the documentation/source distribution as appropriate, but do not rely on a root-level Markdown file being available in the wheel.

#### 5.5 Dependency decision

Phase 1 uses the Python standard library for manifest validation and does not add `jsonschema` to the package dependencies. The packaged JSON schema remains the machine-readable contract, while the runtime validator enforces the schema’s structure plus cross-field semantics that JSON Schema alone cannot express. Revisit an optional pinned `jsonschema` extra only if future schema complexity justifies it; do not make validation silently optional.

### Deliverables

- [x] `CellDatasetManifest` parsing and serialization.
- [x] Canonical JSON serialization for sidecar and embedded metadata.
- [x] Clear manifest validation exceptions.
- [x] Runtime access to the packaged schema.
- [x] Tests for valid and invalid manifests.

### Gate A

Passed. The manifest semantics, reserved columns, dataset-type rules, package-data location, dependency strategy, and validation behavior are approved for Phase 2 storage implementation.

## 6. Phase 2 — Implement local Parquet dataset storage

### Status: complete

Completed on 2026-10-01. `CellDataset` now provides eager local PyArrow-backed reads and writes using:

```text
dataset/
├── manifest.json
└── data/
    └── part-00000.parquet
```

The implementation includes:

- atomic write-to-temporary-directory then rename;
- refusal to overwrite an existing destination;
- canonical sidecar manifest writing;
- canonical `geosquare.manifest` Parquet metadata embedding;
- sidecar/embedded manifest consistency checks;
- Arrow schema and declared Parquet type validation;
- row counts and unique-cell counts;
- compact and queryable identity columns;
- GID, URI, domain, level, packed ID, x/y consistency checks;
- `cell_values` duplicate rejection;
- `cell_contributions` provenance and repeated-GID support; and
- coverage/length ratio bounds and nullability checks.

S3, remote filesystems, lazy dataset scanning, and query pushdown remain deferred to later phases.

### Suggested modules

```text
src/geosquare_v2/dataset.py
src/geosquare_v2/storage.py
src/geosquare_v2/cell_manifest.py
```

### Suggested API

```python
dataset = CellDataset.from_table(table, manifest=manifest)
dataset.write("path/to/dataset/")
dataset = CellDataset.read("path/to/dataset/")
dataset.validate()
```

Convenience functions may also be provided:

```python
write_cell_dataset(dataset, path)
read_cell_dataset(path)
```

### Initial local layout

```text
dataset/
├── manifest.json
└── data/
    └── part-00000.parquet
```

### Writer requirements

The writer must:

1. Validate the manifest before writing.
2. Validate the Arrow/Parquet schema against the manifest.
3. Support `cell_values` and `cell_contributions`.
4. Support compact datasets containing `gid` and value fields.
5. Support queryable datasets containing `gid`, `packed_id`, `x_idx`, and `y_idx`.
6. Write a sidecar `manifest.json`.
7. Embed the canonical manifest under the Parquet metadata key:

   ```text
   geosquare.manifest
   ```

8. Preserve UTF-8 GIDs and declared value types.
9. Use an atomic temporary-directory-then-rename strategy for local output.
10. Reject partial or inconsistent output.

### Reader requirements

The reader must:

1. Read the sidecar manifest first.
2. Validate the manifest before trusting the data.
3. Read embedded Parquet metadata.
4. Reject sidecar and embedded manifest mismatches.
5. Validate physical Parquet fields and types.
6. Validate GIDs against the trusted domain registry and profile.
7. Validate `gid`, `packed_id`, `x_idx`, and `y_idx` consistency.
8. Enforce duplicate rules by dataset type.
9. Validate coverage and length ratios.
10. Validate declared row and unique-cell counts.
11. Return a `CellDataset` object that can expose Arrow/Pandas views without losing metadata.

Use existing registry and grid primitives rather than duplicating identity logic:

```text
DomainRegistry
GeosquareGrid.canonical_from_gid
GeosquareGrid.pack
GeosquareGrid.unpack
```

### Gate B: passed

The local contract passes:

```text
local write → local read → validate
```

The Phase 2 suite covers compact, queryable, and contribution datasets, sidecar/embedded metadata mismatches, missing metadata, undeclared columns, wrong types, invalid GIDs, duplicate GIDs, packed identity mismatches, ratio bounds, nullability, and destination safety. The focused dataset tests and complete suite both pass.

## 7. Phase 2 — Add dataset fixtures and validation tests

### Status: complete

The local storage validation fixtures and tests are complete. They cover compact, queryable, and contribution datasets; sidecar/embedded metadata; invalid schemas and rows; identity consistency; duplicate policy; ratio bounds; nullability; and destination safety. The original suite continues to pass alongside these tests.

## 8. Phase 3 — Add query support

### Status: complete

Completed on 2026-10-01 for local queryable Parquet datasets.

### API

```python
query_cell_dataset(
    "path/to/dataset/",
    bbox=(min_lon, min_lat, max_lon, max_lat),
    domain="ID",
    level=12,
    registry=trusted_registry,
)
```

### Implemented requirements

The query layer now:

1. Reads and validates the manifest before scanning Parquet data.
2. Requires a trusted `DomainRegistry` and validates the requested domain and level.
3. Requires complete `packed_id`, `x_idx`, and `y_idx` query metadata.
4. Validates WGS84 bbox coordinates and latitude/longitude ordering.
5. Supports antimeridian-crossing bboxes by splitting them into two windows.
6. Transforms bbox corners into the trusted profile grid CRS using `always_xy`.
7. Calculates and clamps candidate x/y windows to the profile root.
8. Uses `pyarrow.dataset` predicate filters.
9. Returns a filtered PyArrow table without constructing cell geometries.
10. Preserves canonical `geosquare.manifest` metadata on the result.
11. Returns an empty schema-preserving table when no candidate cells match.
12. Rejects compact GID-only datasets because they lack a rectangular query index.

### Query tests

The five focused query tests cover:

- valid bbox filtering;
- manifest metadata preservation;
- domain and level mismatch;
- compact dataset rejection;
- invalid bbox coordinates;
- no-match/out-of-profile results; and
- antimeridian splitting.

### Gate C: passed

A query against a queryable local dataset returns the expected cells using x/y predicate filtering without materializing cell geometries. S3 and remote filesystem query support remain deferred.

## 9. Phase 4 — Implement geometry-table conversion

### Status: complete

Completed on 2026-10-01. `geometry_table_to_cells` now produces auditable Pandas contribution rows using the existing point, line, and polygon conversion algorithms.

### API

```python
geometry_table_to_cells(
    source,
    service,
    domain_code,
    level,
    geometry_column="geometry",
    source_id_column="asset_id",
    source_crs="EPSG:4326",
)
```

### Implemented geometry support

```text
Point
MultiPoint
LineString
MultiLineString
Polygon
MultiPolygon
```

### Contribution output

Each generated row preserves:

```text
source payload columns
source_id or source_row
domain
level
gid
uri
coverage_ratio
length_ratio
assignment_method
boundary_policy
```

The implementation supports projected or WGS84 point inputs, selected source payload columns, explicit `OperationalBoundary` filtering, and nullable per-row coverage/length ratios for mixed geometry tables. `boundary_policy` is now a reserved contribution column in the contract/schema.

The applicable ratio depends on geometry type:

- polygon: area coverage ratio;
- line: length ratio;
- point: assignment method and point-to-cell identity.

This stage does not allocate values or aggregate contributions.

### Focused tests

Six geometry-table tests cover all supported geometry families, source provenance, boundary filtering, invalid inputs, projected point inputs, and validation through `CellDataset` as a `cell_contributions` dataset.

### Gate D: passed

A source geometry table can be converted into a valid, auditable `cell_contributions` table, and every contribution can be traced to a source feature and assignment rule.

## 10. Phase 5 — Add geometry-aware allocation and aggregation

### Status: complete

Completed on 2026-10-01. The new public API separates contribution weights, value allocation, semantic aggregation, and provenance metadata.

### APIs

```python
aggregate_geometry_contributions(
    contributions,
    value_semantics="TOTAL",
    value_column="population",
)

aggregate_geometry_table_to_cells(
    source,
    service,
    domain_code,
    level,
    value_semantics="TOTAL",
    value_column="population",
    geometry_options={...},
)
```

### Implemented semantic rules

- `COUNT`: one unit per contribution row.
- `TOTAL`: multiply each source value by its normalized coverage or length share, then sum by cell.
- `DENSITY`: ratio-weighted mean; the result remains a density rather than an integrated total.
- `MEASUREMENT`: ratio-weighted mean.
- `RATE`: ratio-weighted mean by default, or weighted numerator/denominator aggregation when both are supplied.
- `ORDINAL`: explicit priority-order aggregation.
- `CATEGORICAL`: explicit category rule aggregation.
- `RANGE`: explicit min/max, full-range, weighted-mean, or distribution aggregation through the existing range rules.

The selected `value_semantics`, `allocation_rule`, source value column, and pipeline stage are recorded in `DataFrame.attrs["geosquare"]`. Zero rate denominators, ambiguous ratio columns, missing required fields, invalid semantics, and invalid contribution weights are rejected.

Polygon contribution ratios are normalized per source geometry before allocation so a source total is conserved across all intersected cells. Line ratios are length-normalized by the existing line conversion.

### Focused tests

Six focused aggregation tests cover ratio-weighted totals and means, unit counts, numerator/denominator rates, categorical/ordinal/range dispatch, high-level geometry conversion plus aggregation, provenance metadata, and invalid rules.

### Gate E: passed

Every geometry-aware aggregate is explainable from source geometry, contribution rows, allocation rule, semantic rule, and final cell aggregation. The focused and complete suites pass.

## 11. Phase 6 — Add optional filesystem and S3 support

### Status: complete

Completed on 2026-10-01. The local manifest-plus-Parquet format remains authoritative, and optional fsspec access now supports local, memory, and S3-style URLs without adding filesystem dependencies to the base package.

### Optional dependencies

```toml
filesystem = ["fsspec==2025.7.0"]
s3 = ["fsspec==2025.7.0", "s3fs==2025.7.0"]
```

`s3fs` is not required for the in-memory S3-compatible tests and no live AWS credentials are required by the test suite.

### APIs

```python
write_cell_dataset_filesystem(dataset, "memory://bucket/path/")
read_cell_dataset_filesystem("s3://bucket/path/", filesystem=fs)
query_cell_dataset_filesystem(
    "memory://bucket/path/",
    bbox=(min_lon, min_lat, max_lon, max_lat),
    registry=trusted_registry,
)
```

The filesystem backend:

- writes the same `manifest.json` and `data/part-00000.parquet` layout;
- embeds the same canonical `geosquare.manifest` metadata;
- validates sidecar and embedded manifests;
- uses temporary prefixes before moving completed remote output;
- supports injected filesystem objects for S3-compatible testing;
- preserves local query validation and result semantics; and
- does not add `boto3` to core dependencies.

Local `query_cell_dataset` retains `pyarrow.dataset` predicate pushdown. The backend-neutral filesystem query path reads validated fragments and applies equivalent Arrow table filters, which keeps behavior consistent across fsspec backends without assuming a specific remote filesystem implementation.

### Tests

Five focused filesystem tests cover memory round trips, S3-style URL handling with an injected memory filesystem, filesystem query behavior, missing sidecars, embedded-manifest mismatches, and destination collisions.

### Gate F: passed

A dataset written through the fsspec backend is readable and queryable without changing its manifest, Parquet format, or validation behavior. Live AWS credentials are not required for the test suite.

## 12. Packaging and distribution work

Before any later publication review:

1. Keep the contract documentation, runtime schema, attribution notice, and
   package-data configuration explicit.
2. Confirm the runtime JSON schema and `NOTICE` are present in the wheel and
   sdist as appropriate.
3. Preserve the signed registry database/signature, all packaged boundaries,
   and their source metadata without editing signed artifacts.
4. Build a fresh wheel and sdist into the isolated `dist-candidate/` directory;
   never reuse or regenerate tracked `dist/` 0.1.0 artifacts.
5. Inspect both archives, run `twine check dist-candidate/*`, and install both
   artifacts in clean temporary environments.
6. Run registry, schema, boundary, import, and public-API smoke tests from the
   installed artifacts.

The root contract Markdown file must not be assumed to be included in the wheel
merely because it exists in the repository. `NOTICE` is an explicit release
input; boundary redistribution approval remains unresolved.

## 13. Legal, security, and release decisions

### 13.1 Candidate versus production profiles

The signed registry currently contains candidate ASEAN profiles. Before a production release, choose one of:

1. approve the static candidate policy for the release;
2. replace candidate profiles with correct national datum CRSs; or
3. label the package clearly as a technical candidate.

The package and documentation must not imply production geodetic status if that approval has not occurred.

### 13.2 Boundary-data licensing

The evidence-backed attribution is in `NOTICE`, based only on the source notes,
metadata, mirrored package source notes, and profile source fields. It lists all
included full and simplified candidate boundaries by recorded source/license.
The notice does not assert redistribution permission. Approval for every file
remains a blocker, and the full boundary set remains packaged for this local
candidate because the signed registry and `verify_boundaries=True` path require
it.

### 13.3 Package size

The tracked historical artifacts are 17,440,667 bytes for the wheel and
34,580,131 bytes for the sdist. Fresh `dist-candidate/` sizes must be recorded
in the evidence. Full boundaries remain packaged for this technical candidate;
explicit package-size approval is still a blocker.

### 13.4 Secret handling

- Keep the new private signing key outside the repository.
- Never include a private key in the wheel, sdist, source tree, or release upload.
- Do not reuse the old compromised private key.
- Run a secret scan before TestPyPI and again before PyPI.

## 14. PyPI release plan — not yet published

No release has been uploaded to PyPI or TestPyPI yet. Publishing is a later gated activity, not part of the initial implementation work.

### Recommended version

Use:

```text
0.1.0rc1
```

while the profiles remain candidate/static and the dataset distribution layer is still being validated. Reserve:

```text
0.1.0
```

for the first approved production release.

Confirm the final version in package metadata before building. Do not upload artifacts whose metadata still says an unintended version.

### Pre-upload release gates

The following must pass before any upload:

- full test suite;
- dataset manifest and Parquet tests;
- local query tests;
- geometry contribution and aggregation tests;
- `pip check`;
- package metadata checks;
- local Markdown link checks;
- JSON artifact parsing;
- profile and boundary hash checks;
- wheel installation;
- sdist installation;
- `twine check dist-candidate/*`;
- package-content inspection;
- final secret scan;
- boundary-license review;
- explicit candidate/production profile decision.

### Publication workflow

TestPyPI and PyPI publication are deferred and explicitly out of scope for this
release-hardening task. Do not run upload commands or contact either index.
After a human resolves the boundary redistribution, technical-candidate
geodetic-status, and package-size blockers, a later release workflow may define
publication and post-publication installation checks. The local candidate gate
for this task is:

```zsh
.venv/bin/python -m build --sdist --wheel --outdir dist-candidate
.venv/bin/twine check dist-candidate/*
```

Install and smoke-test the two local artifacts from `dist-candidate/` in clean
temporary environments. Record the results in `.agents/tasks/evidence.md`.
Never reuse the tracked 0.1.0 artifacts under `dist/`.

## 15. Final ordered checklist

### Implementation

- [x] Reconcile the stale handover Git state.
- [x] Approve dataset contract semantics.
- [x] Decide reserved columns and value-field behavior.
- [x] Decide schema-validation dependency strategy: standard-library runtime validation for Phase 1.
- [x] Package the runtime JSON schema.
- [x] Implement `CellDatasetManifest`.
- [x] Add focused manifest validation tests.
- [x] Implement local Parquet writer.
- [x] Implement local Parquet reader.
- [x] Embed and verify manifest metadata in Parquet files.
- [x] Add compact, queryable, and contribution fixtures.
- [x] Add invalid-manifest and invalid-data tests.
- [x] Implement dataset query support.
- [x] Implement geometry-table conversion.
- [x] Implement semantic value allocation.
- [x] Implement geometry-aware aggregation.
- [x] Add optional filesystem support.
- [x] Add S3-compatible integration coverage.

### Release preparation

- [x] Review candidate versus production profile status; retain technical-candidate scope.
- [x] Review boundary source/license evidence and add `NOTICE`; redistribution approval remains a blocker.
- [x] Keep full and simplified boundary resources packaged because the signed registry and `verify_boundaries=True` path require them.
- [x] Set authoritative package metadata and runtime `__version__` to `0.1.0rc1` only.
- [x] Add explicit sdist/wheel inclusion for `NOTICE` and the runtime schema.
- [x] Preserve tracked 0.1.0 artifacts and tracked `.DS_Store` files unchanged.
- [x] Build fresh wheel and sdist in `dist-candidate/`.
- [x] Inspect archive contents, metadata, registry, signature, schema, boundaries, and sizes.
- [x] Run the fail-closed source/release-input/archive secret scan.
- [x] Run `twine check`, `pip check`, compile checks, the current 195-test suite, and both clean installs.
- [ ] Obtain explicit approval for boundary redistribution and `NOTICE` accuracy.
- [ ] Obtain explicit approval to distribute static/candidate profiles as a `0.1.0rc1` technical candidate.
- [ ] Obtain explicit approval for the package size while retaining full boundaries.
- [x] Confirm no TestPyPI or PyPI upload occurred; publication remains out of scope.

### Publication

- [ ] Upload to TestPyPI — deferred and not part of this task.
- [ ] Install from TestPyPI — deferred and not part of this task.
- [ ] Obtain explicit production-release approval.
- [ ] Create the release tag.
- [ ] Upload to production PyPI — deferred and not part of this task.
- [ ] Install and verify the production release.
- [ ] Record release hashes and provenance.

## 16. Release-hardening result

The `0.1.0rc1` candidate was prepared locally only, with no TestPyPI/PyPI
upload, commit, tag, push, or Git-history change. Tracked `dist/` artifacts and
`.DS_Store` files were preserved.

Candidate artifacts:

```text
dist-candidate/geosquare_grid_v2-0.1.0rc1-py3-none-any.whl
dist-candidate/geosquare_grid_v2-0.1.0rc1.tar.gz
```

Exact byte sizes and SHA-256 hashes are recorded in
`.agents/tasks/evidence.md`.

`twine check`, `pip check`, compileall, the current 195-test suite, complete
archive inspection, the fail-closed source/archive secret scan, and clean wheel
and sdist installs all passed. The installed smoke tests verified version
`0.1.0rc1`, packaged schema/boundaries/NOTICE, 11-domain signed registry
loading, and `geosquare:v2:ID:H2X545V39`. Detailed command coverage is in
`.agents/tasks/evidence.md`.

The three approval blockers remain: boundary redistribution and `NOTICE`
accuracy, approval of the static/candidate geodetic profiles as a technical
candidate, and package-size approval while retaining full boundaries.
