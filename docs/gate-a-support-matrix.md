# Gate A support matrix

**Release:** `2.2.0-rc1`
**Profile version:** `2.2.0-explicit-datum`
**Policy:** explicit datum operation per profile
**Status:** six released domains; five provisional domains

The profile writes the full WGS 84 longitude/latitude to grid pipeline. PROJ must not choose a datum operation from its database. The machine-readable source is [`release/profiles/DOMAIN_SUPPORT_MATRIX.json`](../release/profiles/DOMAIN_SUPPORT_MATRIX.json).

| Domain | Support status | Datum/reference basis | Written operation | Production guarantee |
|---|---|---|---|---|
| `BN` | Released | GDBD2009, `EPSG:5246` | None; explicit projection pipeline | Yes |
| `KH*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `ID` | Released | SRGI2013 at `2012.0`, `EPSG:9470` | `INVERSE(EPSG:15912) + EPSG:9472` | Yes |
| `LA` | Released | Lao 1997, `EPSG:4678` | `INVERSE(EPSG:1065)` | Yes |
| `MY` | Released | GDM2000, `EPSG:4742` | None; explicit projection pipeline | Yes |
| `MM*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `PH` | Released | PRS92, `EPSG:4683` | `INVERSE(EPSG:15708)` | Yes |
| `SG` | Released | SVY21, `EPSG:4757` | None; explicit projection pipeline | Yes |
| `TH*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `TL*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `VN` | Candidate | VN-2000, `EPSG:4756` | `INVERSE(EPSG:6960)`, provisional opt-in only | No |

`*` marks a provisional technical candidate.

## QA result

The report is [`release/crs-qa-2.2.0-rc1.json`](../release/crs-qa-2.2.0-rc1.json). It compares 300 spread-out boundary points per domain.

The six released domains use the written pipelines and match pinned PROJ. Their GID checks match at levels 9 and 12. The release status is a GeoSquare support classification, not official national-authority certification.

VN is available only with explicit provisional opt-in. The chosen `EPSG:6960` pipeline differs from automatic PROJ selection by up to `0.82 m` in the sample. It has no production guarantee.

## Remaining limits

The five candidate domains still need authoritative datum evidence and review. Candidate profiles must not be used as production CRS inputs.

The stated operation accuracy is not the same as source-point accuracy. A point near a 50 m cell edge may have more than one reasonable GID.
