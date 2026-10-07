"""Load the bundled candidate registry and index one WGS84 point.

Run from an installed checkout with::

    python -m pip install -e ".[registry]"
    python examples/quickstart.py

The trust file and registry resources are local candidate inputs. Production
applications must manage their trusted public keys independently.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from geosquare_v2 import DbRegistryLoader, GeosquareService


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    trust_values = json.loads((root / "release/registry-trust.json").read_text())
    trust = {
        key_id: base64.b64decode(value, validate=True)
        for key_id, value in trust_values.items()
    }

    boundary_root = root / "src/geosquare_v2/data/registry"
    registry = DbRegistryLoader(
        trust,
        root / "src/geosquare_v2/db",
        boundary_root=boundary_root,
        verify_boundaries=True,
    ).load()
    service = GeosquareService(registry, boundary_root=boundary_root)

    indexed = service.point_to_cell(
        "ID",
        longitude=106.8456,
        latitude=-6.2088,
        level=9,
    )

    print(f"URI: {indexed.uri}")
    print(f"GID: {indexed.gid}")
    print(f"Projected bounds: {indexed.projected_bounds}")
    print(f"Cell edge (m): {indexed.cell_edge_m}")
    print(f"Profile version: {indexed.profile_version}")
    print(f"Maximum scale error (%): {indexed.scale_error_max_pct}")


if __name__ == "__main__":
    main()
