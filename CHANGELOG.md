# Changelog

## 1.3.0 — manifest 1.1 and reading of 1.0.0 datasets

Status: prepared. Not yet published.

### Reading datasets written by 1.0.0

- readers accept profile `2.1.0-static-datum`, written by geosquare-v2 1.0.0, for all 11 domains. Writers refuse it.
- each manifest reports `profile_status`: `current`, `legacy_same_gids` or `legacy_gids_differ`.
- reading a dataset for VN or LA written under the legacy profile emits a warning. Their GIDs differ from the current profile for some points.
- added 1.0.0 regression fixtures and `tests/test_legacy_profile_read.py`.
- added `docs/profile-compatibility.md` with the measurements.
- limits: the current code refuses VN points outside the datum area of use (10.4% of sampled box points) and LA points outside it (6.0%). Points that 1.0.0 indexed are now refused. Which VN and LA result is correct is an open decision. See the doc.

### Manifest 1.1

- `CellDatasetManifest` reads manifest 1.1. Manifest 1.0 is unchanged.
- Manifest 1.1 adds per-column `space_aggregation`, `space_weight`, `null_share`, `min_value` and `max_value`; `extent`; `governance`; `storage.data_files` with `content_sha256`; and `provenance.spec_version` and `derived_from`. Rules are in `docs/dataset-metadata.md`.
- `CellDataset` checks 1.1 content hashes, row counts and column statistics against the data.
- added `geosquare_v2.cell_metadata` with `content_sha256`, `data_file_entry` and cross-field checks.
- limits: `extent.bbox_wgs84` is not checked against the cells yet. There is no packaged JSON schema for 1.1 yet. `CellDatasetManifest.schema()` still returns the 1.0 schema.

## 1.2.0 — stores for cell_compact_set and cell_time_values

Status: published on PyPI.

### Changes

- added `geosquare_v2.compact_store` to write and read `cell_compact_set` datasets;
- added `geosquare_v2.time_store` to write and read `cell_time_values` datasets, including hour buckets in UTC;
- every read checks the manifest, columns, row count and rules, and rejects bad data without repair;
- added the `cell_compact_set` and `cell_time_values` rules to the contract (no change to `cell_values` or `cell_contributions`);
- added the `cell_time_values` reference rules and 28 conformance cases.

### Validation

- targeted tests: compact, time-cube and store suites pass;
- the full suite is run before the TestPyPI upload.

### Limits

- there is no JSON schema file for the two new types yet;
- partitioning for time values is not defined.

## 1.1.0 — explicit datum pipelines and provisional VN support

Status: published to PyPI on 2026-11-18. See the [GitHub release](https://github.com/geosquareai/geosquare-v2/releases/tag/v1.1.0).

### Changes

- added explicit WGS 84-to-grid datum pipelines for `ID`, `LA`, `PH`, and `VN`;
- added signed registry metadata for the explicit datum rules;
- added 300-point pipeline parity QA for every domain;
- added explicit opt-in for provisional VN support through `EPSG:6960`; and
- kept VN outside the default production path.

### Validation

- GitHub tests passed;
- a clean Python 3.12 installation passed;
- signed registry loading passed; and
- VN opt-in indexing passed.

### Limits

- VN remains a provisional technical candidate;
- this release does not claim VN field accuracy; and
- Python 3.15 support remains a separate follow-up because the pinned PROJ version is unavailable there.

## 2.2.0-rc1 — explicit datum QA candidate

Status: engineering candidate. No domain has a production guarantee yet.

### Changes

- added a required `datum_transformation` object to every profile;
- wrote complete WGS 84 longitude/latitude to grid pipelines;
- selected `INVERSE(EPSG:15912) + EPSG:9472` for ID;
- selected `INVERSE(EPSG:1065)` for LA;
- selected `INVERSE(EPSG:15708)` for PH;
- selected `INVERSE(EPSG:6960)` for VN as a provisional, opt-in operation;
- added 300-point pipeline parity QA for every domain; and
- added a runtime gate for candidate and blocked profiles.

### Limits

- ID, LA, and PH have no independent field-accuracy check. Their stated accuracy is the value written by the operation source.
- Control points are not a release requirement. Accuracy claims cite the operation source, not a GeoSquare field test.
- VN remains provisional because competing EPSG operations still exist.
- The report proves repeatable numbers, not field accuracy.
- The registry must be rebuilt and signed before release.

## 1.0.0 — first stable major release

Status: published to PyPI on 2026-11-17. Versions `0.1.0rc1`, `0.1.0rc2`, and `0.2.0` are also on PyPI. 1.0.0 carries the frozen 0.2.0 contract forward.

### Support scope (option 2)

- Production-ready within the GeoSquare support scope: `BN`, `ID`, `LA`, `MY`, `PH`, `SG`, `VN`.
- Provisional technical candidates, marked with an asterisk: `KH*`, `MM*`, `TH*`, `TL*`. They stay bundled under their `GEOSQUARE:*` identifiers. They have no official national-datum, authoritative-transformation, or production-accuracy guarantee.

### Notes

- Custom projected CRSs are GeoSquare-owned. They are not official national projected CRSs.
- ID inputs must already be normalized to the SRGI2013 realization at epoch `2012.0`. The runtime does not apply dynamic epoch transformations.
- Bundled boundaries keep their file-specific licenses. See [NOTICE](NOTICE).
- The package classifier is `Development Status :: 5 - Production/Stable`. The support matrix above, not the classifier, defines which domains carry a production guarantee.

## 0.2.0 — published to PyPI on 2026-10-08 (superseded by 1.0.0)

Status: published to PyPI on 2026-10-08. This release may bundle all 11 domain profiles while explicitly classifying KH, MM, TH, and TL as technical/provisional. Production geodetic guarantees apply only to profiles individually approved through Gate A.

### Release preparation

- promoted the reviewed static-datum successor inputs from `0.1.0rc2`;
- selected `0.2.0` because the successor changes CRS/profile behavior while preserving the pre-1.0 API contract;
- retained GeoSquare-owned custom CRS identifiers rather than inventing EPSG codes;
- retained the static ID realization and no-dynamic-transformation limitation;
- corrected the malformed Philippines license-source placeholder to the canonical CC BY 3.0 IGO license text, while keeping upstream-source and redistribution approval open; and
- regenerated release metadata in the isolated worktree pending final registry signing and release authorization.

## 0.1.0rc2 — staged static-datum technical candidate

Status: staged locally and not uploaded. The previous `0.1.0rc1` candidate was uploaded to TestPyPI and verified from a clean Python 3.14 environment. This successor must be reviewed before any TestPyPI or PyPI upload.

### Changes

- added static GeoSquare custom CRS profiles based on GDBD2009 for BN, Lao 1997 for LA, GDM2000 for MY, PRS92 for PH, and SVY21 for SG;
- added the ID SRGI2013 static realization at epoch 2012.0, with an explicit pre-normalized-input limitation;
- retained the VN-2000 baseline;
- kept KH and MM pending authoritative CRS packages;
- kept TH on its existing technical profile because TGM2017 is a vertical/geoid model rather than a horizontal CRS;
- kept TL provisional because no verified modern national horizontal datum is available; and
- added a staged successor generator and registry/artifact validation workflow.

### Candidate limitations

- The custom projected CRSs are GeoSquare-owned technical projections, not claims that they are official national projected CRSs.
- The static policy does not perform dynamic coordinate-epoch, tectonic, or deformation transformations.
- ID inputs must already be normalized to the SRGI2013 static realization at epoch 2012.0.
- Bundled boundary data remains under its recorded file-specific licenses.

## 0.1.0rc1 — ASEAN V2 technical candidate

Status: uploaded to TestPyPI and verified from a clean Python 3.14 environment. Not uploaded to PyPI or Conda. The candidate remains non-production; its profile and boundary data are distributed with their documented technical and file-specific limitations. See [NOTICE](NOTICE) and [the release guide](docs/release.md).

### Added

- 11 ASEAN country domains in the signed candidate registry;
- projected square geometry computed on read;
- alternating 5x5 and 2x2 hierarchy;
- GID and packed signed Int64 codecs;
- parent, children, neighbours, rings, disks, and same-level distance;
- boundary policies for points, cells, polyfill, and neighbourhoods;
- point, polygon, and line to cell conversion;
- optional cell geometry output;
- CSV, XLSX, Parquet, and Pandas table input;
- selected source-field retention;
- numeric, categorical, ordinal, and range aggregation;
- V1 point and area migration adapter;
- signed SQLite registry loading;
- full ASEAN boundary metadata and source attribution;
- profile and cross-system benchmarks; and
- complete Markdown documentation.

### Release notes

- Country profiles are release candidates.
- Custom WGS84-style candidate profiles use a static/no-dynamic-epoch policy until national datum approval is complete.
- The registry is signed with an Ed25519 key stored outside the repository.
- The project has passed the current pinned 195-test suite.
- Fresh wheel and sdist installation checks are required for `0.1.0rc1` and
  must use `release/artifacts/dist-candidate/`, not the archived `release/artifacts/dist/` files.
- Boundary attribution and the open redistribution gate are recorded in
  `NOTICE`.
