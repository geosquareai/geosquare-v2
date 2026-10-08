# Data-to-grid contract

**Status:** V2 design contract
**Date:** 2026-09-18

This document locks the public names and the main rules for turning data into GeoSquare cells.

## 1. Public feature names

Use one naming pattern: **input_to_output**.

| Feature | Public name | Meaning |
|---|---|---|
| Point to one cell | `point_to_cell` | Find the cell containing a point. |
| Polygon to many cells | `polygon_to_cells` | Cover a polygon with cells and return area coverage. |
| Polygon to one cell | `polygon_to_cell` | Choose one cell for a polygon. |
| Line to many cells | `line_to_cells` | Find cells touched by a line and return length coverage. |
| Cell ID to geometry | `cell_to_geometry` | Build geometry from one cell ID. |
| Many cell IDs to geometry | `cells_to_geometry` | Build geometry for a table or list of cell IDs. |
| Table points to cells | `table_to_cells` | Add cell fields to point rows. |
| Values to cells | `aggregate_to_cells` | Assign values to cells and aggregate them. |
| Cell neighbours | `cell_neighbours` | Return a ring or disk around a cell. |
| Cell distance | `cell_distance` | Return same-level grid distance in metres. |

The current names remain as aliases for now:

- `index_point` → `point_to_cell`;
- `polyfill` → legacy bare-GID/coverage output; use `polygon_to_cells` for `GridCellRecord` output;
- `neighbourhood` → `cell_neighbours`;
- `distance` → `cell_distance`.

New documentation should use the new names.

## 2. Common output rules

Every conversion result must include, when applicable:

```text
domain
level
x_idx
y_idx
gid
uri
```

Optional fields include:

```text
coverage_ratio
length_ratio
source_row
source_id
geometry
```

Geometry output is opt-in.

Supported geometry output modes:

```text
none
projected
wgs84
```

Supported formats can include:

```text
shapely
wkt
wkb
```

The default output should avoid geometry for speed and memory use.

## 3. Geometry rules

### Point

A point maps to exactly one cell.

The source CRS must be declared. Longitude/latitude uses `always_xy=True`.

### Polygon

`polygon_to_cells` returns one row per intersecting cell.

Each row includes an area coverage ratio.

Coverage can use:

- `GRID_PLANAR`; or
- `EQUAL_AREA`.

`polygon_to_cell` needs an explicit choice:

- `centroid`;
- `representative_point`; or
- `largest_overlap`.

The default is `centroid` for speed. Use `largest_overlap` when the polygon must be represented by its dominant cell.

### Line

`line_to_cells` returns cells with positive line-length overlap.

A line that only touches a cell corner does not count.

The result includes length coverage. Length is measured in the declared projected/grid CRS unless a future geodesic mode is requested.

## Cell dataset format

The Parquet storage contract is [cell-dataset-contract.md](cell-dataset-contract.md). It defines the manifest, reserved columns, value fields, and validation rules.

`table_to_cells` preserves selected source fields.

The caller chooses:

```text
keep_columns=None       # keep all columns
keep_columns=[...]      # keep only selected columns
source_id_column=None   # preserve a stable source ID
output_geometry=False
```

Supported input formats:

- CSV;
- XLSX; and
- Parquet.

Large files must support chunked processing where the input library allows it.

The output adds cell fields. It does not delete the original value columns unless the caller asks for that.

## 5. Value semantics

Before aggregation, the caller must declare what a value means.

Supported semantics:

- `COUNT`;
- `TOTAL`;
- `DENSITY`;
- `MEASUREMENT`;
- `RATE`; and
- `ORDINAL`.

This matters because a total, density, and average must not be combined in the same way.

## 6. Numeric aggregation

Supported numeric operations:

- `count`;
- `sum`;
- `mean`;
- `weighted_mean`;
- `median`;
- `min`;
- `max`;
- `std`; and
- `quantile`.

For geometry data, weighting must be explicit.

Examples:

- polygon total → allocate by area overlap;
- polygon density → calculate density over the target cell area;
- line measurement → weight by line length;
- point measurement → group by containing cell.

## 7. Categorical aggregation

Supported category rules:

- `largest_overlap`;
- `majority_weighted`;
- `centroid_category`;
- `priority_order`; and
- `all_categories`.

The result should include the winning category and, when useful, its coverage share.

Ties must use a deterministic rule.

## 8. Range and ordinal aggregation

Range and ordinal values are separate from normal numeric values.

Supported rules include:

- weighted majority;
- minimum;
- maximum;
- weighted mean;
- full range; and
- category distribution.

Do not silently convert an ordinal category into a normal numeric average.

## 9. Accuracy modes

### Fast

Use:

- centroid assignment;
- spatial indexes;
- no output geometry; and
- approximate overlap where declared.

### Accurate

Use:

- exact geometry intersection;
- equal-area coverage for area work;
- length-weighted line coverage;
- explicit value semantics; and
- coverage metadata.

The selected mode must be recorded in the output metadata.

## 10. ASEAN profile approval

The six priority countries are:

```text
Indonesia
Philippines
Viet Nam
Myanmar
Thailand
Malaysia
```

A profile is approved only after:

1. a reviewed full-resolution boundary is available;
2. the boundary source, license, version, and SHA-256 are recorded;
3. at least two projection candidates are tested where practical;
4. boundary edges are sampled densely;
5. interior points are sampled;
6. the full boundary fits inside the root;
7. scale error is measured and published;
8. the empty-root ratio is recorded;
9. island and detached-component behavior is documented;
10. antimeridian behavior is tested where relevant;
11. grid CRS and equal-area CRS parse with the pinned PROJ version; and
12. the final profile is reviewed before signing.

### Scale bands

These are planning bands, not absolute laws:

- **Preferred:** maximum sampled directional error `<= 1%`;
- **Conditional:** `> 1%` and `<= 2.5%`, with explicit approval;
- **Reject:** `> 2.5%` for a single-country profile.

If a country cannot meet the target, use a new regional-domain design. Do not silently accept a bad projection.

Indonesia may remain conditional if no single-country projection performs better without breaking the country-wide hierarchy.

The Philippines EQC candidate at about 7.2% is rejected and needs a different projection.
