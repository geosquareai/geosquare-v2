# Gate C contract freeze

**Release:** `0.2.0`
**Registry version:** `2.0.0`
**Profile version:** `2.1.0-static-datum`
**Decision date:** `2026-10-08`
**Status:** frozen for the isolated stable-release candidate

This record freezes the public identity, API, migration, dataset, profile, and support-scope contracts for the `0.2.0` release. It does not authorize signing, publication, or a claim that the custom CRSs are official national projected CRSs.

## Canonical identity

The durable cell identity is exactly:

```text
(domain_code, level, x_idx, y_idx)
```

Rules:

- `domain_code` identifies the country/domain profile;
- `level` is an integer from `0` through `14`;
- `x_idx` and `y_idx` are validated Cartesian indices at that level;
- the root is one 50,000,000 m square; and
- GIDs, packed IDs, geometry, and URIs are derived representations.

The V2 hierarchy uses the fixed alternating subdivision sequence:

```text
5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2
```

## URI and GID contract

The canonical durable URI is:

```text
geosquare:v2:<domain_code>:<gid>
```

A bare GID does not contain its domain and must not be stored as the sole durable identifier. The level-0 root has an empty bare GID and therefore uses a trailing colon in the full URI.

`parse_uri()` is a syntactic parser only. Registry-backed service methods perform domain/profile/GID validation. The URI carries the V2 grid version and domain; durable datasets must also retain `profile_version` and `registry_version` in their manifest because the URI alone does not identify the exact profile bytes.

## Version contract

The stable candidate freezes:

| Item | Frozen value |
|---|---|
| Package version | `0.2.0` |
| Python import version | `geosquare_v2.__version__ == "0.2.0"` |
| Registry version | `2.0.0` |
| Profile version | `2.1.0-static-datum` |
| Support policy | option 2 |
| Production-ready domains | BN, ID, LA, MY, PH, SG, VN |
| Provisional technical domains | KH, MM, TH, TL |

The machine-readable support classification is [`DOMAIN_SUPPORT_MATRIX.json`](../release/profiles/DOMAIN_SUPPORT_MATRIX.json).

## Public API contract

Canonical service names are:

```text
point_to_cell       polygon_to_cells       polygon_to_cell
line_to_cells       cell_to_geometry       cells_to_geometry
table_to_cells      aggregate_to_cells     cell_neighbours
cell_distance       describe
```

Compatibility names remain available:

- `index_point` delegates to `point_to_cell`;
- `neighbourhood` remains the legacy ring/disk method;
- `distance` remains the legacy distance method;
- `cell_neighbours` and `cell_distance` are canonical wrappers for the legacy methods; and
- `polyfill` remains a legacy bare-GID/coverage API and is **not** a return-type alias for `polygon_to_cells`.

Return contracts are frozen as follows:

- `polygon_to_cells` returns `GridCellRecord` values containing cell, GID, URI, and coverage metadata;
- `polyfill` returns `(bare_gid, coverage_ratio)` pairs for compatibility; and
- `line_to_cells` returns records with length coverage metadata.

## Dataset and migration contract

A cell dataset manifest must carry one domain, one level, one `profile_version`, and one `registry_version`. It must retain the versioned URI/GID identity context and the boundary hash used for assignment.

V1 and V2 are different ID systems. There is no safe string conversion from a V1 GID to a V2 GID. V1 migration remains coordinate-preferred, centroid-fallback for point data, and one-to-many for area data. Migration records retain source/target versions, profile version, method, CRS, source bounds, coverage mode, and coverage ratio.

## Profile and CRS contract

Each profile uses a GeoSquare-owned custom CRS identifier and WKT2 definition. The seven production-ready profiles are approved within the GeoSquare support scope; KH/MM/TH/TL remain provisional technical profiles. `EPSG:8857` is the equal-area analysis CRS, not a claim that the GeoSquare custom projected CRS is an official national projected CRS.

ID is explicitly static: inputs must already be normalized to the SRGI2013 realization at epoch `2012.0`; the runtime does not perform dynamic epoch transformation. Dynamic epoch transformations are outside this frozen contract.

## Compatibility evidence

The freeze is supported by the core conformance, facade, migration, boundary-policy, dataset-manifest, and targeted API tests. Final Gate D validation must run the same contract tests against the exact signed stable registry and built artifacts; this record does not replace that validation.

This contract freeze is a GeoSquare project decision and is not an official authority endorsement or legal advice.
