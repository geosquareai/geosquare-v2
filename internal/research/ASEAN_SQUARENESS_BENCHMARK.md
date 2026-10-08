# ASEAN GeoSquare squareness benchmark

Level 12 is the nominal 50 m cell. Results use sampled boundary points and the selected candidate CRS for each country.

| Domain | Candidate | Boundary | Side error max | Ground side p05–p95 | Area ratio p05–p95 | Scale error | Band |
|---|---|---|---:|---:|---:|---:|---|
| `BN` | `LCC` | simplified | 0.0000% | 50.00–50.00 m | 1.0000–1.0000 | 0.0023% | preferred |
| `KH` | `LCC` | simplified | 0.0000% | 49.98–50.02 m | 0.9993–1.0008 | 0.0481% | preferred |
| `ID` | `lcc_fraction_1_6` | full | 0.0001% | 49.88–50.24 m | 0.9952–1.0096 | 0.6071% | preferred |
| `LA` | `LCC` | simplified | 0.0001% | 49.94–50.06 m | 0.9974–1.0025 | 0.1569% | preferred |
| `MY` | `lcc_fraction_1_6` | full | 0.0000% | 49.96–50.04 m | 0.9985–1.0014 | 0.0891% | preferred |
| `MM` | `lcc_fraction_1_6` | full | 0.0001% | 49.70–50.30 m | 0.9881–1.0120 | 0.7727% | preferred |
| `PH` | `lcc_fraction_1_6` | full | 0.0001% | 49.82–50.23 m | 0.9929–1.0092 | 0.5861% | preferred |
| `SG` | `LOCAL_PROJECTED` | simplified | 0.0000% | 50.00–50.00 m | 1.0000–1.0000 | 0.0009% | preferred |
| `TH` | `lcc_fraction_1_6` | full | 0.0001% | 49.80–50.19 m | 0.9918–1.0074 | 0.4715% | preferred |
| `TL` | `LCC` | simplified | 0.0000% | 50.00–50.00 m | 0.9999–1.0001 | 0.0040% | preferred |
| `VN` | `existing_profile` | full | 0.0001% | 49.82–50.19 m | 0.9929–1.0076 | 0.4922% | preferred |

Side error is `(longest side / shortest side - 1) × 100`.
Area ratio is geodesic ground area divided by the nominal 50 m × 50 m grid area.
These are candidate measurements, not final profile approval.

Detailed JSON: [`../../release/scale/ASEAN_SQUARENESS_BENCHMARK.json`](../../release/scale/ASEAN_SQUARENESS_BENCHMARK.json)
