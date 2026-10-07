from __future__ import annotations

import numpy as np
import pandas as pd
import pyarrow as pa
from pyproj import CRS, Transformer

from geosquare_v2.batch import (
    encode_lonlat_arrow,
    encode_lonlat_numpy,
    encode_lonlat_pandas,
    encode_projected_arrow,
    encode_projected_numpy,
    encode_projected_pandas,
)


def test_numpy_projected_encoding_matches_scalar_including_root_edges(grid):
    root = grid.profile.root_bounds
    x = np.array([root.min_x, 0.0, root.max_x])
    y = np.array([root.min_y, 0.0, root.max_y])
    result = encode_projected_numpy(grid, x, y, 4)

    for row, (x_m, y_m) in enumerate(zip(x, y)):
        cell = grid.canonical_from_projected(float(x_m), float(y_m), 4)
        assert int(result.x_idx[row]) == cell.x_idx
        assert int(result.y_idx[row]) == cell.y_idx
        assert result.gid[row] == grid.gid_from_canonical(cell)
        assert int(result.packed_id[row]) == grid.pack(cell)


def test_numpy_lonlat_encoding_matches_scalar(grid, profile):
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(profile.crs_wkt2), always_xy=True)
    result = encode_lonlat_numpy(grid, np.array([0.0]), np.array([0.0]), 4)
    cell = grid.canonical_from_lonlat(0.0, 0.0, 4, transformer)

    assert int(result.x_idx[0]) == cell.x_idx
    assert int(result.y_idx[0]) == cell.y_idx
    assert result.gid[0] == grid.gid_from_canonical(cell)


def test_pandas_and_arrow_adapters_match_numpy(grid):
    frame = pd.DataFrame({"x": [-1.0, 1.0], "y": [-1.0, 1.0]})
    pandas_result = encode_projected_pandas(grid, frame, "x", "y", 4)
    arrow_result = encode_projected_arrow(grid, pa.table(frame), "x", "y", 4).to_pandas()

    expected = encode_projected_numpy(grid, frame["x"].to_numpy(), frame["y"].to_numpy(), 4)
    assert pandas_result["gid"].tolist() == expected.gid.tolist()
    assert arrow_result["gid"].tolist() == expected.gid.tolist()
    assert pandas_result["packed_id"].tolist() == expected.packed_id.tolist()
    assert arrow_result["packed_id"].tolist() == expected.packed_id.tolist()


def test_pandas_and_arrow_lonlat_adapters_match_numpy(grid):
    frame = pd.DataFrame({"longitude": [0.0], "latitude": [0.0]})
    pandas_result = encode_lonlat_pandas(grid, frame, "longitude", "latitude", 4)
    arrow_result = encode_lonlat_arrow(grid, pa.table(frame), "longitude", "latitude", 4).to_pandas()
    expected = encode_lonlat_numpy(grid, frame["longitude"].to_numpy(), frame["latitude"].to_numpy(), 4)

    assert pandas_result["gid"].tolist() == expected.gid.tolist()
    assert arrow_result["gid"].tolist() == expected.gid.tolist()
    assert pandas_result["packed_id"].tolist() == expected.packed_id.tolist()
    assert arrow_result["packed_id"].tolist() == expected.packed_id.tolist()
