# Gate A support matrix

**Release candidate:** `0.2.0`
**Profile version:** `2.1.0-static-datum`
**Policy:** option 2
**Status:** release-owner classification recorded; production support is limited to the seven approved domains below

The release owner approved `BN`, `ID`, `LA`, `MY`, `PH`, `SG`, and `VN` as production-ready for the GeoSquare stable-release support scope. `KH`, `MM`, `TH`, and `TL` remain bundled as provisional technical candidates. This is a GeoSquare release classification, not an official national-authority endorsement or legal/geodetic certification. The machine-readable source is [`release/profiles/DOMAIN_SUPPORT_MATRIX.json`](../release/profiles/DOMAIN_SUPPORT_MATRIX.json).

| Domain | Support classification | Datum/reference basis | Decision status | Production guarantee |
|---|---|---|---|---|
| `BN` | Production-ready | GDBD2009, `EPSG:5246` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `KH` | Provisional technical candidate | National datum not established; WGS84-style technical base | Provisional | No |
| `ID` | Production-ready | SRGI2013 static realization at `2012.0`, `EPSG:9470` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `LA` | Production-ready | Lao 1997, `EPSG:4678` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `MY` | Production-ready | GDM2000, `EPSG:4742` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `MM` | Provisional technical candidate | National datum not established; WGS84-style technical base | Provisional | No |
| `PH` | Production-ready | PRS92, `EPSG:4683` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `SG` | Production-ready | SVY21, `EPSG:4757` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |
| `TH` | Provisional technical candidate | National horizontal datum not established; WGS84-style technical base | Provisional | No |
| `TL` | Provisional technical candidate | Modern national horizontal datum not verified; WGS84-style technical base | Provisional | No |
| `VN` | Production-ready | VN-2000, `EPSG:4756` | Release-owner approved 2026-10-08 | Yes, within GeoSquare scope |

## Evidence and limitations

The profiles have custom GeoSquare WKT2 projected CRSs, linked scale reports, pinned PROJ/pyproj measurements, boundary hashes, and phase-3 root-coverage evidence. ID remains explicitly static: input coordinates must already be normalized to the SRGI2013 realization at epoch `2012.0`, and the runtime does not perform dynamic epoch transformation.

Production-ready here means approved for the GeoSquare release support scope using the recorded static profile and documented limitations. It does not mean that the custom projected CRS is an official national projected CRS, that GeoSquare performs authoritative datum transformations, or that the bundled boundary is legally authoritative.

KH, MM, TH, and TL remain provisional because their national horizontal datum/reference-frame evidence and transformation policies are unresolved. They must not be described as official national CRS support or as having production geodetic accuracy guarantees.
