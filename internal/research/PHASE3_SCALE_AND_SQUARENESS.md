# Phase 3 scale and squareness benchmark

This benchmark uses full ASEAN boundaries, deterministic boundary densification, and seeded interior sampling. It is a candidate-profile measurement, not geodetic or boundary approval.

- Run ID: `phase3-20261007T230644.096271Z`
- Repository commit: `2120f1fd6d9412b6cb59ce883d87964a5e7b5ffb`
- Level: `12` (nominal 50 m)
- Interior points per domain: `2048`
- Base seed: `20260301`; domain seed is base plus the 1-based ASEAN ordinal

| Domain | Boundary points | Interior points | Unique cells | Side error max | Area ratio p05–p95 | Max area error | Approval status |
|---|---:|---:|---:|---:|---:|---:|---|
| `BN` | 758 | 2048 | 2799 | 0.000007% | 0.999973–1.000037 | 0.0046% | review-required |
| `KH` | 11512 | 2048 | 13493 | 0.000033% | 0.999359–1.000763 | 0.0962% | review-required |
| `ID` | 21019 | 2048 | 21721 | 0.000116% | 0.995486–1.009626 | 1.2002% | datum-review |
| `LA` | 18173 | 2048 | 19914 | 0.000059% | 0.997460–1.002483 | 0.3132% | review-required |
| `MY` | 17203 | 2048 | 18770 | 0.000045% | 0.998495–1.001419 | 0.1780% | component-and-datum-review |
| `MM` | 19508 | 2048 | 21170 | 0.000133% | 0.988550–1.012032 | 1.5277% | datum-and-boundary-review |
| `PH` | 22709 | 2048 | 21641 | 0.000115% | 0.991892–1.009215 | 1.1620% | datum-and-island-review |
| `SG` | 8070 | 2048 | 6691 | 0.000003% | 0.999984–1.000000 | 0.0018% | review-required |
| `TH` | 18869 | 2048 | 20476 | 0.000103% | 0.991951–1.007438 | 0.9365% | datum-and-boundary-review |
| `TL` | 15104 | 2048 | 12441 | 0.000009% | 0.999949–1.000063 | 0.0080% | review-required |
| `VN` | 4449 | 2048 | 6407 | 0.000103% | 0.993199–1.007548 | 0.9764% | datum-review |

Side error is `(longest geodesic edge / shortest geodesic edge - 1) × 100` over unique Level-12 cells reached by the combined point set.
Area ratio is geodesic ground area divided by the nominal 50 m × 50 m grid area.
The profile's published candidate scale error is retained separately from geodesic cell side anisotropy.

Detailed JSON: [`release/scale/phase3/ASEAN_LEVEL12_BENCHMARK.json`](../../release/scale/phase3/ASEAN_LEVEL12_BENCHMARK.json)
Run manifest: [`release/scale/phase3/PHASE3_RUN_MANIFEST.json`](../../release/scale/phase3/PHASE3_RUN_MANIFEST.json)
