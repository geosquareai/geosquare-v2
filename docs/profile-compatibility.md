# Profile compatibility: datasets written with geosquare-v2 1.0.0

**Status:** in force from the change that adds this file.

## What changed

All 11 domain profiles changed their `profile_version`:

| Release | Profile version | Datum operation |
|---|---|---|
| 1.0.0 | `2.1.0-static-datum` | none. PROJ chooses the WGS84 to grid operation. |
| 1.1.0 and later | `2.2.0-explicit-datum` | explicit operation from the registry. Each domain has an area of use. |

The CRS definition, origin, levels and boundary did not change.

Before this change, the reader accepted only the profile version in the trusted registry. A dataset written under `2.1.0-static-datum` was rejected.

## Rules now

1. Readers accept `2.1.0-static-datum` for the 11 domains. The mapping is in `_LEGACY_PROFILE_VERSIONS` in `src/geosquare_v2/cell_manifest.py`.
2. Writers refuse the legacy profile. `CellDataset.from_table` raises `ValidationError`.
3. Each manifest reports `profile_status`:
   - `current`: profile `2.2.0-explicit-datum`.
   - `legacy_same_gids`: legacy profile. GIDs match the current profile for this domain.
   - `legacy_gids_differ`: legacy profile. GIDs differ for some points in this domain. `CellDataset.read` warns.
4. Unknown profile versions are still rejected.

## Measurements

Method: the same seeded random points for each domain. 1.0.0 used `Transformer.from_crs(EPSG:4326, profile.crs_wkt2)`. The current code uses the explicit pipeline. PROJ 9.5.1 (the pinned version) on one machine.

| Domain | Projected positions | GIDs at level 12 that differ | GIDs at level 14 that differ | Points refused by the current code |
|---|---|---|---|---|
| BN, ID, KH, MM, MY, PH, SG, TH, TL | identical | 0 | 0 | 0 |
| VN | 2,876 of 20,000 moved (up to 227 m) | 2,095 | 2,215 | 2,086 of 20,000 (10.4%) |
| LA | 1,195 of 20,000 moved (up to 28 m) | 306 | 1,091 | 1,195 of 20,000 (6.0%) |

- The GID counts come from `gid_moved_all.py`. The refusal counts come from `validate_wgs84_point` on the same kind of sample, using each domain's box.
- A refused point is one that the 1.0.0 code could index. The current code refuses it because it is outside the datum operation's area of use.

## What this means

- Datasets from the nine unchanged domains load and their GIDs still match.
- VN and LA datasets from 1.0.0 load, and they are flagged. Their GIDs differ from current GIDs for some points. Do not join them with current VN or LA data.
- VN and LA points outside the area of use cannot be indexed by the current code. That is a write-side change, not a loading problem.

## Decision still open

Which VN and LA result is correct: the 1.0.0 PROJ choice, or the declared operation in 2.2.0? The CRS QA work chose the declared operation. Options for the old VN and LA datasets:

- keep them flagged and never join them with current data;
- rewrite them under profile 2.2.0 from their source data.

## Regression fixtures

`tests/fixtures/legacy_v1_0_0/<DOMAIN>/` holds one dataset per domain. Each was written with the 1.0.0 code. `points.json` keeps the sample points and their 1.0.0 GIDs. `tests/test_legacy_profile_read.py` checks them.
