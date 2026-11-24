# Quick start

This page runs the main calls in order. Each code block runs as written. The output shown came from a real run.

**Needs a git clone.** The PyPI package does not include the trust file in `release/` or the registry files in `src/`. A PyPI-only install can do step 1. Steps 2 to 7 fail with `FileNotFoundError` unless you run them from a clone of this repo, from its root.

## 1. Install

From PyPI, for the package only:

```zsh
python -m pip install "geosquare-v2[registry,geo,table]"
```

From a git clone, which steps 2 to 7 need:

```zsh
python -m pip install -e ".[registry,geo,table]"
```

- `registry` loads the signed registry.
- `geo` adds Shapely for polygons.
- `table` adds Pandas for tables.

Python 3.11 or newer is required.

## 2. Load the registry

Every run starts here. The loader checks the signature and the boundary files before it returns.

```python
import base64
import json
from pathlib import Path

from geosquare_v2 import DbRegistryLoader, GeosquareService

root = Path(".")
keys = json.loads((root / "release/registry-trust.json").read_text())
trust = {key_id: base64.b64decode(value, validate=True) for key_id, value in keys.items()}
boundary_root = root / "src/geosquare_v2/data/registry"

registry = DbRegistryLoader(
    trust,
    root / "src/geosquare_v2/db",
    boundary_root=boundary_root,
    verify_boundaries=True,
).load()
service = GeosquareService(registry, boundary_root=boundary_root, allow_candidate_crs=True)
```

The flag lets candidate domains (`KH`, `MM`, `TH`, `TL`, `VN`) run. Without it, those domains raise `ValidationError`. `ID` is a released domain. The trust file in `release/` is an example. Production code must manage its own trusted public keys.

## 3. Encode a point to a cell

```python
cell = service.point_to_cell("ID", longitude=106.8456, latitude=-6.2088, level=9)
print(cell.uri)
print(cell.gid)
```

Output:

```text
geosquare:v2:ID:H2X545V39
H2X545V39
```

Store the `uri` in your data. It keeps the domain and the profile version.

## 4. Decode a cell

Pass a full URI, or a bare GID with `domain_code`:

```python
from_uri = service.describe("geosquare:v2:ID:H2X545V39")
from_gid = service.describe("H2X545V39", domain_code="ID")
print(from_uri.uri)
print(from_gid.cell_edge_m)
```

Output:

```text
geosquare:v2:ID:H2X545V39
1000.0
```

## 5. Polygon to cells

Pass a Shapely polygon, its CRS, and the level. The call returns one record for each cell that the polygon covers.

```python
from shapely.geometry import Polygon

polygon = Polygon([
    (106.82, -6.20),
    (106.86, -6.20),
    (106.86, -6.17),
    (106.82, -6.17),
    (106.82, -6.20),
])
records = service.polygon_to_cells("ID", polygon, "EPSG:4326", 9)
print(len(records))
print(records[0].uri, round(records[0].coverage_ratio, 3))
```

Output:

```text
25
geosquare:v2:ID:H2X545V2L 0.154
```

`coverage_ratio` is the share of the cell that falls inside the polygon.

## 6. Aggregate a table

Give each row a `gid`, then pick a rule for each value column. This example adds up people counts per cell, so `value_semantics` is `TOTAL`.

```python
import pandas as pd

frame = pd.DataFrame({
    "gid": [from_gid.gid, from_gid.gid, from_gid.gid],
    "population": [10, 5, 7],
})
totals = service.aggregate_to_cells(
    frame,
    value_type="numeric",
    value_column="population",
    rule="sum",
    value_semantics="TOTAL",
)
print(totals)
```

Output:

```text
         gid  population  feature_count
0  H2X545V39        22.0              3
```

The rules are in [data and aggregation](data-and-aggregation.md). Pick the rule for each value. Do not assume a default.

## 7. Read a dataset written by 1.0.0

Datasets written by geosquare-v2 1.0.0 use profile `2.1.0-static-datum`. The reader still loads them. The test fixture in this repo is one example.

```python
from geosquare_v2 import read_cell_dataset

legacy = read_cell_dataset("tests/fixtures/legacy_v1_0_0/ID", registry=registry)
print(legacy.manifest.profile_status)
```

Output:

```text
legacy_same_gids
```

`profile_status` tells you what happened:

- `current`: the dataset uses the current profile.
- `legacy_same_gids`: the legacy profile, and its GIDs match the current profile for this domain.
- `legacy_gids_differ`: the legacy profile, and some GIDs differ. The reader warns.

For LA and VN, the status is `legacy_gids_differ`. See [profile compatibility](profile-compatibility.md).

## Next steps

- [Concepts](concepts.md): the grid model.
- [API guide](api.md): boundary policies, low-level grid calls and the full API.
- [Data and aggregation](data-and-aggregation.md): value rules.
- [Runnable quickstart script](../examples/quickstart.py): the same registry setup as one file.
