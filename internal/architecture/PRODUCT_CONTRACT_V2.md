# GeoSquare V2 Product Contract

**Status:** Locked product contract for V2
**Version:** 2.0
**Date:** 2026-09-18
**Technical companion:** [V2SPECS.md](V2SPECS.md)

This document defines what users should be able to expect from GeoSquare V2.

`V2SPECS.md` defines the low-level encoding and implementation rules. This document defines the product meaning. If the two documents disagree, update both documents before changing code.

## 1. Product promise

GeoSquare gives every location a stable, hierarchical square-grid address.

The system should be:

- easy to explain;
- based on a clear size hierarchy;
- usable across one country at a time;
- computable from a compact ID;
- useful for neighbours, distance, and polyfill; and
- reproducible from a signed domain profile.

The exact machine identity is more important than the human-friendly label.

## 2. Canonical identity

The canonical V2 identity is:

```text
(domain_code, level, x_idx, y_idx)
```

These fields are the source of truth.

The following are derived forms:

- GID string;
- packed signed `Int64`;
- projected square geometry; and
- WGS84 display geometry.

Durable data must use a versioned and domain-qualified URI:

```text
geosquare:v2:<domain_code>:<gid>
```

Example:

```text
geosquare:v2:ID:2G4M3N8P
```

A bare GID is allowed only when the V2 version and domain are already fixed by the API context. It must not be the only ID in a database, API response, event, or exported file.

V2 is not wire-compatible with V1. A V1 GID must never be silently decoded as a V2 GID.

## 3. Hierarchy and sizes

V2 uses this fixed subdivision sequence:

```text
[5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2]
```

The root side is 50,000 km.

| Level | Grid-CRS cell edge |
|---:|---:|
| 0 | 50,000 km |
| 1 | 10,000 km |
| 2 | 5,000 km |
| 3 | 1,000 km |
| 4 | 500 km |
| 5 | 100 km |
| 6 | 50 km |
| 7 | 10 km |
| 8 | 5 km |
| 9 | 1 km |
| 10 | 500 m |
| 11 | 100 m |
| 12 | 50 m |
| 13 | 10 m |
| 14 | 5 m |

The level-0 GID is the empty string. It still needs domain and version context.

Removing the last GID character gives the parent. Adding one valid character gives a child.

A base-5 refinement has 25 children. A base-2 refinement has 4 children.

Level 14 is the current V2 leaf. V2 does not include a 1 m level.

If 1 m is needed later, it must use a new ID encoding or a new major version. It must not change the meaning of existing V2 levels.

## 4. Meaning of “50 m square”

A V2 cell is an exact square in its domain’s canonical projected CRS.

“50 m” means 50 m per side in that CRS. It does not promise an exact 50 m by 50 m ground patch everywhere on Earth.

Each signed profile must publish its measured scale error.

User-facing results should expose:

- grid-CRS cell size;
- profile version;
- maximum published scale error; and
- the fact that the size is a grid-CRS measurement.

The system must not claim that every country has the same physical accuracy.

## 5. Country domains and registry

Each country domain has its own signed profile.

A profile must define at least:

- domain ID and code;
- profile version;
- origin and root size;
- canonical grid CRS in WKT2;
- equal-area CRS in WKT2;
- a reference epoch, or an explicit `null` static/no-dynamic-epoch policy;
- operational boundary and its hash;
- scale-error metadata; and
- required PROJ version and resources.

The registry is a release artifact. It is not mutable runtime configuration.

A registry release must be reproducible and signed.

The private signing key must stay outside the repository and outside distributed packages. It should be kept offline or in a secure signing system.

The public trust key may be distributed to applications. It is not secret.

Deleting the old keys means the current candidate database must be signed again with a new key pair before release.

## 6. Mathematical root and country boundary

The mathematical root is complete. Every cell inside it has a valid mathematical identity.

The country boundary is an operational filter. It is not part of the cell identity.

Core grid operations must not silently apply a country boundary.

Country-facing APIs must make the boundary behavior visible and selectable.

Supported boundary predicates are:

- `COVERS_POINT`: the boundary covers the input point, including the boundary line;
- `CENTROID_COVERED`: the cell centroid is inside the boundary;
- `INTERSECTS`: the cell and boundary have a positive-area intersection; and
- `MIN_COVERAGE`: the cell meets a declared boundary-coverage threshold.

Recommended defaults for the high-level API:

- point indexing: `COVERS_POINT`;
- general polyfill: `INTERSECTS`; and
- official or statistical analysis: `MIN_COVERAGE` with an explicit threshold.

The current `MIN_COVERAGE` boundary check measures area in the grid CRS. For high-accuracy statistical area work, use `EQUAL_AREA` polyfill coverage as well and record both rules.

The selected boundary predicate and boundary version must be available in result metadata.

Boundary verification and boundary filtering are different:

- verification checks that the boundary file matches the signed profile;
- filtering decides which cells an application wants to use.

## 7. Point indexing

The point-indexing flow is:

```text
longitude/latitude
  → profile CRS transformation
  → epoch handling
  → root check
  → level and x/y index
  → canonical identity
  → GID, URI, or packed ID
```

Longitude must be treated as X and latitude as Y. Transformers must use `always_xy=True`.

The outer root edge is included in the last cell. Internal cell edges use lower-inclusive and upper-exclusive intervals.

A point outside the mathematical root is invalid for that domain.

A point inside the root but outside the country boundary is mathematically valid. A country-facing API may reject it or return a policy result, depending on the selected boundary mode.

No API may infer an epoch from the system clock.

## 8. Geometry

The authoritative geometry is the projected square derived from:

```text
profile origin + cell index × cell size
```

The geometry is computed on read. It is not stored as a permanent polygon table.

WGS84 geometry is for display and interchange. Large cells must use edge densification before reprojection.

A WGS84 polygon must not replace the projected square as the identity geometry.

## 9. Neighbours and distance

Neighbourhood operations use integer indices.

They must not use:

- GID lexical order;
- polygon buffering; or
- web-map tile relationships.

`k_disk(k)` includes cells with:

```text
max(abs(dx), abs(dy)) <= k
```

`k_ring(k)` includes cells with:

```text
max(abs(dx), abs(dy)) == k
```

The source cell is included when `k == 0`.

Results are clipped to the mathematical root first. A selected country-boundary predicate may then filter them.

Grid distance is defined only for cells at the same level in V2:

```text
hypot(x2 - x1, y2 - y1) × cell_edge_m
```

This is Euclidean distance in the profile grid CRS. It is not a geodesic distance and it does not account for roads or terrain.

Cross-level distance needs a separately defined API. It must not be guessed from packed IDs or string prefixes.

## 10. Polyfill

Polyfill must:

1. accept a geometry and its source CRS;
2. transform it with `always_xy=True`;
3. normalize or reject invalid geometry;
4. clip work to the mathematical root;
5. check the candidate limit before enumeration;
6. derive cells procedurally;
7. return deterministic results; and
8. expose the coverage rule.

Coverage modes are:

- `GRID_PLANAR`: area is measured in the grid CRS;
- `EQUAL_AREA`: area is measured in the profile’s equal-area CRS.

`EQUAL_AREA` is the default choice for coastal, cross-projection, and published statistical results.

Polyfill must not silently apply the country boundary. The high-level country API must accept an explicit boundary predicate.

## 11. Migration from V1

V1 and V2 have different roots, level behavior, coordinate semantics, and character rules.

There is no safe direct string conversion.

V1 migration must be a separate adapter with explicit source and target versions.

For point records:

- use the original source coordinates when available;
- otherwise use a documented representative point; and
- record the method and uncertainty.

For area records:

- decode the legacy cell geometry;
- reprocess it through V2 polyfill; and
- allow one V1 cell to produce many V2 cells.

Every migration result must retain:

- source ID and version;
- target URI and profile version;
- target level and domain;
- migration method;
- coverage mode and threshold; and
- provenance.

## 12. Human aliases

A human alias is a presentation label. It is not the canonical identity.

An alias must:

- resolve to a versioned V2 URI;
- have its own version;
- remain separate from geometry and topology;
- show or imply scale clearly;
- work for rural, oceanic, and remote cells; and
- avoid random words unless testing proves they help users.

Aliases are deferred until the canonical ID, registry, boundary rules, and migration behavior are stable.

## 13. Release gates

V2 is not production-ready until all of these are true:

- no private signing key is in the repository;
- the registry layout works from a clean wheel and sdist install;
- a new key pair signs the released registry;
- trusted applications can verify the signature;
- all 11 ASEAN profiles pass root, CRS, boundary, and scale checks;
- scalar codec, hierarchy, packing, topology, distance, geometry, and polyfill fixtures pass;
- batch and warehouse outputs match scalar reference results;
- boundary predicates are tested on multipolygons and islands;
- the V1 migration adapter has point and area fixtures; and
- the public API documents profile, boundary, and epoch assumptions.

## 14. Deferred work

The following work is intentionally deferred:

- 1 m cells in the current V2 encoding;
- cross-level distance;
- Hilbert or Peano locality keys;
- automatic global country selection without an explicit registry policy;
- adding many countries before profile certification is proven; and
- human aliases before the canonical system is stable.

These items can return as separate, versioned features. They must not weaken the V2 identity contract.
