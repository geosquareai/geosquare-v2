# Boundary policy

A V2 cell can be valid in the mathematical grid but still be outside the country we want to use.

Example:

```text
A cell crosses the coast.
Part of it is land. Part of it is sea.
```

We need a clear rule before keeping that cell.

## The four rules

### `COVERS_POINT`

Use this for a point.

The country boundary must cover the point. A point exactly on the boundary is accepted.

### `CENTROID_COVERED`

Use the cell center.

Keep the cell only when its center is inside the country.

### `INTERSECTS`

Keep the cell when it touches or overlaps the country boundary.

This is useful for general maps and discovery.

### `MIN_COVERAGE`

Keep the cell only when enough of it is inside the country.

Example:

```text
MIN_COVERAGE = 0.50
```

This keeps cells with at least 50% of their area inside the country. The current implementation measures this percentage in the grid CRS. For high-accuracy statistical area work, also use the polyfill `EQUAL_AREA` coverage mode and document the chosen rule.

## Recommended use

- point indexing: `COVERS_POINT`;
- normal polyfill: `INTERSECTS`;
- official/statistical analysis: `MIN_COVERAGE` with an explicit threshold;
- neighbourhood: calculate the grid ring first, then apply one of the cell rules.

## Important separation

The boundary does not change the cell ID.

The ID comes from:

```text
(domain, level, x_idx, y_idx)
```

The boundary only decides whether an application keeps or rejects that cell.

This means two applications can use different boundary rules without creating different grid IDs.

## Example

```python
from geosquare_v2.boundary import BoundaryPredicate, OperationalBoundary
from geosquare_v2.polyfill import polyfill

boundary = OperationalBoundary.from_profile(
    grid,
    boundary_root="src/geosquare_v2/data/registry",
)

inside = boundary.covers_lonlat(
    longitude=106.8456,
    latitude=-6.2088,
    transformer=to_grid,
)

cells = polyfill(
    grid,
    polygon,
    "EPSG:4326",
    level=9,
    boundary=boundary,
    boundary_predicate=BoundaryPredicate.INTERSECTS,
)
```

Core grid operations do not apply a boundary by themselves. Boundary-aware behavior must be explicit in the call.
