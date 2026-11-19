# Phase 4 Design Draft: Compact Cell Sets and Time Cubes

**Status:** design draft for review
**Scope:** E13 compact cell set and L7 time cube
**Related documents:** `V2SPECS.md`, `docs/cell-dataset-contract.md`

This draft proposes additive dataset types. It does not change the frozen V2 specification, the registry, conformance vectors, or existing dataset files.

## A. E13 compact cell set

### Problem

A polygon covering a large, mostly continuous area wastes storage when it is represented only at a fine level. Storing every small edge cell preserves detail but repeats the same interior coverage many times. A compact cell set should store large cells in the interior and progressively smaller cells only where the boundary needs them, while remaining joinable to ordinary single-level cell data.

A compact set is a set of cells, not a value table. Its rows describe spatial membership and do not have the one-row-per-cell-value meaning of `cell_values`.

### Proposed definition

Introduce a separate dataset type, tentatively `cell_compact_set`. Its manifest declares one V2 domain and one registry/profile version. Its required columns are:

```text
gid      UTF-8, non-null, valid for the declared domain
level    int8/int16, non-null, equal to the decoded GID level
```

The set has no dataset-level `level` field because rows may have different levels. The explicit `level` column is redundant by design: it makes the mixed-level schema visible, allows cheap consistency checks, and avoids inferring the intended type from GID length. Rows are distinct. The represented geometry is the union of the grid-CRS squares for all rows.

The canonical compact form is an antichain: no row is an ancestor of another row. A cell covers all of its descendants. A canonicalizer first removes descendants covered by an already-present ancestor. It then repeatedly applies this promotion rule bottom-up:

- for a cell at level `L`, inspect its direct children at level `L + 1`;
- if every direct child is present, remove those children and insert the parent;
- the child count is `D[L]²`, where `D = [5, 2, 5, 2, ...]`;
- therefore a level whose next step is 5 uses all 25 children, and a level whose next step is 2 uses all 4 children;
- stop at a fixed point, at level 0 if the complete root is present, or at level 14 for leaves.

The 5×5 child set uses the exact section 3 matrix and the 2×2 child set uses the exact section 3 matrix. A character valid at another level is not a valid substitute. Promotion operates on decoded parent/child identity, not on lexical GID ranges. If a source contains deeper descendants rather than direct child rows, the compactifier must first expand them to the level being considered or reject the input as non-normalized; it must not infer completeness from a partial descendant sample.

### Required rules

1. One compact set has one `domain_code`, `grid_version`, `registry_version`, and profile version. A domain mismatch is an error.
2. Every row must decode successfully, and its `level` must equal the decoded GID length and remain within levels 0–14.
3. The set must be an antichain after canonicalization. A reader may canonicalize only when that behavior is explicitly requested; a validating reader should reject non-canonical input rather than silently changing it.
4. A compact set may mix levels. This is the deliberate exception to the cell dataset contract rule that ordinary datasets must not mix levels. A `cell_values` or `cell_contributions` dataset still must not mix levels.
5. The set is a spatial selection, not a polygon validity claim. Coverage thresholds and boundary predicates used to create it belong in manifest metadata and must not be inferred by a reader.
6. The half-open coordinate rule, root-edge rule, and domain-boundary policy remain those in V2SPECS sections 5 and 9.

### Expansion, membership, and joins

To expand a row to target level `T`, require `T >= level` and recursively append every valid child through level `T`. The result is the exact set of level-`T` descendants. Expanding a canonical mixed-level set unions and de-duplicates those descendants; canonical rows are disjoint, so the result is deterministic. A request below any row's level is invalid rather than an implicit roll-up.

For a candidate GID `g`, membership is true when `g` is valid for the set's domain and either equals a stored row or has a stored row as an ancestor. The implementation may test the candidate's parent chain against a hash set or a trie. It must not use string-prefix matching without first validating the level-specific GID, domain, and hierarchy position.

Point lookup first converts the point to a valid GID at a requested query level using the profile, source CRS, `always_xy`, epoch policy, and section 5 edge rules. It then applies the membership test. A point outside the mathematical root is rejected; operational-boundary filtering remains an explicit policy.

A join from a compact set to a single-level dataset has two exact strategies:

- **Expansion:** expand the compact set to the dataset level, then join on equal GID. Cost is proportional to the number of covered target cells and can be large for a broad area or a deep target level. It is useful when the expanded set will be reused for many joins.
- **Ancestor lookup:** for each single-level dataset GID, test that GID and its ancestors against the compact set. Cost is `O(R × depth)` for `R` dataset rows with a bounded maximum depth of 14, or less with a trie/index. It avoids materializing edge descendants and is the default for one-off or sparse joins.

Both strategies must produce the same matched target GIDs. The compact set must remain its own dataset type and must not be encoded as a `cell_values` table with a fake value column.

### Validation and test vectors

The reader should reject null GIDs, invalid level-specific characters, mismatched explicit levels, domain mismatches, duplicate rows, ancestor/descendant pairs in canonical input, and malformed manifest scope. It should also reject a compact set that claims a single dataset level or uses `unique_gid` semantics without declaring the compact type.

Required vectors include: all 25 children at a 5×5 step promote to one parent; all 4 children at a 2×2 step promote to one parent; one missing child prevents promotion; promotion cascades across alternating 5×5 and 2×2 steps; an existing ancestor suppresses descendants; expansion counts match the product of child counts; membership agrees for exact cells and descendants; points on internal and root edges follow the half-open rule; domain and level mismatches fail; and expansion joins equal ancestor-lookup joins.

### Open decisions

- **A1, physical schema:** `gid + level` only, or add `packed_id`/indices? Recommendation: require `gid + level` and allow `packed_id`, `x_idx`, and `y_idx` only as validated optional acceleration columns.
- **A2, invalid non-canonical input:** reject, or canonicalize while reading? Recommendation: reject by default and provide an explicit canonicalization writer step.
- **A3, join default:** materialize to the target level, or ancestor lookup? Recommendation: ancestor lookup by default; expose expansion for repeated joins and export.

## B. L7 time cube

### Problem

The current `cell_values` contract identifies one value row by `gid`. It cannot represent a time series without either overwriting rows or inventing an unstandardized date column. L7 needs a stable temporal key, deterministic ordering, and manifest metadata that makes a time range unambiguous to readers.

### Proposed definition

Introduce dataset type `cell_time_values`, with rows shaped as:

```text
gid, period, <one or more value fields>
```

`period` is a reserved GeoSquare column name. It is UTF-8 text containing one canonical ISO 8601 calendar label selected by the manifest's `period_type`:

| `period_type` | Required `period` format | Example |
|---|---|---|
| `year` | `YYYY` | `2026` |
| `month` | `YYYY-MM` | `2026-11` |
| `day` | `YYYY-MM-DD` | `2026-11-19` |

Use four-digit years from `0001` through `9999`, two-digit months, and two-digit days. The parser must validate real calendar dates, including leap years. No time zone, time-of-day, offset, alternate spelling, or partial label is permitted. Fixed-width labels sort chronologically as text.

The manifest must add:

```json
"period_type": "month",
"period_start": "2020-01",
"period_end": "2027-01"
```

`period_start` is inclusive and `period_end` is exclusive. Both use the format for `period_type`; the end is the first period outside the dataset. For a `day` cube, for example, `period_end: "2027-01-01"` includes 2026-12-31 but excludes 2027-01-01. The manifest must reject an empty or reversed interval. A manifest may describe a range containing gaps, but it must not claim that every period exists unless a separate completeness field is later designed.

Rows are sorted by `gid`, then `period`, and the uniqueness constraint is `unique (gid, period)`. The existing `cell_values` uniqueness rule, `unique gid`, remains unchanged. Multiple periods for one GID are expected; duplicate observations for the same pair are not.

### Required rules

1. `cell_time_values` retains the ordinary dataset scope: one domain, one grid/profile version, and one cell level. It does not mix spatial levels.
2. `gid` remains the spatial identity and must validate against the manifest domain and level.
3. `period` is reserved and cannot appear as a user value field or be renamed through aliases in the physical table.
4. `period`, `period_start`, and `period_end` must all use the same declared granularity. A period outside the half-open manifest range is invalid.
5. Sorting is the canonical physical order `gid, period`; a manifest must record this in `storage.sorted_by` or an equivalent versioned field.
6. A non-temporal `cell_values` or `cell_contributions` reader must reject a `period` column rather than silently treating repeated GIDs as valid.

### Validation and test vectors

A reader must reject an unknown dataset type, missing or invalid `period_type`, missing period bounds, non-canonical period strings, impossible dates, null periods, period bounds in a different format, `period_start >= period_end`, periods outside the declared range, duplicate `(gid, period)` pairs, GIDs at the wrong domain or level, and a `period` name used in `value_fields`. It must reject a `cell_time_values` manifest that still declares `unique_gid: true` as its uniqueness rule.

Vectors should cover all three period types, month and day boundaries, leap day 2024, invalid 2023-02-29, sort order across years and months, duplicate spatial rows at different periods, duplicate `(gid, period)`, range endpoints, empty intervals, nulls, and accidental `period` columns in ordinary dataset types. A round-trip fixture should verify that a writer's manifest and Parquet metadata preserve the same period contract.

### Open decisions

- **B1, period representation:** canonical strings, typed dates/timestamps, or integer period keys? Recommendation: canonical ISO 8601 strings for the first format because they are portable across Parquet engines and human-readable; parse them strictly at the boundary.
- **B2, range end:** inclusive or exclusive? Recommendation: exclusive `period_end`, which supports adjacent partitions without overlap.
- **B3, missing periods:** allow gaps or require a dense cube? Recommendation: allow gaps and treat completeness as a future explicit manifest field.
- **B4, physical sort:** `gid, period` or `period, gid`? Recommendation: `gid, period`, because cell joins and per-cell time scans are the primary access pattern.

## Changes required in a future spec and contract revision

No existing file is changed by this draft. A future additive revision should update the cell dataset contract to register `cell_compact_set` and `cell_time_values`, reserve `period`, define their schemas and manifest fields, and add the new rejection rules. It should retain the ordinary “do not mix levels in one dataset” rule and state the compact-set exception explicitly. It should add the temporal uniqueness and sort rules without weakening `cell_values`.

The future revision should update V2SPECS section 15 only for the physical layout and sort metadata needed by these dataset types. The hierarchy, GID, topology, polyfill, registry, and existing conformance vectors remain unchanged. Under section 16, these are additive dataset capabilities and should be released as a compatible minor specification/contract revision, subject to the repository’s versioning policy, not as a registry change. New fixtures must be added before implementation is accepted.

## Decisions

| ID | Question | Options | Recommendation |
|---|---|---|---|
| A1 | Compact-set physical identity | `gid + level` / add packed identity columns | Require `gid + level`; permit validated optional acceleration columns |
| A2 | Non-canonical compact input | Reject / canonicalize on read | Reject by default; canonicalize explicitly when writing |
| A3 | Compact-set join strategy | Expansion / ancestor lookup | Ancestor lookup by default; expand for reuse/export |
| B1 | Period representation | ISO strings / typed timestamps / integer keys | Strict canonical ISO 8601 strings |
| B2 | Temporal range end | Inclusive / exclusive | Exclusive `period_end` |
| B3 | Missing periods | Dense cube / gaps allowed | Gaps allowed; add completeness metadata later |
| B4 | Time-cube sort key | `gid, period` / `period, gid` | `gid, period` |
