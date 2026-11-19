# Country profiles

## 1. Why profiles exist

A single world longitude/latitude grid does not keep metre-sized cells consistent everywhere.

GeoSquare uses one signed profile per country domain.

The profile chooses:

- the canonical grid CRS;
- the equal-area CRS;
- the origin;
- the root size;
- the reference epoch;
- the boundary source; and
- the measured scale error.

The profile is part of the meaning of a GeoSquare ID.

A profile must never be edited in place after release.

## 2. Profile fields

A release profile includes:

```text
domain_id
domain_code
name
profile_version
origin_x_m
origin_y_m
root_side_m
reference_epoch
grid_crs
crs_wkt2
equal_area_crs
equal_area_crs_wkt2
min_level
max_level
scale_error_max_pct
scale_error_method
scale_metadata_sha256
boundary_source_crs
boundary_file
boundary_sha256
boundary_source
```

The registry also records the required PROJ version and resource hashes.

## 3. Current ASEAN work

The current scope has 11 ASEAN members:

```text
BN  Brunei Darussalam
KH  Cambodia
ID  Indonesia
LA  Lao PDR
MY  Malaysia
MM  Myanmar
PH  Philippines
SG  Singapore
TH  Thailand
TL  Timor-Leste
VN  Viet Nam
```

Simplified boundaries are available for all 11.

Full boundary candidates are available for:

```text
ID, MY, MM, PH, TH, VN
```

Source and license details are in:

- [`SOURCES.md`](../release/boundaries/SOURCES.md);
- [`ASEAN_COVERAGE_PROJECTION.md`](../internal/research/ASEAN_COVERAGE_PROJECTION.md); and
- [`ASEAN_BOUNDARY_METADATA.json`](../release/boundaries/ASEAN_BOUNDARY_METADATA.json).

## 4. Current support classes

The stable `1.1.0` release marks six profiles as production-ready under GeoSquare's support policy. Five profiles remain provisional technical candidates.

| Domain | Support status | Datum or CRS basis | Review note |
|---|---|---|---|
| BN | Released | GDBD2009 | Production-ready in the support matrix |
| ID | Released | SRGI2013 at epoch 2012.0 | Explicit datum operation |
| LA | Released | Lao 1997 | Explicit datum operation |
| MY | Released | GDM2000 | Production-ready in the support matrix |
| PH | Released | PRS92 | Explicit datum operation |
| SG | Released | SVY21 | Production-ready in the support matrix |
| KH | Candidate | WGS84-style technical base | Provisional |
| MM | Candidate | WGS84-style technical base | Provisional |
| TH | Candidate | WGS84-style technical base | Provisional |
| TL | Candidate | WGS84-style technical base | Provisional |
| VN | Candidate | VN-2000 with `EPSG:6960` | Explicit opt-in only |

## 5. Approval bands

Planning bands:

- **Preferred:** maximum sampled directional error `<= 1%`;
- **Conditional:** `> 1%` and `<= 2.5%`;
- **Reject:** `> 2.5%` for one country-wide profile.

These bands are not the only approval rule.

A profile also needs boundary, datum, component, and legal-scope review.

## 6. Profile approval checklist

Before signing a profile:

1. Use the final reviewed boundary.
2. Record the source, license, version, and SHA-256.
3. Test at least two practical projection candidates.
4. Sample boundary edges densely.
5. Sample points inside the country.
6. Check root coverage.
7. Measure ground side ratio.
8. Measure ground area ratio.
9. Record empty-root ratio.
10. Test islands and detached components.
11. Test antimeridian behavior where relevant.
12. Parse both CRS definitions with the pinned PROJ version.
13. Run scalar, geometry, boundary, and polyfill fixtures.
14. Review the generated profile diff.
15. Sign a new registry database.

## 7. Metrics

At level 12, the nominal cell is 50 m × 50 m.

Useful profile metrics are:

### Side anisotropy

```text
longest ground side / shortest ground side
```

`1.0` is perfect.

### Area ratio

```text
geodesic ground area / 2,500 m²
```

`1.0` is nominal size.

### Scale error

Maximum measured directional projection scale error.

### Root occupancy

The approximate part of the 50,000 km root occupied by the country bounding box.

A low occupancy is not automatically bad. It is a trade-off for keeping one national namespace.

## 8. Profile changes

Changing any of these can change cell IDs:

- origin;
- grid CRS;
- root size;
- subdivision rules; or
- level meaning.

Such a change needs a new profile version and a migration plan.

Do not silently replace a released profile.
