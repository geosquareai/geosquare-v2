# ASEAN Coverage and Projection Plan

**Status:** candidate plan, not a production release
**Date:** 2026-09-18
**Technical contract:** [PRODUCT_CONTRACT_V2.md](../architecture/PRODUCT_CONTRACT_V2.md)

## 1. Scope

This plan covers the 11 current ASEAN member states:

- Brunei Darussalam;
- Cambodia;
- Indonesia;
- Lao PDR;
- Malaysia;
- Myanmar;
- Philippines;
- Singapore;
- Thailand;
- Timor-Leste; and
- Viet Nam.

The simplified boundaries are stored for candidate work and visual checks. They are not yet approved as final operational boundaries.

## 2. Common V2 rules

Every ASEAN domain uses the same V2 identity rules:

- canonical identity: `(domain_code, level, x_idx, y_idx)`;
- root side: 50,000 km;
- levels: 0–14;
- level 12: 50 m in the grid CRS;
- level 14: 5 m in the grid CRS;
- geometry: exact square in the grid CRS;
- area coverage: `GRID_PLANAR` or `EQUAL_AREA`;
- point boundary rule: `COVERS_POINT`;
- general cell rule: `INTERSECTS`;
- official/statistical rule: `MIN_COVERAGE` with an explicit threshold.

Boundary filtering is separate from cell identity. The same cell ID must not change because an application chose a different boundary policy.

## 3. Projection approach

A country does not automatically get a global CRS or a separate root for every local zone.

The first candidate approach is:

- use the existing reviewed profile for Indonesia;
- use the existing reviewed profile for Viet Nam;
- use a country-wide Lambert Conformal Conic candidate for compact mainland countries;
- use an Equidistant Cylindrical or other broad-area candidate for wide archipelagos;
- use a local small-area projected candidate for Singapore; and
- keep all candidates under one country namespace until distortion testing proves that this is not acceptable.

These are starting choices. They are not release approvals.

| Domain | Country | First candidate family | Main risk to test |
|---|---|---|---|
| `BN` | Brunei Darussalam | LCC | Small-area datum and border detail |
| `KH` | Cambodia | LCC | National scale error and boundary source |
| `ID` | Indonesia | Existing SRGI2013-based EQC | Wide archipelago and island components |
| `LA` | Lao PDR | LCC | North-south scale variation |
| `MY` | Malaysia | Country-wide LCC | Separate Peninsular and Borneo components |
| `MM` | Myanmar | LCC | Long north-south extent and source quality |
| `PH` | Philippines | EQC or broad LCC | Large archipelago and island coverage |
| `SG` | Singapore | Local projected CRS | Very small area and boundary precision |
| `TH` | Thailand | LCC | North-south scale variation |
| `TL` | Timor-Leste | LCC | Island geometry and source resolution |
| `VN` | Viet Nam | Existing VN-2000 LCC | Long north-south extent |

## 4. Equal-area coverage

`EPSG:8857` Equal Earth is the current V2 candidate for equal-area calculations.

Before a country becomes a release profile, compare it with a local equal-area option where needed. Coastal and statistical results must use `EQUAL_AREA` unless the user explicitly asks for grid-planar coverage.

## 5. Profile acceptance checks

A country profile is not ready for the signed registry until it passes all of these checks:

1. Every included boundary component transforms inside the 50,000 km root.
2. The boundary is checked with densified edges, not only existing vertices.
3. Interior points are sampled for projection distortion.
4. The maximum directional scale error is published.
5. The root empty-area ratio is recorded.
6. Antimeridian behavior is tested where relevant.
7. Island and detached-component policy is recorded.
8. The boundary source, license, version, and SHA-256 are recorded.
9. The profile CRS and equal-area CRS parse in the pinned PROJ version.
10. The profile gets a new signed registry release.

## 6. Simplified versus final boundary

The `_simplified.geojson` files are useful for:

- early projection selection;
- quick maps;
- candidate root checks; and
- development fixtures.

They are not enough by themselves for final legal or statistical use.

A production profile should use a reviewed boundary with enough detail for the intended operation. Simplification can remove islands, narrow corridors, small border details, or coastal features.

## 7. First-pass results

The evaluator used the simplified boundaries, a densified sample capped at 10,000 points per country, and one candidate CRS per country.

| Domain | Candidate max sampled scale error | Root covers sampled boundary | Result |
|---|---:|---|---|
| `BN` | 0.0023% | yes | promising candidate |
| `KH` | 0.0481% | yes | promising candidate |
| `ID` | 1.8738% | yes | keep existing profile; publish the error |
| `LA` | 0.1569% | yes | promising candidate |
| `MY` | 0.0893% | yes | promising, but test Peninsular/Borneo components separately |
| `MM` | 0.7717% | yes | needs closer review |
| `PH` | 7.2022% | yes | reject this first EQC candidate; test another projection |
| `SG` | 0.0009% | yes | promising, but boundary detail matters |
| `TH` | 0.4716% | yes | needs closer review |
| `TL` | 0.0040% | yes | promising candidate |
| `VN` | 0.4922% | yes | keep existing profile; publish the error |

These numbers are planning results. They are not final guarantees. The Philippines result shows why each country needs a projection review instead of one global CRS choice.

The full WKT, candidate parameters, sample counts, boundary hashes, and worst-point coordinates are in [`scale/ASEAN_PROJECTION_CANDIDATES.json`](../../release/scale/ASEAN_PROJECTION_CANDIDATES.json).

## 8. Current status

The 11 full boundary files and their source metadata are now stored in the repository.

The signed candidate registry now contains all 11 ASEAN domains. They remain candidate profiles until datum, boundary, epoch, and production approval checks pass.

The next step is production approval and release authorization for the generated 11-domain registry.

## Six-country profile review

Full boundary candidates were added for `ID`, `MY`, `MM`, `PH`, `TH`, and `VN`.

The alternative projection review is in [`ASEAN_PRIORITY_PROFILE_REVIEW.md`](ASEAN_PRIORITY_PROFILE_REVIEW.md). It uses the full candidates, densified boundary samples, and a small interior sample.

First-pass recommendations:

- `ID`: test the LCC 1/6 candidate. It is about 0.61% in the first pass, better than the existing EQC candidate at about 1.87%. Review the datum choice before approval.
- `PH`: use the LCC 1/6 candidate for the next review. The first EQC candidate is rejected.
- `VN`: keep the existing VN-2000 LCC candidate unless a datum-correct alternative clearly improves it.
- `MM`: use LCC 1/6 as the next candidate. The centered EQC candidate is rejected.
- `TH`: use LCC 1/6 as the next candidate.
- `MY`: use LCC 1/6 as the next candidate, but review Peninsular and Borneo components separately.

These are not signed profiles yet. Before approval, review official datum, boundary authority, component policy, interior distortion, and application accuracy requirements.
