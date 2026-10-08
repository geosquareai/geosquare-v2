# National-datum-based custom CRS plan

This document defines the target design for a future GeoSquare technical candidate. It does **not** modify the published `0.1.0rc1` profiles, signed registry, or artifacts.

## Design principle

Each domain gets one GeoSquare-owned canonical projected CRS:

```text
national datum/reference frame + GeoSquare custom metric projection
```

Official national projected zones are ingestion and interoperability metadata. They are not alternate canonical GeoSquare roots, zone-specific GIDs, or separate cell namespaces.

For example:

```text
GEOSQUARE:ID_SRGI2013_LCC_V2
```

means “a GeoSquare custom LCC grid whose geographic datum base is SRGI2013.” It does not claim that the custom LCC is an official Indonesian projected CRS.

## Epoch policy

### Policy for the next static technical candidate

Use a **static-realization policy**:

- a profile may declare a realization/reference epoch as metadata;
- the runtime does not infer an epoch from the system clock;
- the current 2D API does not accept or propagate a coordinate epoch;
- a dynamic national frame must not be treated as dynamically transformed merely because its WKT2 contains a frame epoch;
- inputs must already be in the documented static realization expected by the profile, or be transformed by the caller using an authoritative operation before indexing; and
- the profile must clearly state that it is a technical static realization, not full dynamic-epoch support.

Do not invent a coordinate epoch. A frame epoch, coordinate observation epoch, and transformation realization epoch are different concepts.

### Future dynamic policy

A future dynamic release should add an explicit `coordinate_epoch` to point, geometry, batch, table, dataset, and query APIs. It must pass that epoch through the PROJ operation, require it for dynamic-required profiles, persist epoch provenance with cell assignments, hash required velocity/deformation resources, and version the dataset/registry contract. Until those changes exist, SRGI2013/ITRF-style dynamic transformations remain deferred rather than silently approximated.

## Target domain definitions

These are design targets, not current signed profiles. `GEOSQUARE:*` identifiers are project-owned authority labels and must not be confused with EPSG authority codes.

| Domain | Datum/reference base | GeoSquare target | Zone/component policy | Epoch disposition | Status |
|---|---|---|---|---|---|
| BN | GDBD2009, geographic base `EPSG:5246`; official Brunei BRSO `EPSG:5247` is an interoperability reference | `GEOSQUARE:BN_GDBD2009_LCC_V2` | Brunei BRSO accepted as input/reference metadata; one canonical root | Static realization pending authoritative epoch/operation review | Target |
| KH | Cambodian national datum/grid not yet sufficiently evidenced | `GEOSQUARE:KH_NATIONAL_DATUM_LCC_V2` | No zone claim until the official Cambodian source is confirmed | Static only after authoritative datum and realization are confirmed | Deferred |
| ID | SRGI2013 static realization target, based on geographic base `EPSG:9470` and fixed realization epoch `2012.0` | `GEOSQUARE:ID_SRGI2013_STATIC2012_LCC_V2` | SRGI2013 UTM/TM zones are input/reference metadata only | Static candidate requires pre-normalized SRGI2013-at-2012 coordinates; runtime does not perform dynamic epoch transformation | Candidate included in the stable `0.2.0` support scope |
| LA | Lao 1997 geographic base `EPSG:4678` | `GEOSQUARE:LA_LAO1997_LCC_V2` | Official Lao zones are input/reference metadata only | Static realization and transformations require authority review | Target |
| MY | GDM2000 geographic base `EPSG:4742` | `GEOSQUARE:MY_GDM2000_LCC_V2` | Peninsula RSO `EPSG:3375` and East Malaysia BRSO `EPSG:3376` are ingestion/reference metadata; one canonical root | Static candidate policy, with component behavior documented | Target |
| MM | Myanmar Datum 2000 is a research target, but authoritative WKT/parameters are not yet available | `GEOSQUARE:MM_MYANMAR_DATUM2000_LCC_V2` | No legacy Indian datum as canonical; input use requires source metadata and tested transformation | Epoch and transformation policy pending | Deferred/research |
| PH | PRS92 geographic base `EPSG:4683`; check the current official PRS2020 direction before finalizing | `GEOSQUARE:PH_PRS92_LCC_V2` or an approved PRS2020-based successor | PRS92 zones `EPSG:3121`–`3125` are input/reference metadata only | Static realization pending current national standard review | Research target |
| SG | SVY21 geographic base `EPSG:4757`; official SVY21/TM `EPSG:3414` is an interoperability reference | `GEOSQUARE:SG_SVY21_METRIC_V2` | Singapore TM is input/reference metadata; one canonical root | Static candidate policy | Target |
| TH | WGS84/ITRF2008 is a documented research baseline, but the active official production operation must be confirmed | `GEOSQUARE:TH_ITRF2008_LCC_V2` | UTM/Indian 1975 systems are input-only when documented; no canonical legacy datum assumption | Dynamic/reference epoch policy pending | Research target |
| TL | No verified modern national reference frame has been located | `GEOSQUARE:TL_NATIONAL_DATUM_LCC_V2` | Explicit WGS84/ITRF fallback may be provisional input only; component policy required | Epoch policy pending official frame | Deferred/provisional |
| VN | VN-2000 geographic base `EPSG:4756` | Existing `GEOSQUARE:VN_VN2000_LCC_V2` baseline | National zone/component behavior must still be documented | Existing profile records `2000.0`; runtime treats it as metadata only | Existing baseline |

The EPSG codes above are reference definitions, not permission to claim that every target is an approved national operational profile. EPSG is the source for CRS parameter definitions; national authorities remain the source for operational datum, epoch, transformation, and area-of-use decisions. See the [EPSG Geodetic Parameter Dataset](https://epsg.org/), the [Myanmar Datum 2000 reference presentation](https://un-ggim-ap.org/sites/default/files/media/meetings/Plenary05/201607/W020161026570135032964.pdf), and the [Royal Thai Survey Department reference material](https://un-ggim-ap.org/sites/default/files/media/meetings/Plenary05/201607/W020161026570135201666.pdf).

## Required evidence before implementation

For each target profile, obtain and record:

1. authoritative datum/reference-frame source;
2. geographic CRS WKT2 and projected conversion definition;
3. official area of use and source-coordinate transformations;
4. frame epoch, coordinate epoch requirements, and static/dynamic policy;
5. velocity/deformation resources if dynamic behavior is required;
6. official zone/component and island policy;
7. full-boundary distortion results and root-fit checks;
8. round-trip and point/geometry tests; and
9. an explicit approval that the profile is technical-candidate or production eligible.

## Implementation sequence

1. Add explicit profile metadata for `epoch_policy`, datum base, source CRS aliases, and transformation provenance.
2. Add `source_crs` and optional `coordinate_epoch` to APIs before enabling dynamic profiles.
3. Implement and test epoch-aware PROJ transformations; reject missing epochs for dynamic-required profiles.
4. Generate candidate profiles and scale reports in a new staging tree, not over the published `release/` inputs.
5. Build a new SQLite registry, verify boundary/scale hashes and exact PROJ resources, and sign it with the existing external registry key.
6. Build the selected stable package version `0.2.0`; never overwrite published candidate artifacts.
7. Run the full test, clean-install, TestPyPI, and registry smoke-test sequence before considering PyPI.

Until steps 1–3 exist, only static, explicitly documented realization profiles should be implemented. Dynamic national datum claims should remain deferred.
