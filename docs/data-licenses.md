# Code and boundary-data licenses

GeoSquare V2 is a mixed-content distribution:

- **Python code and project documentation:** Apache License 2.0, as stated in [`LICENSE`](../LICENSE).
- **Bundled boundary data:** licensed according to the source and license recorded for each exact file below.

The Apache-2.0 license for the GeoSquare code does **not** relicense, replace, or override the licenses of third-party boundary data. Do not describe all bundled data as Apache-2.0 or CC BY merely because the Python package is distributed under Apache-2.0.

## Recorded boundary licenses

These records come from `release/boundaries/ASEAN_BOUNDARY_METADATA.json` and the bundled source notes. Full and simplified files use the same recorded source/license entry for each domain.

| Domain | Files | Recorded source/license |
|---|---|---|
| BN | `BN_full.geojson`, `BN_simplified.geojson` | Wikimedia Commons / Public Domain |
| KH | `KH_full.geojson`, `KH_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| ID | `ID_full.geojson`, `ID_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| LA | `LA_full.geojson`, `LA_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| MY | `MY_full.geojson`, `MY_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| MM | `MM_full.geojson`, `MM_simplified.geojson` | OpenStreetMap / CC BY-SA 2.0 |
| PH | `PH_full.geojson`, `PH_simplified.geojson` | OCHA Philippines and NAMRIA / CC BY 3.0 IGO |
| SG | `SG_full.geojson`, `SG_simplified.geojson` | Urban Redevelopment Authority, derived from ADM 3 / ODbL 1.0 |
| TH | `TH_full.geojson`, `TH_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| TL | `TL_full.geojson`, `TL_simplified.geojson` | OpenStreetMap, Wambacher / ODbL 1.0 |
| VN | `VN_full.geojson`, `VN_simplified.geojson` | geoBoundaries, Wikipedia / CC BY 4.0 |

The Philippines record identifies the source dataset as [HDX Philippines administrative levels 0–3](https://data.humdata.org/dataset/philippines-administrative-levels-0-to-3). The geoBoundaries API reports `CC BY 3.0 IGO` but exposes the malformed license-source value `Data https`; the stable record links the canonical [CC BY 3.0 IGO license text](https://creativecommons.org/licenses/by/3.0/igo/) separately.

The release owner approved redistribution of all listed boundary files on 2026-10-08 under their recorded Public Domain, ODbL 1.0, CC BY-SA 2.0, CC BY 3.0 IGO, or CC BY 4.0 terms, with the required attribution, change-disclosure, and non-endorsement language. This approval is a project release decision, not legal advice.

The source directory also contains legacy candidate files `ID.geojson` and `VN.geojson`. They are byte-identical aliases of `ID_simplified.geojson` and `VN_simplified.geojson`, and their hashes and inherited source/license records are included in `ASEAN_BOUNDARY_METADATA.json`.

## What users must preserve

For every redistributed boundary file or derived database:

1. retain appropriate source credit and the applicable license link;
2. identify material changes, simplification, transformation, or other adaptation;
3. preserve required notices and attribution information;
4. do not imply that a source or government authority endorses GeoSquare; and
5. do not apply additional legal or technical restrictions that conflict with the applicable license.

ODbL and CC BY-SA are not attribution-only licenses in every situation. Redistribution, adaptation, or combining data into a database may create additional notice, licensing, or share-alike obligations. Review those obligations for the exact use before publication. The project does not grant a blanket Apache-2.0 or CC BY license over third-party data.

## Source and license references

- [GeoBoundaries project](https://github.com/wmgeolab/geoBoundaries)
- [GeoBoundaries usage and attribution guidance](https://www.geoboundaries.org/)
- [OpenStreetMap copyright and ODbL guidance](https://www.openstreetmap.org/copyright)
- [Open Data Commons ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
- [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/)
- [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/)
- [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

Exact API URLs, pinned GitHub revisions, boundary IDs, build dates, and SHA-256 values remain in [`ASEAN_BOUNDARY_METADATA.json`](../release/boundaries/ASEAN_BOUNDARY_METADATA.json). The release-level attribution notice is [`NOTICE`](../NOTICE).

This document explains the project’s distribution model; it is not legal advice or a legal determination that redistribution is approved.
