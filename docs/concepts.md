# GeoSquare V2 overview

## 1. The idea

GeoSquare assigns every location to a square cell.

The cells form a hierarchy. Large cells contain smaller cells.

A user should be able to understand the scale without learning a map projection:

```text
50 m cell = about 50 m across in the domain grid CRS
```

The implementation keeps the projection details in the country profile.

## 2. The canonical identity

A cell is identified by four fields:

```text
(domain_code, level, x_idx, y_idx)
```

- `domain_code` selects the country profile;
- `level` selects the resolution;
- `x_idx` increases eastward;
- `y_idx` increases northward.

The durable external identifier is:

```text
geosquare:v2:<domain>:<gid>
```

Example:

```text
geosquare:v2:ID:2G4M3N8P
```

Store this full URI in durable data.

A bare GID is only safe when the V2 version and domain are already fixed by the surrounding API.

## 3. The hierarchy

V2 uses alternating 5x5 and 2x2 refinements:

```text
[5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2, 5, 2]
```

The root side is 50,000 km.

| Level | Cell edge in the grid CRS |
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

Removing the last GID character gives the parent.

A base-5 refinement gives 25 children. A base-2 refinement gives 4 children.

## 4. What “square” means

A cell is an exact square in the domain’s projected grid CRS.

It is not a perfect physical square everywhere on Earth.

A country profile publishes scale metadata. This metadata tells users how much the ground size can differ from the grid size.

There are two useful measurements:

- **shape squareness:** longest side divided by shortest side;
- **size consistency:** ground area divided by nominal grid area.

Both should be checked during profile approval.

## 5. Country domains

V2 does not use one global longitude/latitude grid.

Each country gets a profile with:

- a grid CRS;
- an equal-area CRS;
- an origin;
- a root size;
- a reference epoch;
- boundary metadata;
- scale analysis; and
- a signed release version.

This keeps cells square in a useful local metric plane.

It also creates a trade-off. A country-wide projection may not be perfect everywhere.

## 6. Mathematical root versus country boundary

The mathematical root is a complete square coordinate space.

Every cell in it has a valid mathematical identity.

The country boundary is an operational filter. It decides which cells an application wants to keep.

It does not change the cell ID.

Boundary rules are explicit:

- `COVERS_POINT` for point membership;
- `CENTROID_COVERED` for cells whose center is inside;
- `INTERSECTS` for cells touching or overlapping the boundary;
- `MIN_COVERAGE` for a minimum inside-area threshold.

The core grid does not apply a boundary automatically.

## 7. Geometry is computed on read

The projected cell square is derived from:

```text
origin + cell index × cell size
```

It is not stored in a global polygon table.

For display, the projected square can be transformed to WGS84. Large cells need edge densification before transformation.

The projected square remains the source of truth.

## 8. Neighbours and distance

Neighbour operations use integer indices.

They do not use GID string order or polygon buffers.

V2 provides:

- `neighbor(dx, dy)`;
- `k_ring(k)`;
- `k_disk(k)`; and
- same-level `distance_m()`.

Grid distance is Euclidean distance in the profile grid CRS:

```text
hypot(x2 - x1, y2 - y1) × cell edge
```

It is not road distance or geodesic distance.

## 9. Data operations

GeoSquare has three main data flows:

```text
geometry → cells
points/table rows → cells
cell-assigned values → aggregation
```

The public names describe the direction:

```text
point_to_cell
polygon_to_cells
line_to_cells
table_to_cells
aggregate_to_cells
```

Each flow has its own coverage and value rules.

## 10. What GeoSquare is not

GeoSquare is not:

- a global replacement for S2 or H3;
- a street or road network;
- a geodesic distance engine;
- a legal boundary authority;
- a random word alias system; or
- a promise of exactly equal ground area in every country.

Its job is narrower and clearer: a readable, country-scoped, metric square grid.
