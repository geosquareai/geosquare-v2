# Gate B boundary-data and attribution decision

**Release candidate:** `0.2.0`
**Status:** PH redistribution approved; separate non-PH license-family review prepared
**Scope:** bundled boundary resources used by the stable candidate

This record separates mechanical provenance/hash verification from legal or redistribution approval. The project is not making a legal determination through this document.

## Evidence prepared

The stable candidate records the following for the 11 current domain boundary inputs:

- pinned geoBoundaries API and full/simplified download URLs;
- full and simplified filenames;
- boundary ID and source year;
- source organization or attribution;
- recorded file-specific license;
- license reference;
- SHA-256 values; and
- build date.

The profile and scale inputs use the recorded full files. The bundled legacy names are also explicit: `ID.geojson` is byte-identical to `ID_simplified.geojson`, and `VN.geojson` is byte-identical to `VN_simplified.geojson`; their hashes and inherited source/license records are recorded in `ASEAN_BOUNDARY_METADATA.json`.

The authoritative metadata files are:

- [`release/boundaries/ASEAN_BOUNDARY_METADATA.json`](../release/boundaries/ASEAN_BOUNDARY_METADATA.json);
- [`release/boundaries/SOURCES.md`](../release/boundaries/SOURCES.md);
- [`src/geosquare_v2/data/registry/boundaries/ASEAN_BOUNDARY_METADATA.json`](../src/geosquare_v2/data/registry/boundaries/ASEAN_BOUNDARY_METADATA.json); and
- [`NOTICE`](../NOTICE);
- [`docs/gate-b-license-review.md`](gate-b-license-review.md); and

## License and attribution inventory

| Files/domains | Recorded license | Attribution/source status |
|---|---|---|
| BN | Public Domain | Wikimedia Commons recorded |
| KH, ID, LA, MY, SG, TH, TL | ODbL 1.0 | OpenStreetMap/recorded source attribution |
| MM | CC BY-SA 2.0 | OpenStreetMap/recorded source attribution |
| PH | CC BY 3.0 IGO | OCHA Philippines/NAMRIA recorded; source URL and canonical license text recorded; release-owner approved |
| VN | CC BY 4.0 | geoBoundaries/Wikimedia Commons recorded |

For PH, the online geoBoundaries API record identifies the source dataset as [HDX Philippines administrative levels 0–3](https://data.humdata.org/dataset/philippines-administrative-levels-0-to-3) and reports `CC BY 3.0 IGO`. Its `licenseSource` value is the literal placeholder `Data https`, so the stable record uses the canonical [CC BY 3.0 IGO license text](https://creativecommons.org/licenses/by/3.0/igo/) and preserves the HDX dataset URL separately as `boundary_source_url`.

## Mechanical checks required for closure

Before signing or publishing, run and retain evidence for:

1. every metadata JSON file parses;
2. every recorded full and simplified hash matches the packaged file;
3. the legacy ID/VN alias hashes match the recorded simplified hashes;
4. mirrored metadata and source notes agree;
5. every profile boundary hash matches its full boundary and scale report;
6. attribution and non-endorsement language is present in `NOTICE`; and
7. the final signed registry references the same profile/boundary inputs.

## Release-owner decision

### Philippines files

The release owner approved redistribution of the exact `PH_full.geojson` and `PH_simplified.geojson` files recorded in `ASEAN_BOUNDARY_METADATA.json` under CC BY 3.0 IGO, with the attribution and non-endorsement language in `NOTICE`.

```text
Decision owner: Release owner
Decision date: 2026-10-08
Decision:     APPROVE
Scope:        PH_full.geojson and PH_simplified.geojson, exact recorded hashes
License:      CC BY 3.0 IGO
Terms:        attribution and non-endorsement language retained
```

This approval is a project release decision, not independent legal advice. It does not certify legal sovereignty, boundary authority, or geodetic accuracy.

### Other boundary files

This PH approval does not relabel or replace the recorded licenses for BN, KH, ID, LA, MY, MM, SG, TH, TL, or VN. The release owner separately approved those exact file groups under their existing Public Domain, ODbL 1.0, CC BY-SA 2.0, and CC BY 4.0 terms on 2026-10-08; the per-family scopes and obligations are recorded in [`gate-b-license-review.md`](gate-b-license-review.md).
