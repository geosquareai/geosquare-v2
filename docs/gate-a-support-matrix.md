# Gate A support matrix

**Release:** `2.2.0-rc1`
**Profile version:** `2.2.0-explicit-datum`
**Policy:** explicit datum operation per profile
**Status:** CRS QA candidate; VN remains blocked

The profile now writes the full WGS 84 longitude/latitude to grid pipeline. PROJ must not choose a datum operation from its database. The machine-readable source is [`release/profiles/DOMAIN_SUPPORT_MATRIX.json`](../release/profiles/DOMAIN_SUPPORT_MATRIX.json).

| Domain | Support status | Datum/reference basis | Written operation | Production guarantee |
|---|---|---|---|---|
| `BN` | Candidate | GDBD2009, `EPSG:5246` | None; explicit projection pipeline | No |
| `KH*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `ID` | Candidate | SRGI2013 at `2012.0`, `EPSG:9470` | `INVERSE(EPSG:15912) + EPSG:9472` | No |
| `LA` | Candidate | Lao 1997, `EPSG:4678` | `INVERSE(EPSG:1065)` | No |
| `MY` | Candidate | GDM2000, `EPSG:4742` | None; explicit projection pipeline | No |
| `MM*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `PH` | Candidate | PRS92, `EPSG:4683` | `INVERSE(EPSG:15708)` | No |
| `SG` | Candidate | SVY21, `EPSG:4757` | None; explicit projection pipeline | No |
| `TH*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `TL*` | Candidate | WGS84-style technical base | None; explicit projection pipeline | No |
| `VN` | Candidate | VN-2000, `EPSG:4756` | `INVERSE(EPSG:6960)`, provisional opt-in only | No |

`*` marks a provisional technical candidate.

## QA result

The report is [`release/crs-qa-2.2.0-rc1.json`](../release/crs-qa-2.2.0-rc1.json). It compares 300 spread-out boundary points per domain.

ID, LA, and PH match the pinned PROJ result with the written pipeline. Their GID checks also match at levels 9 and 12. This proves reproducibility. It does not prove real-world accuracy without independent control points.

VN is available only with explicit provisional opt-in. The chosen `EPSG:6960` pipeline differs from automatic PROJ selection by up to `0.82 m` in the sample. It has no production guarantee.

## Release gate still open

A domain needs independent control points, round-trip checks, edge checks, ground-size checks, and release-owner approval. Until then, candidate profiles must not be called production-ready.

The stated operation accuracy is not the same as source-point accuracy. A point near a 50 m cell edge may have more than one reasonable GID.
