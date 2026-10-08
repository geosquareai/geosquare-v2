# Changelog

## 0.2.0 — proposed stable software release under option 2

Status: prepared in an isolated release worktree and not published. This release may bundle all 11 domain profiles while explicitly classifying KH, MM, TH, and TL as technical/provisional. Production geodetic guarantees apply only to profiles individually approved through Gate A.

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
