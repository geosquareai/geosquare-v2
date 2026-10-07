"""Tests for explicit geometry-aware allocation and aggregation."""

from __future__ import annotations

import pandas as pd
import pytest
from shapely.geometry import box

from geosquare_v2 import (
    CategoryRule,
    CellDatasetError,
    DomainRegistry,
    GeosquareService,
    RangeRule,
    ValueSemantics,
    aggregate_geometry_contributions,
    aggregate_geometry_table_to_cells,
)
from geosquare_v2.errors import ValidationError


def _contributions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "domain": ["TS", "TS", "TS"],
            "level": [3, 3, 3],
            "gid": ["A", "A", "B"],
            "uri": ["geosquare:v2:TS:A"] * 2 + ["geosquare:v2:TS:B"],
            "coverage_ratio": [0.25, 0.75, 1.0],
            "length_ratio": [None, None, None],
            "assignment_method": ["polygon_to_cells"] * 3,
            "boundary_policy": [None] * 3,
            "source_id": ["source-1", "source-1", "source-2"],
            "total_value": [100.0, 100.0, 50.0],
            "density": [10.0, 20.0, 5.0],
            "numerator": [10.0, 20.0, 5.0],
            "denominator": [2.0, 4.0, 1.0],
            "category": ["forest", "urban", "forest"],
            "ordinal": ["low", "high", "medium"],
            "range_min": [1.0, 2.0, 5.0],
            "range_max": [3.0, 4.0, 8.0],
        }
    )


def _service(profile):
    return GeosquareService(DomainRegistry([profile]))


def _value(result, gid, column):
    return result.loc[result.gid == gid, column].iloc[0]


def test_total_allocates_by_area_ratio_and_records_provenance():
    result = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.TOTAL,
        value_column="total_value",
    )

    assert _value(result, "A", "total_value") == pytest.approx(100.0)
    assert _value(result, "B", "total_value") == pytest.approx(50.0)
    assert result.attrs["geosquare"] == {
        "value_semantics": "TOTAL",
        "allocation_rule": "ratio_weighted_sum",
        "source_value_column": "total_value",
        "stage": "geometry_contributions_to_cells",
    }


def test_density_and_measurement_use_ratio_weighted_means():
    density = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.DENSITY,
        value_column="density",
    )
    measurement = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.MEASUREMENT,
        value_column="density",
    )

    assert _value(density, "A", "density") == pytest.approx(17.5)
    assert _value(measurement, "A", "density") == pytest.approx(17.5)


def test_count_and_rate_have_explicit_paths():
    count = aggregate_geometry_contributions(_contributions(), value_semantics=ValueSemantics.COUNT)
    rate = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.RATE,
        numerator_column="numerator",
        denominator_column="denominator",
    )

    assert _value(count, "A", "count") == 2
    assert _value(rate, "A", "rate") == pytest.approx(5.0)
    assert rate.attrs["geosquare"]["source_value_column"] == "numerator/denominator"


def test_categorical_ordinal_and_range_use_existing_explicit_rules():
    categorical = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.CATEGORICAL,
        value_column="category",
        category_rule=CategoryRule.MAJORITY_WEIGHTED,
    )
    ordinal = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.ORDINAL,
        value_column="ordinal",
        priority_order=["low", "medium", "high"],
    )
    ranges = aggregate_geometry_contributions(
        _contributions(),
        value_semantics=ValueSemantics.RANGE,
        lower_column="range_min",
        upper_column="range_max",
        range_rule=RangeRule.FULL_RANGE,
    )

    assert _value(categorical, "A", "category") == "urban"
    assert _value(ordinal, "A", "ordinal") == "low"
    assert _value(ranges, "A", "range_min") == pytest.approx(1.0)
    assert _value(ranges, "A", "range_max") == pytest.approx(4.0)


def test_high_level_geometry_pipeline_converts_then_aggregates(profile):
    source = pd.DataFrame(
        {
            "asset_id": ["parcel-1"],
            "population": [100.0],
            "geometry": [box(0, 0, 2_000_000, 1_000_000)],
        }
    )
    result = aggregate_geometry_table_to_cells(
        source,
        _service(profile),
        "TS",
        3,
        value_semantics=ValueSemantics.TOTAL,
        value_column="population",
        geometry_options={
            "geometry_column": "geometry",
            "source_id_column": "asset_id",
            "source_crs": profile.crs_wkt2,
            "keep_columns": ["population"],
        },
    )

    assert result["population"].sum() == pytest.approx(100.0)
    assert result.attrs["geosquare"]["stage"] == "geometry_table_to_cells_to_aggregate"


def test_invalid_semantics_and_contribution_rules_are_rejected():
    frame = _contributions()
    with pytest.raises(ValidationError, match="unknown value semantics"):
        aggregate_geometry_contributions(frame, value_semantics="UNKNOWN", value_column="density")
    with pytest.raises(ValidationError, match="must not contain both"):
        aggregate_geometry_contributions(
            frame.assign(length_ratio=[0.1, None, None]),
            value_semantics=ValueSemantics.TOTAL,
            value_column="total_value",
        )
    with pytest.raises(ValidationError, match="supplied together"):
        aggregate_geometry_contributions(
            frame,
            value_semantics=ValueSemantics.RATE,
            numerator_column="numerator",
        )
    with pytest.raises(ValidationError, match="denominator"):
        aggregate_geometry_contributions(
            frame.assign(denominator=[0.0, 0.0, 0.0]),
            value_semantics=ValueSemantics.RATE,
            numerator_column="numerator",
            denominator_column="denominator",
        )
