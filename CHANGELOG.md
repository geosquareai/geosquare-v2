# Changelog

## 2.2.0-rc1 — explicit datum QA candidate

Status: engineering candidate. No domain has a production guarantee yet.

### Changes

- added a required `datum_transformation` object to every profile;
- wrote complete WGS 84 longitude/latitude to grid pipelines;
- selected `INVERSE(EPSG:15912) + EPSG:9472` for ID;
- selected `INVERSE(EPSG:1065)` for LA;
- selected `INVERSE(EPSG:15708)` for PH;
- selected `INVERSE(EPSG:6960)` for VN, but kept VN blocked;
- added 300-point pipeline parity QA for every domain; and
- added a runtime gate for candidate and blocked profiles.

### Limits

- ID, LA, and PH still need independent control points.
- VN has two competing EPSG operations and stays blocked.
- The report proves repeatable numbers, not field accuracy.
- The registry must be rebuilt and signed before release.

## 1.0.0 — first stable major release

Status: prepared in the isolated `release/v1.0.0` worktree and not published. Versions `0.1.0rc1`, `0.1.0rc2`, and `0.2.0` are already on PyPI. 1.0.0 carries the frozen 0.2.0 contract forward.

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
