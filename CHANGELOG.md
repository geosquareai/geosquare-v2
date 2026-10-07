# Changelog

## 0.1.0rc1 — ASEAN V2 technical candidate

Status: local candidate preparation only. Not uploaded to TestPyPI or PyPI.
The candidate remains non-production and is subject to the boundary
redistribution, geodetic-status, and package-size approval gates. See
[NOTICE](NOTICE).

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
