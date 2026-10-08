# GeoSquare V2 versus existing grid systems

**Date:** 2026-09-18
**Scope:** squareness, metric consistency, hierarchy, neighbours, country boundaries, and usability
**Recommendation:** Keep GeoSquare as a country-scoped metric square grid. Do not try to replace S2 or H3 for global indexing.

## 1. Short answer

GeoSquare has a clear advantage when the goal is:

> “Give me a country-specific grid where a level-12 cell is about 50 m by 50 m and behaves like a normal Cartesian square.”

S2 and H3 have a different goal. They are global spherical indexes.

- S2 is the closest competitor in spirit because it uses quadrilateral cells and strong hierarchy.
- H3 is better for global neighbourhood and aggregation work, but it uses hexagons and pentagons.
- Geohash and Plus Codes are simple coordinate encodings. They are not strong metric grid systems.
- MGRS/UTM gives familiar local metric coordinates, but zone boundaries make one continuous national grid difficult.
- Web Mercator tiles are excellent for maps. They are not a ground-metric grid.

GeoSquare should compete on **understandable national metric squares**, not on global coverage or ecosystem size.

## 2. Fair comparison metrics

We should not compare only the number of characters or the nominal resolution. The systems use different shapes and different Earth models.

Use these metrics instead:

### Shape

What does one cell look like?

- square;
- quadrilateral;
- hexagon;
- rectangle in longitude/latitude; or
- map tile.

### Local squareness

For a cell on the ground:

```text
longest side / shortest side
```

A value of `1.0` is perfect.

This is the main metric for GeoSquare.

### Area consistency

Compare the real ground area with the nominal cell area.

This answers:

> “Are two cells at the same level actually similar in size?”

### Hierarchy

Can a parent be found by removing one level?

Can a parent produce a fixed set of children?

### Neighbour consistency

Can we find neighbours from integer offsets or a stable topology?

### Metric consistency

Can the system promise a meaningful distance or cell size?

### Global continuity

Does one grid work across the whole Earth without zones, faces, or special cases?

### Country projection support

Can each country choose its own CRS and boundary policy?

## 3. GeoSquare benchmark

The local benchmark measures the current ID and VN profiles at level 12. The all-ASEAN comparison is in `ASEAN_CROSS_SYSTEM_BENCHMARK.md`.

Level 12 is the 50 m grid-CRS level.

It samples raw GeoJSON boundary vertices with deterministic stride decimation: `benchmark_grid_systems.py` uses up to 500 vertices for ID and VN, the all-ASEAN squareness benchmark uses up to 2,000 vertices per candidate, and the cross-system benchmark uses up to 100 vertices per country. These Phase 2 baselines do not densify long segments or include a designed interior sample. The scripts transform projected cell corners back to WGS84 and measure geodesic side lengths and area.

Run it with:

```zsh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python tools/benchmark_grid_systems.py
```

Output:

```text
release/scale/GRID_SYSTEM_COMPARISON_BENCHMARK.json
```

The all-ASEAN cross-system table is in [`ASEAN_CROSS_SYSTEM_BENCHMARK.md`](ASEAN_CROSS_SYSTEM_BENCHMARK.md). It measures GeoSquare, S2, H3, geohash, and a 50 m Web Mercator square at comparable target scale.

### All ASEAN results

The full 11-country table is in [`ASEAN_SQUARENESS_BENCHMARK.md`](ASEAN_SQUARENESS_BENCHMARK.md).

### Current measurements

| Profile | Median side ratio | P95 side ratio | Maximum side ratio | Ground area ratio p05–p95 | Sampling |
|---|---:|---:|---:|---:|---|
| Indonesia | 1.0000004745 | 1.0000009452 | 1.0000011564 | 0.995189–1.009593 | 500 raw boundary vertices |
| Viet Nam | 1.0000006561 | 1.0000009656 | 1.0000010272 | 0.992861–1.007564 | 500 raw boundary vertices |

The current signed Indonesia profile is the LCC candidate `GEOSQUARE:ID_LCC_FRACTION_1_6_V2`; its separately published candidate projection-factor scale error is 0.6071%. That projection-factor value is not the same metric as Level-12 geodesic side ratio. The Phase 2 values above are boundary-sampling measurements, not universal guarantees.

Interpretation:

- Viet Nam is extremely close to a square in this boundary sample.
- The current Indonesia LCC candidate is also close to square at Level 12, despite its separate 0.6071% candidate projection-factor scale error.
- The side ratio is useful for sampled ground squareness; the area ratio is useful for sampled ground coverage.
- Neither metric is a profile approval or a universal national guarantee.

The cross-system comparison was rerun locally with the pinned optional dependencies `h3==4.3.1` and `s2sphere==0.2.5`; those versions are recorded in `release/scale/ASEAN_CROSS_SYSTEM_BENCHMARK.json`. The comparison still uses up to 100 raw boundary vertices per country and a first-sample/average-area resolution-selection protocol, so it is a Phase 2 baseline rather than a like-for-like national evaluation.

## 4. System comparison

| System | Cell shape | Metric square promise | Hierarchy | Neighbour model | Country-specific CRS | Main strength |
|---|---|---|---|---|---|---|
| **GeoSquare V2** | Exact projected square | Strong inside a profile | Strong prefix and Cartesian hierarchy | Integer neighbours/rings | Yes | Understandable national metric squares |
| **S2** | Spherical quadrilaterals | Square-like, not fixed metre squares | Strong quadtree | Strong global sphere topology | No | Global topology and containment |
| **H3** | Hexagons plus pentagons | Not square | Strong hierarchical index | Very strong neighbourhood tools | No | Global aggregation and neighbourhood analysis |
| **Geohash** | Longitude/latitude rectangles | Weak | Strong prefix | Requires neighbour-prefix handling | No | Simple strings and database prefix search |
| **Plus Codes** | Longitude/latitude grid cells | Weak to medium | Hierarchical code | Not a full topology system | No | Human-friendly point addressing |
| **Web Mercator tiles** | Projected squares | Square in map CRS, not on ground | Strong quadkey/tile hierarchy | Strong tile adjacency | No | Web maps and tile rendering |
| **MGRS/UTM** | Local projected squares | Good inside a zone | Zone and precision hierarchy | Good inside zones | Local zones | Established operational coordinate reference |
| **rHEALPix/DGGS family** | Global quadrilateral variants | Depends on the CRS and zone | Strong DGGS model | Global grid operations | Usually global | Standardized global grid research and exchange |

## 5. S2

S2 represents the Earth on a sphere. Its hierarchy starts from six cube faces and recursively divides cells into four children. Each cell is a quadrilateral bounded by geodesics.

That gives S2 strong global topology and a clean quadtree.

But it does not give a country-specific 50 m ground square. Cell shape and area vary with position on the cube projection. Face transitions also matter.

S2 is better than GeoSquare for:

- one global namespace;
- global coverings;
- spherical topology; and
- broad geospatial indexing.

GeoSquare is better for:

- national projected CRS control;
- simple metre-based cell sizes;
- ordinary Cartesian neighbour math; and
- explaining a cell as “50 m to the right and 50 m forward”.

Source: [S2 cell hierarchy](https://s2geometry.io/devguide/s2cell_hierarchy).

## 6. H3

H3 uses an icosahedral global grid. Most cells are hexagons. Twelve base areas are pentagons. Each hexagon normally has seven children.

H3 is excellent for neighbourhood and aggregation work.

It is not a square grid. It also documents that logical parent-child containment is not always exact geometric containment.

H3 is better than GeoSquare for:

- global coverage;
- hexagonal neighbourhoods;
- mature traversal APIs; and
- large ecosystem support.

GeoSquare is better for:

- square-cell semantics;
- simple 2D offsets;
- country-specific projections; and
- a clear 1/5/10 scale hierarchy.

Sources: [H3 overview](https://h3geo.org/docs/core-library/overview), [H3 indexing](https://h3geo.org/docs/highlights/indexing), and [H3 cell statistics](https://h3geo.org/docs/core-library/restable).

## 7. Geohash

Geohash interleaves latitude and longitude bits into a string. A longer prefix gives a smaller rectangle.

It is simple and useful for rough lookup.

Its weaknesses are important for GeoSquare’s goals:

- cell width changes with latitude;
- cells are not fixed metre squares;
- neighbouring cells may not share a useful prefix;
- prefix order is not a complete spatial order; and
- there is no country-specific CRS contract.

Geohash is a good secondary lookup key. It is not a replacement for GeoSquare’s canonical identity.

Source: [Mapzen’s geohash explanation](https://mapzen.com/blog/geohashes-and-you) and the [IETF geohash hint draft](https://www.ietf.org/archive/id/draft-geohash-hint-00.html).

## 8. Plus Codes / Open Location Code

Plus Codes are designed for sharing locations as human-readable codes. They use a latitude/longitude grid and a code hierarchy.

They are useful for:

- addresses;
- short location references; and
- places without normal street addresses.

They are not designed to provide:

- national projected squares;
- integer Cartesian neighbours;
- cell-distance guarantees; or
- area aggregation semantics.

GeoSquare should not copy Plus Codes as its canonical ID. A future presentation label can sit above the canonical GeoSquare URI.

Source: [Open Location Code specification](https://github.com/google/open-location-code/blob/main/Documentation/Specification/olc_definition.adoc).

## 9. Web Mercator tiles and Quadkeys

Web Mercator tiles are squares in the Web Mercator map plane. Quadkeys add a simple quadtree address.

They are excellent for web maps.

They are not a good national metric grid because the ground scale changes with latitude. A projected 50 m tile is not 50 m on the ground everywhere.

GeoSquare can still interoperate with them:

```text
GeoSquare cell → display geometry → Web Mercator tile lookup
```

But the tile ID must not become the GeoSquare identity.

Source: [OGC Two Dimensional Tile Matrix Set](https://www.ogc.org/standards/tms).

## 10. MGRS and UTM

MGRS is built on UTM and UPS zones. It gives familiar metre-based references inside local zones.

It is strong for:

- field operations;
- military and emergency use;
- existing GIS workflows; and
- local metric coordinates.

Its main problem for GeoSquare is continuity. A country can cross zones. Neighbour and parent behavior across zone borders needs special handling.

GeoSquare’s country profile approach keeps one country namespace. The trade-off is that one projection must meet the country’s distortion target.

Source: [FGDC USNG/MGRS material](https://www.fgdc.gov/standards/projects/usng).

## 11. DGGS and rHEALPix

The OGC DGGS model is broader than one specific grid. It describes hierarchical global cell systems and their operations.

rHEALPix is relevant because it shows that global quadrilateral DGGS designs are possible.

These systems are useful references for:

- global grid standards;
- data exchange;
- equal-area designs; and
- global analysis.

They do not automatically solve GeoSquare’s product goal. A global equal-area quadrilateral grid still has projection zones, face transitions, or shape trade-offs.

Source: [OGC Discrete Global Grid Systems](https://ogc.org/standard/dggs).

## 12. What GeoSquare should claim

GeoSquare should claim this:

> GeoSquare is a country-scoped, profile-driven grid of exact projected squares with a simple hierarchical size sequence and explicit ground-scale metadata.

GeoSquare should not claim:

- globally perfect squares;
- globally equal ground area;
- one projection that is optimal for every country;
- better global topology than S2; or
- better global neighbourhood behavior than H3.

## 13. Recommended position

Use GeoSquare as the **canonical national metric grid**.

Use other systems as optional secondary indexes:

```text
canonical identity: geosquare:v2:<domain>:<gid>
optional indexes:    S2, H3, geohash, Plus Code, Web Mercator tile
```

Do not convert one system into another by string manipulation.

Store the relationships explicitly when needed:

```text
geosquare_uri
s2_cell_id
h3_cell_id
geohash
web_mercator_tile
```

## 14. What to do next

The next work should be:

1. Complete the Phase 3 rerun using full boundaries for all 11 domains.
2. Densify boundary segments deterministically and add exactly 2,048 accepted interior points per domain.
3. Record seeds, point-set hashes, boundary/profile hashes, software versions, CRS metadata, and sample counts in new `release/scale/phase3/` artifacts.
4. Compare Phase 3 results with these raw-vertex Phase 2 baselines without overwriting them.
5. Finish the datum, boundary-authority, zone/component, and profile-approval review for the candidate domains.
6. Add optional S2/H3 benchmark dependencies only in the separate comparison environment.
7. Update the paper only from the versioned Phase 3 artifacts after an independent claim audit.

Do not treat the heuristic `approval_band` values in the benchmark JSON as geodetic approval. The LCC candidates remain drafts until the datum and boundary reviews close.

## Sources and note

The system descriptions above were rephrased from the linked technical documentation. The sources define each system’s design. The GeoSquare numbers come from this repository’s local benchmark script and candidate profiles.
