# Geosquare V2: Crucial Logic, CRS Roles, and Operational Rules

**Status:** implementation guide for the V2 candidate package  
**Normative companion:** [V2SPECS.md](V2SPECS.md)  
**Audience:** implementers, GIS reviewers, data-platform engineers, and release approvers

This guide explains *why* the V2 rules exist and how its most important parts fit together. It is deliberately more explanatory than the specification. Where it differs from code, the code and [V2SPECS.md](V2SPECS.md) control.

## 1. The one-sentence model

A V2 cell is a permanent integer address inside one signed country profile; that address derives an **exact square in the profile's canonical grid CRS**. Other geometries, GIDs, packed integers, WGS84 display shapes, and area measurements are representations or calculations around that address—they are not alternative definitions of the cell.

That separation prevents a common failure: allowing a changed web map projection, a changed boundary file, or a different warehouse CRS to silently change an identifier that has already been stored in a database.

## 2. The layers of truth

| Layer | Canonical? | Purpose | Must not be used for |
|---|---|---|---|
| `(domain_code, level, x_idx, y_idx)` | Yes | Durable cell identity and integer topology | Display geometry or a global spatial-order key |
| Profile grid CRS | Yes, for geometry/indexing | Exact square bounds, point indexing, neighbours, metric grid distance | Published area claims without considering distortion |
| GID | Reversible encoding | Human-readable hierarchy encoding | Lexicographic spatial ranges |
| Packed `Int64` | Reversible encoding | Equality keys, compact storage, hierarchy-aware data models | Unmasked parent derivation or physical-window search |
| WGS84 geometry | No | Interchange, web display, geographic APIs | Authoritative square construction or area ratios |
| Equal-area CRS | No, for identity; yes, for coverage measurement | Fractional area coverage | Point indexing, hierarchy, topology, or replacing the grid CRS |
| Operational country boundary | No | Explicit policy filtering for an application | Defining whether a coordinate belongs to the mathematical root |

The rule is simple: **identity and topology happen in integer/grid space; area happens in equal-area space; display happens in WGS84 when needed.**

## 3. Canonical identity comes before every encoding

The canonical cell identity is:

```text
(domain_code, level, x_idx, y_idx)
```

- `domain_code` selects a signed, immutable country profile such as `ID` or `VN`.
- `level` is an integer from 0 through 14.
- `x_idx` increases west to east.
- `y_idx` increases south to north.

This is intentionally Cartesian rather than curve-based. Cartesian indices make the following direct and unambiguous:

- exact square derivation;
- parent/child relationships;
- Moore neighbours and `k_ring`/`k_disk` operations;
- rectangular database filters; and
- grid-CRS distance calculations.

A GID is not the primary identity; it is a reversible string encoding of the indices. The packed `Int64` is also not primary; it is a reversible storage encoding. A future Hilbert- or Peano-like key may be a useful *secondary* locality index, but it cannot replace the Cartesian identity without a separately specified orientation-state contract.

### 3.1 Domain qualification is mandatory in durable records

A bare GID only has meaning if the V2 version and domain are already fixed by the surrounding API contract. Durable records should use:

```text
geosquare:v2:<domain_code>:<gid>
```

For example, `geosquare:v2:ID:H2X3P325Q` carries enough context to avoid collisions with V1, future versions, or another country profile. The level-0 root is represented by the empty GID (`""`), so it especially needs domain/version context.

## 4. Hierarchy: why the subdivision sequence is fixed

V2 uses the alternating sequence:

```text
[5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2]
```

with a 50,000,000 m root side. At level `L`:

```text
N(L)    = product(subdivision[0:L])
side(L) = 50,000,000 / N(L) metres
```

This preserves operational resolution semantics while allowing the full level-14 path to fit into 49 bits:

| Level | Grid edge length |
|---:|---:|
| 0 | 50,000 km |
| 3 | 1,000 km |
| 6 | 50 km |
| 9 | 1 km |
| 12 | 50 m |
| 14 | 5 m |

At each 5×5 step, a character represents one of 25 `(row, column)` positions; at each 2×2 step it represents one of four positions. The character sequence is prefix-hierarchical: removing the final GID character produces the parent GID. This property is for hierarchy, **not** for geographic sorting.

## 5. Canonical grid CRS: the identity geometry

Every signed profile supplies an exact grid CRS WKT2, root origin, and root side. These define the only coordinate plane in which a V2 cell is constructed.

For a canonical cell at level `L`, with root origin `(X0, Y0)` and side `S0`:

```text
side = S0 / N(L)
min_x = X0 + x_idx × side
min_y = Y0 + y_idx × side
max_x = min_x + side
max_y = min_y + side
```

The result is an axis-aligned, exact square in the profile grid CRS. `GeosquareGrid.projected_bounds()` is the authoritative implementation of this derivation. It does not use a boundary polygon, an EPSG area of use, a web-map tile, or a cached geometry table.

### 5.1 Why each country needs a profile CRS

A single geographic/longitude-latitude grid would not provide a stable metre-square contract across Indonesia or Vietnam. A country profile instead publishes a reviewed projection and its measured directional scale-error metadata.

The current candidate profiles use:

| Domain | Canonical grid CRS | Why |
|---|---|---|
| `ID` | SRGI2013-based Equidistant Cylindrical centred at 118°E | A single national hierarchy for an east-west archipelago, rather than disconnected UTM/TM roots |
| `VN` | VN-2000-based Lambert Conformal Conic centred at 107.5°E | A single national hierarchy for Vietnam, rather than one canonical root per zonal variant |

Local UTM/TM zones remain useful input/reference metadata. They are not alternative canonical V2 domains: creating zone-specific roots would break cross-zone parent rollups, neighbour operations, and one-country identity.

### 5.2 Point indexing flow

For a longitude/latitude input:

```text
source longitude/latitude
  → transform to profile grid CRS (always_xy=True)
  → validate the closed mathematical root extent
  → calculate x_idx/y_idx at the requested level
  → construct canonical identity
  → optionally encode GID and packed Int64
```

The coordinate convention must be `always_xy=True`: source `x` is longitude/easting and source `y` is latitude/northing. Without it, CRS axis conventions can silently swap values.

The current scalar API accepts a caller-supplied transformer; the convenience batch lon/lat APIs construct a profile-derived `always_xy=True` transformer. In both cases, coordinate transformation must use the complete signed CRS WKT2, not merely an abbreviated authority string.

### 5.3 Root-edge rule

The root extent is closed:

```text
[X0, X0 + S0] × [Y0, Y0 + S0]
```

The outer maximum edge belongs to the last cell. All interior cell boundaries follow the normal lower-inclusive/upper-exclusive rule. This explicit exception prevents a valid coordinate exactly on the external root edge from producing an out-of-range index.

### 5.4 What the grid CRS does *not* claim

A grid-CRS square is exactly square in that CRS. It is not automatically a perfectly square or equal-area patch on the Earth. That is why profiles publish scale-error metadata and why V2 does not reuse the grid CRS for every area statistic.

## 6. Equal-area CRS: the measurement geometry

Every signed profile also contains a verified equal-area CRS WKT2. It has one purpose: providing the area basis for fractional coverage calculations.

It does **not** define:

- a different root;
- different `x_idx`/`y_idx` values;
- a different GID or packed ID;
- parent/child relationships;
- neighbours or distance; or
- a replacement grid geometry.

The profile's equal-area CRS is therefore a measurement lens over the same canonical cell, not a second grid system.

### 6.1 Why grid and equal-area CRS are separate

Projection choices require trade-offs. A CRS selected for stable, practical metric squares across a country is not necessarily the best CRS for comparing polygon areas. Conversely, an equal-area CRS should not be used to define a national metric grid if it does not meet the profile's metric/distortion contract.

V2 makes this trade-off explicit instead of hiding it behind an ambiguous word such as “square.”

### 6.2 Coverage modes

| Mode | Numerator / denominator | Use when |
|---|---|---|
| `GRID_PLANAR` | Grid-CRS intersection area / grid-CRS cell-square area | The question is intentionally about the grid plane itself |
| `EQUAL_AREA` | Equal-area intersection area / equal-area cell area | Coastal reporting, cross-projection comparison, published statistics, or any Earth-area interpretation |

For typical published coverage, use `EQUAL_AREA`.

## 7. Polyfill: exact identity, bounded work, explicit area basis

`polyfill_stream()` returns `(bare_gid, coverage_ratio)` pairs. Its order is deterministic row-major order: increasing `y_idx`, then increasing `x_idx`.

The full logic is:

```text
1. Require a verified ReleaseProfile.
2. Normalize a valid Polygon/MultiPolygon input, or reject it.
3. Transform input geometry from its declared source CRS to the canonical grid CRS
   with always_xy=True.
4. Clip it to the mathematical root square.
5. Turn the clipped grid-CRS bounding box into conservative integer candidate ranges.
6. Reject the request if candidate count exceeds max_candidate_limit.
7. Derive each candidate's exact grid square procedurally from its indices.
8. Intersect in the grid CRS; discard empty or zero-area contact.
9. Calculate the ratio in GRID_PLANAR or EQUAL_AREA mode.
10. Return positive ratios that meet min_coverage.
```

### 7.1 Why clipping and the candidate limit come first

A polygon can be much larger than the country, malformed, or supplied at a very fine target level. Transforming and clipping before candidate calculation avoids work outside the root. Checking the candidate count before cell enumeration makes resource use predictable and prevents accidental multi-million-cell requests.

The candidate range is conservative: a polygon that touches an internal grid boundary can cause the adjacent cell to be considered. The later positive-area intersection test removes zero-area edge/point contact.

### 7.2 The equal-area seam rule

In `EQUAL_AREA` mode, V2 first calculates the exact positive intersection in the canonical grid CRS. It then transforms:

1. the exact grid cell geometry, and
2. that exact grid-space intersection geometry

into the verified equal-area CRS, and divides their areas.

This is intentional. Independently transforming a whole input polygon and a neighbouring cell can produce tiny numerical gaps or overlaps at what should be a shared boundary. Such artifacts previously appeared as false micro-coverage in adjacent cells. Deriving the shared piece first retains the authoritative topology and avoids those transformation-seam artifacts.

Ratios only clamp negligible floating-point overshoot near `0` or `1`; a materially invalid ratio causes an error rather than a silent correction.

### 7.3 Boundary policy remains explicit

Polyfill clips to the **mathematical root**, not the national boundary. The grid is allowed to have valid cells in portions of the root outside the operational country shape. If an application wants only country-intersecting cells, it must apply a named post-filter such as:

- centroid covered by boundary;
- cell intersects boundary; or
- boundary coverage exceeds a declared threshold.

This separates permanent identity rules from policy rules that may differ between users, departments, or releases.

## 8. Geometry for display is derived, not stored as truth

`projected_cell_geometry()` creates the authoritative square directly from `projected_bounds()`.

`wgs84_cell_geometry()` first densifies projected edges and then transforms the vertices to WGS84. Densification matters because a straight edge in the grid CRS can be curved after a non-linear coordinate transformation. Transforming only four corners is a visual approximation for large or oblique cells.

A WGS84 polygon is therefore suitable for map display and geographic interchange. The grid CRS square remains the source of truth for the cell itself.

## 9. GID and packed Int64: two encodings, not two spatial models

### 9.1 GID

A GID maps each refinement digit’s `(row, column)` position to a level-specific character. It is reversible and prefix-hierarchical. Its lexical order has no promise about spatial proximity.

Do not write queries such as:

```sql
WHERE gid BETWEEN '...' AND '...'
```

when the goal is a geographic rectangle or neighbour search. Use `domain_code`, `level`, `x_idx`, and `y_idx` predicates instead.

### 9.2 Packed Int64

The packed format is non-negative signed `Int64`:

```text
bit 63       fixed 0 (sign)
bits 62–54   domain ID (9 bits)
bits 53–50   level (4 bits)
bits 49–1    mixed-radix hierarchy path (49 bits)
bit 0        fixed 0 (reserved)
```

It is compact and useful for equality or hierarchy-aware storage. A decoder validates sign, reserved bit, domain ID, level, unused path bits, and child codes. Parent derivation must understand the level-specific final digit width; a generic right shift without updating the level field is not a valid parent operation.

## 10. Topology and distance use indices, not geometry operations

Neighbour, ring, disk, and grid-distance calculations operate on integer indices:

- `neighbor(cell, dx, dy)` adds integer offsets and clips to root bounds.
- `k_ring(cell, k)` uses `max(abs(dx), abs(dy)) == k`.
- `k_disk(cell, k)` uses `max(abs(dx), abs(dy)) <= k`.
- Grid distance at equal levels is `hypot(Δx_idx, Δy_idx) × cell_side` in grid-CRS metres.

This is faster and more exact than buffering/intersecting polygons, and it remains valid even where the country's operational boundary is complex.

## 11. Vector and warehouse implementations must preserve scalar rules

The scalar codec/grid implementation is normative. NumPy, Pandas, Arrow, SQL, and JavaScript implementations must reproduce its valid-input output exactly, including:

- root maximum-edge assignment;
- level-specific 5×5 and 2×2 character validation;
- canonical index order;
- GID character mapping; and
- signed packed-ID layout.

The batch layer applies NumPy vector kernels for numeric transformation/indexing stages. Pandas and Arrow adapters call those same kernels rather than implementing a competing row-by-row codec.

Generated BigQuery, Snowflake, and PostGIS functions deliberately accept **already projected** X/Y values. Cloud UDFs do not silently implement the profile's complete PROJ transformation. This keeps warehouse behavior reproducible and makes the required CRS transformation explicit at ingestion or query preparation time.

BigQuery and Snowflake JavaScript emit packed IDs as strings because JavaScript `Number` cannot safely represent all V2 signed `Int64` values. The PostGIS function uses native `BIGINT`.

## 12. Reference epoch and coordinate realization

A profile declares a reference epoch, or explicitly uses `reference_epoch: null` for a static candidate with no dynamic epoch transformation. This choice is part of its reproducibility contract. Coordinates supplied without an epoch are interpreted according to that profile policy.

The current public encoder APIs do not accept a coordinate epoch or construct time-dependent transformations. A caller that has time-dependent source coordinates must resolve them to the profile realization first, or reject the request when a documented transformation is unavailable. The system must never infer an epoch from the current clock.

## 13. Signed registry: why profile data is release data

Grid identifiers become durable keys. Therefore profile data cannot be loose runtime configuration.

Before `DbRegistryLoader` returns any profile, it verifies:

1. the SHA-256 digest of the registry database file against a detached Ed25519 signature (`registry.db.sig`) using a trusted external public key;
2. exact required PROJ version, `proj.db`, and declared resources;
3. each domain's scale-metadata row hash and identity;
4. grid/equal-area CRS WKT2 parsing and projected status;
5. boundary file hashes; and
6. safe artifact paths and unique domain IDs/codes (enforced by the database schema).

The trust anchor is supplied outside the signed database. A registry database must not be allowed to nominate the key that trusts itself.

### 13.1 Release discipline

The included registry is a **candidate**, not a production declaration. To change a profile, boundary, CRS resource, or scale metadata:

```text
change reviewed source inputs
  → regenerate candidate artifacts
  → inspect hashes, WKT2, boundary provenance, and scale analysis
  → sign the unsigned registry database with the approved private key
  → distribute the signed registry database and public trust anchor
```

Never manually edit a signed registry database. Never place a private signing key in source control, a release package, chat, or documentation attachment.

## 14. Practical decision guide

| Need | Use | Do not use |
|---|---|---|
| Persist a durable grid reference | Versioned URI plus canonical fields or packed ID | Bare GID alone |
| Index a point | Profile grid CRS, then canonical indices | Equal-area CRS or a web-map CRS |
| Draw cell on a web map | Densified WGS84 geometry derived from the grid square | Four-corner-only geometry for large/curved edges |
| Find neighbouring cells | Integer `x_idx`/`y_idx` operations | GID sort order or geometry buffering |
| Query a rectangle in a warehouse | Domain/level/index ranges | Lexical GID range |
| Publish polygon coverage | `EQUAL_AREA` polyfill | Grid-planar area without saying it is grid-planar |
| Apply a national boundary rule | Explicit declared post-filter | Treating root validity as country membership |
| Add or update a country | Generated, reviewed, signed profile release | Runtime code/config edit |

## 15. Implementation checklist

Before integrating V2 into a product, confirm all of the following:

- [ ] The application stores version and domain with every durable cell reference.
- [ ] Coordinate transformation uses the verified profile WKT2 and `always_xy=True`.
- [ ] Input coordinate epoch policy is documented and enforced outside the current static encoder APIs where needed.
- [ ] Point indexing, topology, bounds, and metric grid distance use the canonical grid CRS.
- [ ] Published/coastal area coverage uses `EQUAL_AREA` mode and a chosen threshold.
- [ ] Polyfill requests have an appropriate `max_candidate_limit` for the service budget.
- [ ] Operational boundary filtering is explicit and records the selected predicate.
- [ ] Warehouse inputs are transformed to projected grid X/Y before UDF invocation.
- [ ] Warehouse spatial windows use Cartesian index predicates, not GID ranges.
- [ ] Registry updates are generated, reviewed, verified, and signed; private keys remain private.

## Related documents

- [README.md](../../README.md) — installation and practical API examples
- [V2SPECS.md](V2SPECS.md) — normative contract
- [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) — design choices and trade-offs
- [RELEASE_CANDIDATE.md](../handover/RELEASE_CANDIDATE.md) — candidate release procedure
