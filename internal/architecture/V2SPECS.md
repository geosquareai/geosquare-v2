# Geosquare Core Specification v2.0

**Status:** implementation baseline
**Scope:** normative contract for the current country-domain candidate release, including the ASEAN profiles in the signed candidate registry.
**Supersedes:** the proposed implementation details in `PROJECT.md` where they conflict with this document. `PROJECT.md` remains the product vision and historical rationale.

## 1. Purpose and invariants

Geosquare V2 is a country-scoped, hierarchical grid of squares in a declared projected coordinate reference system (grid CRS). The grid is a permanent mathematical reference; geometries are derived from an identifier and profile data at read time.

The following invariants are non-negotiable:

1. A cell is an exact square in its domain's **grid CRS**, measured in metres.
2. Canonical identity is `(domain_code, level, x_idx, y_idx)`; GID strings, packed integers, and geometry are reversible representations or derivations of that identity.
3. Every domain has an explicit, immutable origin, root side, grid CRS, equal-area CRS, reference epoch or explicit static/no-dynamic-epoch policy, and versioned profile.
4. Hierarchy uses ordinary prefix truncation: one GID character represents one refinement level.
5. Neighbours and distance operate on integer indices, never by geometric buffering or GID lexical order.
6. GIDs and packed values are version-scoped. V1 identifiers are not V2 identifiers.

A V2 grid cell is **not** claimed to be a globally exact ground square. Its grid-CRS square and published maximum directional scale error are the authoritative metric contract.

## 2. Compatibility and identifier policy

V2 is intentionally a clean break from V1 and the international prototype. Their roots, level numbers, base-2 alphabets, coordinate extents, and CRS semantics differ. Existing data must be migrated by decoding the old identifier with its legacy implementation, using a representative point or source geometry, and re-encoding it under the selected V2 domain and level.

The canonical external identifier is:

```text
geosquare:v2:<domain_code>:<gid>
```

Example: `geosquare:v2:ID:2G4M3N8P`.

`ID:<gid>` is a version-scoped short form. A bare GID is permitted only when domain `ID` and V2 are fixed by the API contract. A serialized dataset, warehouse table, API response, or event **MUST NOT** use a bare GID as its only spatial identity.

The empty GID (`""`) is the level-0 root cell. A non-empty GID has exactly one character per level.

## 3. Grid hierarchy and resolution contract

### 3.1 Refinement sequence

The refinement sequence is fixed and matches the original Geosquare hierarchy:

```python
D = [5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2]
ROOT_SIDE_M = 50_000_000.0
MIN_LEVEL = 0
MAX_LEVEL = 14
```

Level `L` has `N_L = product(D[:L])` cells along each root edge and side length `S_L = ROOT_SIDE_M / N_L`.

| Level | Subdivision at level | Cell edge |
|---:|:---:|---:|
| 0 | root | 50,000 km |
| 1 | 5 × 5 | 10,000 km |
| 2 | 2 × 2 | 5,000 km |
| 3 | 5 × 5 | 1,000 km |
| 4 | 2 × 2 | 500 km |
| 5 | 5 × 5 | 100 km |
| 6 | 2 × 2 | 50 km |
| 7 | 5 × 5 | 10 km |
| 8 | 2 × 2 | 5 km |
| 9 | 5 × 5 | 1 km |
| 10 | 2 × 2 | 500 m |
| 11 | 5 × 5 | 100 m |
| 12 | 2 × 2 | 50 m |
| 13 | 5 × 5 | 10 m |
| 14 | 2 × 2 | 5 m |

This preserves the operational level meanings in `PROJECT.md`: level 6 is 50 km, level 9 is 1 km, and level 14 is 5 m. A 1 m level is deliberately out of scope for V2 because it cannot fit the full root-to-leaf path together with domain and level fields in the selected signed Int64 layout.

### 3.2 GID character matrices

Rows are indexed from south to north; columns are indexed from west to east.

```python
M_5X5_BY_ROW_FROM_SOUTH = [
    ["2", "3", "4", "5", "6"],
    ["7", "8", "9", "C", "E"],
    ["F", "G", "H", "J", "L"],
    ["M", "N", "P", "Q", "R"],
    ["T", "V", "W", "X", "Y"],
]

M_2X2_BY_ROW_FROM_SOUTH = [
    ["2", "3"],
    ["4", "5"],
]
```

At a 5×5 level, all 25 characters are valid. At a 2×2 level, only `2`, `3`, `4`, and `5` are valid. Decoders **MUST** validate against the table for the specific level; a character that is valid in the 5×5 table but invalid in a 2×2 level is invalid GID input.

### 3.3 GID is a hierarchy encoding, not a spatial-order key

The GID is a direct mixed-radix encoding of `(x_idx, y_idx)` and guarantees parent truncation, but its lexical order is not a spatial-neighbour query primitive. No API, database guide, or optimizer may assume that adjacent cells are lexically adjacent.

A future stateful Hilbert/Peano key may be introduced as an **optional, separately versioned secondary ordering key** after a complete orientation-state specification and test vectors exist. It will not replace the canonical identity, GID, or packed identifier.

## 4. Domain profiles and reproducibility

Each country domain is loaded from a versioned profile referenced by a signed registry manifest. The registry is a release artifact, not mutable application configuration.

### 4.1 Required profile fields

```json
{
  "domain_id": 1,
  "domain_code": "ID",
  "name": "Indonesia",
  "reference_epoch": 2012.0,
  "crs_authority": "GEOSQUARE:ID_GRID_V2",
  "crs_wkt2": "<complete parseable grid CRS WKT2>",
  "equal_area_crs_authority": "GEOSQUARE:ID_EQUAL_AREA_V2",
  "equal_area_crs_wkt2": "<complete parseable equal-area CRS WKT2>",
  "origin_x_m": -25000000.0,
  "origin_y_m": -25000000.0,
  "root_side_m": 50000000.0,
  "min_level": 0,
  "max_level": 14,
  "scale_error_max_pct": 0.0,
  "scale_error_method": "projection_factors_max_directional",
  "scale_error_evaluation_metadata": "scale/ID_GRID_V2.json",
  "boundary_source_crs": "OGC:CRS84",
  "boundary_file": "../boundaries/ID.boundary.geojson",
  "boundary_sha256": "<sha256>"
}
```

The numerical origin above is an illustrative layout only. A published profile must use a reviewed origin and a root square that covers all intended coordinates after transformation. The profile must contain generated checksums, complete WKT2 definitions, and measured scale metadata; placeholders are invalid release content.

The grid CRS selection must be documented per domain. It may be conformal, equidistant, or another local projected CRS, but its measured directional scale error across the operational boundary must be published. The equal-area CRS is mandatory and is used only for area/coverage calculations.

### 4.2 Registry verification

The signed manifest identifies the pinned PROJ version, `proj.db` hash, required grid-shift resources, and profile hashes. A conforming loader:

1. validates the manifest schema;
2. verifies an Ed25519 signature over RFC 8785 canonical JSON with `signature` omitted, using a trusted public key outside the manifest;
3. verifies installed PROJ and declared resource hashes;
4. verifies each profile and boundary-file hash before loading it; and
5. rejects duplicate domain IDs/codes, escaping paths, malformed CRS definitions, and invalid profile bounds.

Partial registry initialization is prohibited.

### 4.3 Epoch policy

A Geosquare domain is fixed to its profile's reference frame and epoch policy. A profile with a numeric `reference_epoch` uses that realization. A profile with `reference_epoch: null` is a static candidate with no time-dependent epoch transformation. With no coordinate epoch supplied, input coordinates follow the profile policy. When an epoch is supplied, the implementation must use a documented time-dependent transformation or reject the request with `UnsupportedEpochTransformationError`.

No API may infer an epoch from the system clock. This policy provides stable grid definitions while allowing source features to be re-indexed as their coordinate realization changes.

## 5. Canonical coordinate indexing

For grid-CRS coordinate `(x, y)`, root origin `(X0, Y0)`, side `S0`, and level `L`:

```text
N_L       = product(D[:L])
cell_size = S0 / N_L
```

Input coordinates are valid in the closed root extent `[X0, X0 + S0] × [Y0, Y0 + S0]`. The maximum external edge belongs to the final cell; every internal cell interval is half-open.

```python
def projected_xy_to_canonical(x: float, y: float, profile, level: int):
    validate_finite_non_boolean(x, y)
    validate_level(level)
    x0, y0, s0 = profile.origin_x_m, profile.origin_y_m, profile.root_side_m
    if not (x0 <= x <= x0 + s0 and y0 <= y <= y0 + s0):
        raise OutOfDomainError((x, y))
    if level == 0:
        return profile.domain_code, 0, 0, 0

    n = math.prod(D[:level])
    side = s0 / n
    x_idx = n - 1 if x == x0 + s0 else math.floor((x - x0) / side)
    y_idx = n - 1 if y == y0 + s0 else math.floor((y - y0) / side)
    return profile.domain_code, level, int(x_idx), int(y_idx)
```

`lonlat_to_canonical` transforms source longitude/latitude using `always_xy=True`, applies the profile epoch policy, and then calls this function. Optional operational-boundary enforcement uses `prepared_boundary.covers(point)` in the grid CRS. The mathematical root remains complete even outside the national boundary.

## 6. Canonical ↔ GID codec

To encode, repeatedly take the least significant coordinate digit of the relevant radix, map `(row=y % step, column=x % step)` to the level's table, then reverse the collected characters. To decode, scan GID characters from left to right:

```python
x_idx = y_idx = 0
for step, char in zip(D[:level], gid):
    row, column = level_specific_position(step, char)
    x_idx = x_idx * step + column
    y_idx = y_idx * step + row
```

The codec must round-trip exactly:

```text
canonical_to_gid(gid_to_canonical(domain, gid)) == gid
gid_to_canonical(domain, canonical_to_gid(domain, level, x, y)) == (domain, level, x, y)
```

## 7. Signed Int64 encoding

V2 uses a non-negative signed `Int64`, compatible with common database `BIGINT` implementations.

```text
Bit 63       fixed 0 (sign)
Bits 62–54   domain_id: 9 bits, values 1–511
Bits 53–50   level: 4 bits, values 0–14
Bits 49–1    hierarchical path: 49 bits, root-to-leaf and right-aligned
Bit 0        reserved, fixed 0
```

Each base-5 level stores `row * 5 + column` in 5 bits; each base-2 level stores `row * 2 + column` in 2 bits. At level 14, seven 5×5 steps and seven 2×2 steps require exactly `7 × 5 + 7 × 2 = 49` path bits.

The packed value encodes `domain_id`, level, and path. It must round-trip with the canonical identity. Decoders must reject a set sign bit, reserved bit zero set to one, domain ID zero, level greater than 14, non-zero unused path bits, and child codes outside the valid range.

Packed values are excellent equality and hierarchy-storage keys. Parent derivation must use the level-aware width of the final step and update the level field; applications must not assume that a simple unmasked right-shift alone is a valid parent identifier.

## 8. Topology, hierarchy, geometry, and distance

`parent(gid)` removes one final character. `children(gid)` appends exactly four or 25 valid characters based on `D[level]`. A level-14 cell has no children.

For `(x, y, L)`:

- `k_disk(k)` returns valid root-domain cells satisfying `max(abs(dx), abs(dy)) <= k`, including the source at `k = 0`.
- `k_ring(k)` returns valid root-domain cells satisfying `max(abs(dx), abs(dy)) == k`. `k_ring(1)` is Moore adjacency and excludes the source cell.
- root-domain bounds clip the result. Operational country-boundary filtering is an explicit post-filter and must declare its predicate (`CENTROID_COVERED`, `INTERSECTS`, or coverage threshold).
- grid distance is `sqrt((x2 - x1)^2 + (y2 - y1)^2) * cell_size` metres in the grid CRS.

A projected cell geometry is derived directly as:

```text
[x0 + x_idx * side, x0 + (x_idx + 1) * side]
×
[y0 + y_idx * side, y0 + (y_idx + 1) * side]
```

This exact projected square is authoritative. A reprojected WGS84 geometry may require edge densification for visually correct large-cell geometry; a four-corner transform alone is only an approximation for non-linear or oblique transformations.

## 9. Polyfill and coverage ratios

`polyfill_stream` accepts a polygonal input geometry, its source CRS, a V2 domain and level, coverage mode, threshold, and candidate limit. It must:

1. normalize or reject invalid/non-polygonal geometry;
2. transform input geometry to the grid CRS with `always_xy=True`;
3. clip it to the root square;
4. compute bounded integer candidate indices from the clipped projected bounds;
5. reject requests exceeding `max_candidate_limit` before enumerating cells;
6. derive each candidate square procedurally; and
7. yield `(gid, coverage_ratio)`.

Coverage modes are:

- `GRID_PLANAR`: intersection area in the grid CRS divided by cell square area;
- `EQUAL_AREA`: transform both input and candidate cell to the verified profile equal-area CRS before calculating the ratio.

`EQUAL_AREA` is required for coastal, cross-projection, or published statistical coverage. A threshold of `0.0` includes every positively intersecting cell. Ratios must be clamped only for floating-point noise and remain within `[0, 1]`.

## 10. Batch and warehouse interfaces

The scalar reference codec is authoritative. Batch interfaces must produce byte-for-byte equivalent canonical identities and packed values for the same valid inputs.

Required phases:

1. NumPy arrays: lon/lat or projected x/y to canonical indices and packed values.
2. Pandas and Apache Arrow adapters without per-row Python object loops for numeric transformation/indexing stages.
3. SQL/UDF packages for BigQuery, Snowflake, and PostGIS generated from shared, tested codec fixtures.

Warehouse guidance must distinguish hierarchy operations from spatial locality:

- use packed identifiers or canonical fields for equality and parent aggregation;
- use domain, level, `x_idx`, and `y_idx` predicates for rectangular windows and topology;
- do not use lexicographic GID ranges as a geographic-neighbour query.

## 11. Required conformance fixtures

Before a domain is released, it must ship reproducible fixtures covering:

- registry signature, profile hashes, and PROJ resource validation;
- grid CRS/equal-area CRS parsing and published distortion metadata;
- all GID characters at every 5×5 and 2×2 level;
- invalid 2×2 characters, malformed GIDs, empty GID, and level limits;
- every root edge and internal cell-boundary rule;
- canonical/GID/Int64 round-trips;
- parent/child consistency and 5×5/2×2 child counts;
- neighbour carries across every parent boundary, exact `k_ring` semantics, and `k_disk` semantics;
- projected square geometry, densified WGS84 geometry, and equal-area fractional polyfill; and
- scalar, NumPy, Arrow, and SQL/UDF equivalence.

## 12. Implementation sequence

1. Create signed registry tooling and reviewed ASEAN domain profiles with real CRS WKT2, boundaries, hashes, scale analysis, and fixtures.
2. Implement domain loading, canonical indexing, strict GID codec, projected geometry, hierarchy, and integer topology.
3. Implement Int64 packing and fixture-driven round-trip validation.
4. Implement equal-area fractional polyfill and explicit operational-boundary predicates.
5. Add vectorized interfaces and warehouse implementations from shared reference vectors.
6. Add a V1 migration adapter as a separate package/module; it must not silently treat V1 values as V2 GIDs.
