# Comparison with other grid systems

## 1. Main conclusion

GeoSquare is designed for a specific job:

> country-scoped, understandable metric square cells.

It is not a global replacement for S2 or H3.

Use GeoSquare as the canonical national grid. Add S2, H3, geohash, or Web Mercator indexes only when another system helps a specific query.

## 2. Systems compared

The project compares GeoSquare with:

- S2;
- H3;
- geohash;
- Open Location Code / Plus Codes;
- Web Mercator tiles; and
- MGRS/UTM.

The detailed reports are:

- [`GRID_SYSTEM_COMPARISON.md`](../internal/research/GRID_SYSTEM_COMPARISON.md);
- [`ASEAN_CROSS_SYSTEM_BENCHMARK.md`](../internal/research/ASEAN_CROSS_SYSTEM_BENCHMARK.md); and
- [`ASEAN_SQUARENESS_BENCHMARK.md`](../internal/research/ASEAN_SQUARENESS_BENCHMARK.md).

## 3. Metrics

The ASEAN cross-system benchmark uses a target of 50 m × 50 m.

It records:

- geodesic cell area;
- p05, median, and p95 area;
- area error from 2,500 m²;
- shortest and longest side;
- side anisotropy;
- shape compactness;
- selected resolution; and
- sample count.

A square has compactness about `0.7854`.

A regular hexagon has compactness about `0.9069`.

Compactness describes shape. It does not say that a hexagon is bad.

## 4. ASEAN result

Across all 11 ASEAN countries:

- GeoSquare stays closest to the 50 m target area;
- GeoSquare keeps square side behavior;
- H3 gives strong neighbourhood behavior but uses hexagons;
- S2 gives global quadrilateral topology but has larger area and side variation;
- geohash gives rectangular cells with roughly 2:1 side ratios at the tested precision;
- Web Mercator gives map-plane squares, not stable ground squares.

The full numeric table is in [`ASEAN_CROSS_SYSTEM_BENCHMARK.md`](../internal/research/ASEAN_CROSS_SYSTEM_BENCHMARK.md).

## 5. S2

S2 projects six cube faces onto the sphere and recursively divides cells into four children.

Strengths:

- global namespace;
- strong hierarchy;
- spherical topology;
- useful region covering.

Limits for GeoSquare’s goal:

- not a country-specific metre grid;
- cell area and shape vary by position;
- cube-face effects exist.

Source: [S2 cell hierarchy](https://s2geometry.io/devguide/s2cell_hierarchy).

## 6. H3

H3 uses an icosahedral grid.

Most cells are hexagons. Twelve base cells are pentagons.

Strengths:

- neighbourhood analysis;
- large ecosystem;
- global indexing;
- aggregation workflows.

Limits for GeoSquare’s goal:

- not square;
- pentagons need special handling;
- logical parent containment is not always exact geometric containment;
- no country-specific metric CRS.

Source: [H3 overview](https://h3geo.org/docs/core-library/overview).

## 7. Geohash

Geohash stores latitude/longitude subdivisions in a string.

Strengths:

- simple;
- compact;
- useful for rough prefix lookup.

Limits:

- physical width changes with latitude;
- cells are rectangles, not metre squares;
- prefix order is not a complete spatial order;
- no country profile.

## 8. Plus Codes

Plus Codes are location-sharing codes.

They are useful for human communication. They are not a full topology or aggregation grid.

Source: [Open Location Code specification](https://github.com/google/open-location-code/blob/main/Documentation/Specification/olc_definition.adoc).

## 9. Web Mercator tiles

Web Mercator tiles are squares in the map projection.

They are excellent for web maps.

Their ground scale changes with latitude. A 50 m projected tile is not always a 50 m ground square.

Source: [OGC Tile Matrix Set](https://www.ogc.org/standards/tms).

## 10. MGRS and UTM

MGRS/UTM provides established local metric coordinates.

The main problem is zones. A country-wide hierarchy across multiple zones needs special rules.

Source: [FGDC USNG/MGRS](https://www.fgdc.gov/standards/projects/usng).

## 11. Recommended use

Store GeoSquare as the canonical identity:

```text
geosquare:v2:<domain>:<gid>
```

Optionally store secondary indexes:

```text
s2_cell_id
h3_cell_id
geohash
web_mercator_tile
```

Do not convert between systems by changing strings.
