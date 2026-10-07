# Geosquare V2 Architecture Decisions

**Status:** accepted decisions for V2 implementation
**Date:** 2026-08-18
**Related specification:** [`V2SPECS.md`](V2SPECS.md)

This record captures the decisions made after comparing the legacy `geosquare-grid` package, the `gs-grid-international` prototype, and the original V2 proposal. It deliberately separates durable decisions from exploratory code and historical documentation.

## ADR-001 — V2 is a new identifier system

**Decision:** V2 is not wire-compatible with V1 or the international prototype. All durable V2 identifiers include a version and domain, for example `geosquare:v2:ID:<gid>`.

**Why:** Existing implementations disagree on root extent, levels, CRS treatment, base-2 character placement, and ID scope. Reusing bare GIDs would make the same string ambiguous or silently wrong.

**Consequences:**

- Existing records require an explicit migration process.
- V1 decoding remains available only in an isolated migration adapter.
- APIs, tables, events, and exports store a versioned domain-qualified ID, not a bare GID alone.

## ADR-002 — Preserve the original 5/2 level meanings

**Decision:** V2 uses `D = [5, 2, 5, 2, ...]`, a 50,000 km root, and levels 0–14. Level 6 is 50 km, level 9 is 1 km, and level 14 is 5 m.

**Why:** This preserves the operational hierarchy already defined in `PROJECT.md` while fitting the full 14-level path in 49 bits: seven base-5 digits require 35 bits and seven base-2 digits require 14 bits.

**Consequences:**

- The original V2 proposal's `[2, 5, ...]` sequence and 10,000 km root are retired.
- V2 has no 1 m level in the signed `Int64` scheme. Adding 1 m requires a new encoding/version or a different identifier representation.
- Domains remain isolated despite a generously sized mathematical root; the operational country boundary is a separate explicit filter.

## ADR-003 — Canonical identity is Cartesian, not curve-based

**Decision:** `(domain, level, x_idx, y_idx)` is the sole canonical identity. GID and Int64 are lossless encodings. GID lexical order is not a spatial-order guarantee.

**Why:** Integer Cartesian coordinates give exact topology, deterministic geometry, database-friendly window predicates, and no ambiguity at parent boundaries. A space-filling curve does not replace those guarantees.

**Consequences:**

- Moore neighbours, k-rings, and distance use integer deltas.
- Warehouse range scans for physical windows use `domain`, `level`, `x_idx`, and `y_idx`, not lexicographic GID ranges.
- A Hilbert/Peano-like locality key may later be added only as an optional secondary index. It needs a stateful recursive orientation contract and exhaustive test vectors before adoption.

## ADR-004 — A profile defines a country domain, not an EPSG extent

**Decision:** A V2 domain is defined by a signed Geosquare country profile containing a reviewed origin, root side, grid CRS WKT2, equal-area CRS WKT2, and operational boundary. It is not dynamically derived from an EPSG area's bounding box.

**Why:** EPSG areas of use can include multiple countries, omit territories, change over time, or be much larger than the intended operating area. Dynamically using their extents makes identifiers unstable and weakens national isolation.

**Consequences:**

- `EPSG:<code>` alone is not a V2 domain identifier.
- The `gs-grid-international` prototype remains valuable as reference code for projection, mixed-radix codec, and integer topology, but it is not the V2 domain model.
- Operational-boundary enforcement is opt-in and uses a stated predicate; it never changes mathematical root-cell validity.

## ADR-005 — Metric and area claims are made honestly

**Decision:** Every profile publishes a grid CRS and a separate equal-area CRS, plus measured directional scale-error metadata. Grid cells are exact squares in the grid CRS; fractional coverage is calculated in the equal-area CRS when requested.

**Why:** No one projection is simultaneously perfect for shape, distance, and area across a large country such as Indonesia. A transparent profile-level distortion contract is more accurate than claiming universal physical squares.

**Consequences:**

- The grid CRS is selected per country after distortion analysis rather than by a global EPSG default.
- Reprojected longitude/latitude cell geometry may be densified; four transformed corners are insufficient for exact visual geometry in some projections.
- Published coastal or statistical coverage uses `EQUAL_AREA` mode unless the use case explicitly calls for grid-planar coverage.

## ADR-006 — Reference epoch is explicit

**Decision:** Every domain declares a reference epoch. A missing input epoch means coordinates are interpreted at that reference epoch; supplied epochs require a supported time-dependent transformation.

**Why:** This makes deformation handling reproducible and avoids silently assigning cells according to a moving wall clock or unknown datum realization.

**Consequences:**

- Unsupported epoch transformation fails explicitly.
- Features may be re-indexed as their source coordinates are updated without changing the domain's grid definition.
- V2 does not claim to be an ECEF grid unless a future version is actually defined in ECEF coordinates.

## ADR-007 — Signed registry and fixtures precede scale-out

**Decision:** Production domains are released through a signed registry with pinned CRS resources, profile and boundary hashes, and conformance fixtures. The current candidate release covers all 11 ASEAN domains.

**Why:** Grid identifiers become durable data keys. CRS database drift, changed boundary files, or unreviewed projection changes must not silently redefine them.

**Consequences:**

- A profile with placeholders, unmeasured distortion, missing signatures, or missing fixtures is not a release artifact.
- Vectorized and SQL implementations are derived from shared scalar reference fixtures.
- Additional countries are added as reviewed profile releases, not as runtime code edits.

## ADR-008 — Migration is explicit and geometry-aware

**Decision:** Migration from V1 or prototype IDs is an explicit process that decodes the legacy value in its original context and re-encodes a defined representative location or geometry under V2.

**Why:** There is no one-to-one string transformation between systems with different projections, roots, alphabets, and level semantics.

**Consequences:**

- Point records normally migrate through their original coordinate or the legacy cell centroid/lower-left point, with the chosen policy recorded.
- Area records are reprocessed through V2 polyfill at the desired target level and coverage rule.
- Migration output records source system/version, method, target V2 domain, target level, and any coverage threshold used.
