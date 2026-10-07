from __future__ import annotations

import pandas as pd

from geosquare_v2.aggregation import (
    CategoryRule,
    NumericRule,
    RangeRule,
    aggregate_categorical,
    aggregate_numeric,
    aggregate_range,
)
from geosquare_v2.facade import GeosquareService
from geosquare_v2.registry import DomainRegistry
from geosquare_v2.table import read_table, table_to_cells, write_table


def _service(profile):
    return GeosquareService(DomainRegistry([profile]))


def test_csv_table_to_cells_preserves_selected_columns(tmp_path, profile):
    source = tmp_path / "points.csv"
    pd.DataFrame(
        {
            "asset_id": ["a", "b"],
            "longitude": [0.0, 0.0],
            "latitude": [0.0, 0.0],
            "value": [10, 20],
        }
    ).to_csv(source, index=False)

    frame = table_to_cells(
        source,
        _service(profile),
        "TS",
        9,
        keep_columns=["asset_id", "value", "longitude", "latitude"],
    )

    assert frame["asset_id"].tolist() == ["a", "b"]
    assert frame["value"].tolist() == [10, 20]
    assert {"gid", "uri", "x_idx", "y_idx", "packed_id"} <= set(frame.columns)


def test_table_read_and_write_round_trip_csv(tmp_path):
    source = tmp_path / "input.csv"
    destination = tmp_path / "output.csv"
    original = pd.DataFrame({"id": [1, 2], "value": [3.0, 4.0]})
    original.to_csv(source, index=False)

    loaded = read_table(source)
    write_table(loaded, destination)
    round_trip = read_table(destination)

    assert round_trip.to_dict(orient="list") == original.to_dict(orient="list")


def test_numeric_aggregation_supports_weighted_mean_and_sum():
    frame = pd.DataFrame(
        {
            "domain": ["TS"] * 3,
            "level": [3] * 3,
            "gid": ["A", "A", "B"],
            "value": [10.0, 20.0, 5.0],
            "coverage_ratio": [0.25, 0.75, 1.0],
        }
    )

    mean = aggregate_numeric(
        frame,
        "value",
        rule=NumericRule.WEIGHTED_MEAN,
        weight_column="coverage_ratio",
    )
    total = aggregate_numeric(
        frame,
        "value",
        rule=NumericRule.WEIGHTED_SUM,
        weight_column="coverage_ratio",
    )

    assert mean.loc[mean.gid == "A", "value"].iloc[0] == 17.5
    assert total.loc[total.gid == "A", "value"].iloc[0] == 17.5


def test_categorical_and_range_aggregation_are_explicit():
    frame = pd.DataFrame(
        {
            "gid": ["A", "A", "B"],
            "category": ["forest", "urban", "forest"],
            "weight": [0.25, 0.75, 1.0],
            "low": [1.0, 2.0, 5.0],
            "high": [3.0, 4.0, 8.0],
        }
    )

    categories = aggregate_categorical(
        frame,
        "category",
        rule=CategoryRule.LARGEST_OVERLAP,
        weight_column="weight",
    )
    ranges = aggregate_range(frame, "low", "high", rule=RangeRule.FULL_RANGE)

    assert categories.loc[categories.gid == "A", "category"].iloc[0] == "urban"
    assert ranges.loc[ranges.gid == "A", "range_min"].iloc[0] == 1.0
    assert ranges.loc[ranges.gid == "A", "range_max"].iloc[0] == 4.0
