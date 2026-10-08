# Gate B non-Philippines license-family review

**Release candidate:** `0.2.0`
**Status:** all four non-PH license families approved by the release owner
**Scope:** all non-Philippines boundary files in the stable candidate

This is a release-owner review record, not legal advice or a legal determination. The review approves or holds redistribution of the exact files and hashes recorded in `release/boundaries/ASEAN_BOUNDARY_METADATA.json`; it does not change the underlying license terms.

## Review inventory

| Group | Domains | Exact files | Count | Canonical license reference | Recorded source/reference |
|---|---|---|---:|---|---|
| Public Domain | BN | `BN_full.geojson`, `BN_simplified.geojson` | 2 | Recorded as Public Domain | Wikimedia Commons; pinned geoBoundaries URLs and `commons.wikimedia.org/wiki/File` reference |
| ODbL 1.0 | KH, ID, LA, MY, SG, TH, TL | Full and simplified files for seven domains, plus legacy `ID.geojson` alias | 15 | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) | OpenStreetMap/Wambacher for KH/ID/LA/MY/TH/TL; URA/ADM 3 for SG; pinned geoBoundaries URLs |
| CC BY-SA 2.0 | MM | `MM_full.geojson`, `MM_simplified.geojson` | 2 | [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) | OpenStreetMap; pinned geoBoundaries URLs |
| CC BY 4.0 | VN | `VN_full.geojson`, `VN_simplified.geojson`, legacy `VN.geojson` alias | 3 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) | geoBoundaries/Wikimedia Commons; pinned geoBoundaries URLs |

The PH files are intentionally excluded from this table because their separate approval is recorded in [`gate-b-decision.md`](gate-b-decision.md).

## Exact evidence

For each group, the metadata records the API endpoint, pinned full/simplified URLs, boundary ID, year, source, license, license reference, and SHA-256. The profile inputs use the full files. `ID.geojson` equals `ID_simplified.geojson` byte-for-byte, and `VN.geojson` equals `VN_simplified.geojson` byte-for-byte; the aliases inherit the corresponding ODbL or CC BY 4.0 record.

The authoritative records are:

- [`release/boundaries/ASEAN_BOUNDARY_METADATA.json`](../release/boundaries/ASEAN_BOUNDARY_METADATA.json)
- [`release/boundaries/SOURCES.md`](../release/boundaries/SOURCES.md)
- [`src/geosquare_v2/data/registry/boundaries/ASEAN_BOUNDARY_METADATA.json`](../src/geosquare_v2/data/registry/boundaries/ASEAN_BOUNDARY_METADATA.json)
- [`NOTICE`](../NOTICE)
- [`docs/data-licenses.md`](data-licenses.md)

## Project release checklist

This checklist records what the release owner should confirm for each group:

- [ ] exact files and SHA-256 values match the metadata;
- [ ] source attribution is retained;
- [ ] the applicable license link is retained;
- [ ] material simplification/transformation is disclosed;
- [ ] no source or government authority is represented as endorsing GeoSquare;
- [ ] the candidate administrative-boundary and non-sovereignty disclaimer remains present; and
- [ ] any ODbL/CC BY-SA/database/share-alike implications have been reviewed for this exact redistribution.

The checklist is a project release control. It does not replace review of the applicable license terms.

## Separate release-owner decisions

### Public Domain — BN

```text
Decision owner: Release owner
Decision date: 2026-10-08
Decision:     APPROVE
Scope:        BN_full.geojson and BN_simplified.geojson, exact hashes in metadata
Notes:        Attribution, candidate-boundary, and non-endorsement wording retained.
```

### ODbL 1.0 — KH, ID, LA, MY, SG, TH, TL

```text
Decision owner: Release owner
Decision date: 2026-10-08
Decision:     APPROVE
Scope:        15 exact files: seven full/simplified pairs plus ID.geojson alias
Notes:        ODbL source/license and attribution obligations retained.
```

### CC BY-SA 2.0 — MM

```text
Decision owner: Release owner
Decision date: 2026-10-08
Decision:     APPROVE
Scope:        MM_full.geojson and MM_simplified.geojson, exact hashes in metadata
Notes:        CC BY-SA attribution/share-alike obligations retained.
```

### CC BY 4.0 — VN

```text
Decision owner: Release owner
Decision date: 2026-10-08
Decision:     APPROVE
Scope:        VN_full.geojson, VN_simplified.geojson, and VN.geojson alias
Notes:        CC BY attribution and change-disclosure obligations retained.
```

All four groups are approved for redistribution of the exact recorded files under their existing license terms, with the attribution, change-disclosure, candidate-boundary, and non-endorsement requirements above.

```text
Approval owner: Release owner
Approval date: 2026-10-08
Groups: Public Domain BN; ODbL 1.0 KH/ID/LA/MY/SG/TH/TL; CC BY-SA 2.0 MM; CC BY 4.0 VN
```

This approval is a project release decision, not independent legal advice. It does not certify legal sovereignty, boundary authority, or geodetic accuracy.
