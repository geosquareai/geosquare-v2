# Boundary sources

These files are candidate administrative boundaries. They are not an assertion of legal sovereignty, maritime jurisdiction, or final operational policy. No source or government authority is represented as endorsing GeoSquare.

The current ASEAN scope has 11 member states, including Timor-Leste. See the [ASEAN member list](https://asean.org/about-us).

## Source and licensing

The simplified files were downloaded from the official [geoBoundaries API](https://www.geoboundaries.org/api/current/gbOpen/). Each API record links to the exact simplified GeoJSON file used here.

The files with the `_simplified` suffix are for projection planning, visual checks, and candidate work. They are not yet approved as the final high-resolution operational boundaries.

| Domain | Country | File | Boundary ID | Year | Source | License | SHA-256 |
|---|---|---|---|---:|---|---|---|
| `BN` | Brunei Darussalam | `BN_simplified.geojson` | `BRN-ADM0-51999400` | 2015 | Wikimedia Commons | Public Domain | `c024f46fe6177455381f1e556d74aa21ab73180b88c4eed70db691aff916236e` |
| `KH` | Cambodia | `KH_simplified.geojson` | `KHM-ADM0-94605694` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `8d0a6e840681097f602bb2991845da07903560892d3b917c21091f70c8e9a414` |
| `ID` | Indonesia | `ID_simplified.geojson` | `IDN-ADM0-11942859` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `adb38ba53ef172f63ffdc93da69827725cbd319c7b1d4b5c79ab08e5544b8fa3` |
| `LA` | Lao PDR | `LA_simplified.geojson` | `LAO-ADM0-69401296` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `3c878cb2d5c983705eac14bd1b3a7a7a6453d788e038637d066b7b0eef3d33b3` |
| `MY` | Malaysia | `MY_simplified.geojson` | `MYS-ADM0-87038898` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `37be7210ed0f6d82cc865c98756e4b373fdb05a8a3b3a51dad16e7508ac748a1` |
| `MM` | Myanmar | `MM_simplified.geojson` | `MMR-ADM0-35516675` | 2021 | OpenStreetMap | CC BY-SA 2.0 | `61d90a3c6faf06d8d34b757bb243022bbb0429d193885662b9976686409ed325` |
| `PH` | Philippines | `PH_simplified.geojson` | `PHL-ADM0-24100683` | 2020 | OCHA Philippines, NAMRIA | CC BY 3.0 IGO | `618b602a10daff2c9ae6310e1e1f68c148caf230edca857222c6c5aa015d0a29` |
| `SG` | Singapore | `SG_simplified.geojson` | `SGP-ADM0-21272760` | 2016 | Urban Redevelopment Authority | ODbL 1.0 | `ab19b8908053182bb17ebae6f7d944ea76445119ad13a5b36e011f4436288295` |
| `TH` | Thailand | `TH_simplified.geojson` | `THA-ADM0-76911100` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `16e8f650e4ffddd0f45b49c7357a0202bda271763940e3bb0c12a680a4510b38` |
| `TL` | Timor-Leste | `TL_simplified.geojson` | `TLS-ADM0-64751640` | 2017 | OpenStreetMap, Wambacher | ODbL 1.0 | `88cba3b9d28b4ebaf01f17394e10bf1a67b57f8cd4fc74abe9b9c9b2ed5528d9` |
| `VN` | Viet Nam | `VN_simplified.geojson` | `VNM-ADM0-46766057` | 2016 | geoBoundaries, Wikimedia Commons | CC BY 4.0 | `6d59ad13be1212956005f507fa2ed137b7d09b78320d3ae192e0fa412c530435` |

## Exact source links

Each country uses this metadata endpoint:

```text
https://www.geoboundaries.org/api/current/gbOpen/<ISO3>/ADM0/
```

The API response contains the exact `simplifiedGeometryGeoJSON` URL. The downloaded URLs and all API metadata are preserved in [`ASEAN_BOUNDARY_METADATA.json`](ASEAN_BOUNDARY_METADATA.json).

The current full candidate files remain separate. The legacy files below are byte-identical aliases of the recorded simplified files, so they inherit the same source, license, and provenance record:

- `ID.geojson`: byte-identical to `ID_simplified.geojson`; SHA-256 `adb38ba53ef172f63ffdc93da69827725cbd319c7b1d4b5c79ab08e5544b8fa3`;
- `VN.geojson`: byte-identical to `VN_simplified.geojson`; SHA-256 `6d59ad13be1212956005f507fa2ed137b7d09b78320d3ae192e0fa412c530435`.

For the Philippines record, the source dataset is [HDX Philippines administrative levels 0–3](https://data.humdata.org/dataset/philippines-administrative-levels-0-to-3). The canonical license text is [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/); the geoBoundaries API's `licenseSource` value is the malformed placeholder `Data https`, so this source/license separation is intentional and redistribution approval is still required.

Do not replace those files with simplified files without regenerating profile hashes, scale metadata, the registry database, and its signature.

A future production release must review boundary authority, resolution, legal scope, simplification, and license requirements before using any ASEAN file for operational filtering or profile certification.

## Full profile boundary inputs

Full ADM0 files are bundled for all 11 profile inputs. They remain candidate administrative boundaries and are not automatically legal or operational boundary certification.

| Domain | Full file | SHA-256 |
|---|---|---|
| `BN` | `BN_full.geojson` | `544e8a3b70531614f1fc0441d0a9ebf5777fe03fbfb1b9d8bc4fd07d81131bfa` |
| `KH` | `KH_full.geojson` | `a44140ae62a1dbe8d7cb176bc9b8afc38a65df66c05f84edba2b8b86a8fb4649` |
| `ID` | `ID_full.geojson` | `b2e253c47038aec319eb82b12e73e22e5562848688e676b399be6c59828c4a56` |
| `LA` | `LA_full.geojson` | `ba429d6121d6c193752bb3daaa1438a59fe339857fb168c258d23af2c5e0d0cd` |
| `MY` | `MY_full.geojson` | `20ffa28d8b7980060d43418a6a4a250ffdbcd805c514189accec9f799a181d77` |
| `MM` | `MM_full.geojson` | `5857a9a0d091b68c2b8e07fd9e8edb1fa0cd7e8b6cad87651dcd1419e4103874` |
| `PH` | `PH_full.geojson` | `7c3a7a39dacb5fb0c14d150061306fa5839455fbf93231854af3c6d74a1fa24f` |
| `SG` | `SG_full.geojson` | `d347c753ec38568609f9414da6b85ec46d2a776d1a3c99b9634822735a335c38` |
| `TH` | `TH_full.geojson` | `226eeef03694dc708201f142c992a819798841c0302c89e78cac8579b5058cde` |
| `TL` | `TL_full.geojson` | `8d8e1ce1f1f7452e4f27923c881e04c7b88402d8f1bdbab488f682160e70b3b6` |
| `VN` | `VN_full.geojson` | `2e82dbe0662f0f592902ef3e79011e438d63c7a356d43b3df0553b38866b501b` |

The exact full download URLs are in `ASEAN_BOUNDARY_METADATA.json`.
