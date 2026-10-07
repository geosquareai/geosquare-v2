"""Explicit value aggregation over already-assigned V2 cell rows."""

from __future__ import annotations

from enum import Enum
import math
from typing import Any, Iterable

from .errors import TableDependencyError, ValidationError


class ValueSemantics(str, Enum):
    COUNT = "COUNT"
    TOTAL = "TOTAL"
    DENSITY = "DENSITY"
    MEASUREMENT = "MEASUREMENT"
    RATE = "RATE"
    ORDINAL = "ORDINAL"
    CATEGORICAL = "CATEGORICAL"
    RANGE = "RANGE"


class NumericRule(str, Enum):
    COUNT = "count"
    SUM = "sum"
    WEIGHTED_SUM = "weighted_sum"
    MEAN = "mean"
    WEIGHTED_MEAN = "weighted_mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    STD = "std"
    QUANTILE = "quantile"


class CategoryRule(str, Enum):
    LARGEST_OVERLAP = "largest_overlap"
    MAJORITY_WEIGHTED = "majority_weighted"
    CENTROID_CATEGORY = "centroid_category"
    PRIORITY_ORDER = "priority_order"
    ALL_CATEGORIES = "all_categories"


class RangeRule(str, Enum):
    WEIGHTED_MEAN = "weighted_mean"
    MIN = "min"
    MAX = "max"
    FULL_RANGE = "full_range"
    DISTRIBUTION = "distribution"


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - exercised without table extra
        raise TableDependencyError(
            "aggregation requires the 'table' optional dependency group"
        ) from exc
    return pd


def _as_enum(value: Any, enum_type: Any, name: str) -> Any:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except ValueError as exc:
        raise ValidationError(f"unknown {name}: {value!r}") from exc


def _group_columns(frame: Any, cell_column: str) -> list[str]:
    preferred = ["domain", "level", "x_idx", "y_idx", cell_column, "uri"]
    columns = [column for column in preferred if column in frame.columns]
    if cell_column not in columns:
        columns.append(cell_column)
    if not columns:
        raise ValidationError("a cell column is required")
    return list(dict.fromkeys(columns))


def _validate_columns(frame: Any, columns: Iterable[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValidationError(f"missing table columns: {missing}")


def _weights(group: Any, weight_column: str | None) -> list[float]:
    if weight_column is None:
        return [1.0] * len(group)
    values = group[weight_column].astype(float).tolist()
    if any(value < 0 for value in values):
        raise ValidationError("weights must be non-negative")
    if not any(value > 0 for value in values):
        raise ValidationError("weights must contain at least one positive value")
    return values


def _weighted_median(values: list[float], weights: list[float]) -> float:
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    midpoint = sum(weights) / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= midpoint:
            return value
    return ordered[-1][0]


def _weighted_quantile(values: list[float], weights: list[float], quantile: float) -> float:
    if not 0 <= quantile <= 1:
        raise ValidationError("quantile must be in [0, 1]")
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    target = sum(weights) * quantile
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return value
    return ordered[-1][0]


def _base_result(group_columns: list[str], key: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(group_columns, key))


def aggregate_numeric(
    frame: Any,
    value_column: str,
    *,
    cell_column: str = "gid",
    rule: NumericRule | str = NumericRule.MEAN,
    weight_column: str | None = None,
    value_semantics: ValueSemantics | str = ValueSemantics.MEASUREMENT,
    quantile: float = 0.5,
    output_column: str | None = None,
) -> Any:
    """Aggregate one numeric column per cell with an explicit rule."""
    pd = _require_pandas()
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    _validate_columns(frame, [value_column] + ([weight_column] if weight_column else []))
    selected_rule = _as_enum(rule, NumericRule, "numeric rule")
    _as_enum(value_semantics, ValueSemantics, "value semantics")
    group_columns = _group_columns(frame, cell_column)
    output_name = output_column or value_column
    rows: list[dict[str, Any]] = []

    for key, group in frame.groupby(group_columns, dropna=False, sort=False):
        if not isinstance(key, tuple):
            key = (key,)
        values = group[value_column].astype(float).tolist()
        weights = _weights(group, weight_column)
        weighted_total = sum(value * weight for value, weight in zip(values, weights))
        total_weight = sum(weights)
        if selected_rule is NumericRule.COUNT:
            result = len(values)
        elif selected_rule is NumericRule.SUM:
            result = sum(values)
        elif selected_rule is NumericRule.WEIGHTED_SUM:
            result = weighted_total
        elif selected_rule is NumericRule.MEAN:
            result = sum(values) / len(values)
        elif selected_rule is NumericRule.WEIGHTED_MEAN:
            result = weighted_total / total_weight
        elif selected_rule is NumericRule.MEDIAN:
            result = _weighted_median(values, weights) if weight_column else float(pd.Series(values).median())
        elif selected_rule is NumericRule.MIN:
            result = min(values)
        elif selected_rule is NumericRule.MAX:
            result = max(values)
        elif selected_rule is NumericRule.STD:
            result = float(pd.Series(values).std(ddof=0))
        else:
            result = _weighted_quantile(values, weights, quantile) if weight_column else float(pd.Series(values).quantile(quantile))
        row = _base_result(group_columns, key)
        row[output_name] = result
        row["feature_count"] = len(values)
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_categorical(
    frame: Any,
    category_column: str,
    *,
    cell_column: str = "gid",
    rule: CategoryRule | str = CategoryRule.MAJORITY_WEIGHTED,
    weight_column: str | None = None,
    priority_order: Iterable[Any] | None = None,
    output_column: str | None = None,
) -> Any:
    """Aggregate categories using overlap, count, priority, or full distribution."""
    pd = _require_pandas()
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    _validate_columns(frame, [category_column] + ([weight_column] if weight_column else []))
    selected_rule = _as_enum(rule, CategoryRule, "category rule")
    group_columns = _group_columns(frame, cell_column)
    output_name = output_column or category_column
    priority = list(priority_order or [])
    rows: list[dict[str, Any]] = []

    for key, group in frame.groupby(group_columns, dropna=False, sort=False):
        if not isinstance(key, tuple):
            key = (key,)
        weights = _weights(group, weight_column)
        scores: dict[Any, float] = {}
        counts: dict[Any, int] = {}
        for category, weight in zip(group[category_column].tolist(), weights):
            scores[category] = scores.get(category, 0.0) + weight
            counts[category] = counts.get(category, 0) + 1
        if selected_rule is CategoryRule.ALL_CATEGORIES:
            total = sum(scores.values())
            result: Any = {str(category): score / total for category, score in scores.items()}
        elif selected_rule is CategoryRule.CENTROID_CATEGORY:
            result = max(counts, key=lambda category: (counts[category], str(category)))
        elif selected_rule is CategoryRule.PRIORITY_ORDER:
            rank = {category: index for index, category in enumerate(priority)}
            result = min(
                scores,
                key=lambda category: (rank.get(category, len(rank)), -scores[category], str(category)),
            )
        else:
            result = max(scores, key=lambda category: (scores[category], str(category)))
        row = _base_result(group_columns, key)
        row[output_name] = result
        row["feature_count"] = len(group)
        if selected_rule is not CategoryRule.ALL_CATEGORIES:
            winning_score = scores[result]
            row["category_share"] = winning_score / sum(scores.values())
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_range(
    frame: Any,
    lower_column: str,
    upper_column: str,
    *,
    cell_column: str = "gid",
    rule: RangeRule | str = RangeRule.FULL_RANGE,
    weight_column: str | None = None,
    output_prefix: str = "range",
) -> Any:
    """Aggregate numeric ranges without silently treating them as ordinary values."""
    pd = _require_pandas()
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    _validate_columns(frame, [lower_column, upper_column] + ([weight_column] if weight_column else []))
    selected_rule = _as_enum(rule, RangeRule, "range rule")
    group_columns = _group_columns(frame, cell_column)
    rows: list[dict[str, Any]] = []

    for key, group in frame.groupby(group_columns, dropna=False, sort=False):
        if not isinstance(key, tuple):
            key = (key,)
        lowers = group[lower_column].astype(float).tolist()
        uppers = group[upper_column].astype(float).tolist()
        if any(lower > upper for lower, upper in zip(lowers, uppers)):
            raise ValidationError("range lower values must not exceed upper values")
        weights = _weights(group, weight_column)
        centers = [(lower + upper) / 2 for lower, upper in zip(lowers, uppers)]
        row = _base_result(group_columns, key)
        if selected_rule is RangeRule.MIN:
            row[f"{output_prefix}_min"] = min(lowers)
            row[f"{output_prefix}_max"] = min(uppers)
        elif selected_rule is RangeRule.MAX:
            row[f"{output_prefix}_min"] = max(lowers)
            row[f"{output_prefix}_max"] = max(uppers)
        elif selected_rule is RangeRule.WEIGHTED_MEAN:
            total_weight = sum(weights)
            center = sum(value * weight for value, weight in zip(centers, weights)) / total_weight
            row[f"{output_prefix}_value"] = center
        elif selected_rule is RangeRule.DISTRIBUTION:
            row[f"{output_prefix}_distribution"] = [
                {"min": lower, "max": upper, "weight": weight}
                for lower, upper, weight in zip(lowers, uppers, weights)
            ]
        else:
            row[f"{output_prefix}_min"] = min(lowers)
            row[f"{output_prefix}_max"] = max(uppers)
        row["feature_count"] = len(group)
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_ordinal(
    frame: Any,
    value_column: str,
    *,
    cell_column: str = "gid",
    priority_order: Iterable[Any],
    weight_column: str | None = None,
    output_column: str | None = None,
) -> Any:
    """Aggregate ordinal categories with an explicit priority order."""
    return aggregate_categorical(
        frame,
        value_column,
        cell_column=cell_column,
        rule=CategoryRule.PRIORITY_ORDER,
        weight_column=weight_column,
        priority_order=priority_order,
        output_column=output_column,
    )


def aggregate_to_cells(
    frame: Any,
    *,
    value_type: str = "numeric",
    value_column: str | None = None,
    lower_column: str | None = None,
    upper_column: str | None = None,
    cell_column: str = "gid",
    rule: str | Enum | None = None,
    weight_column: str | None = None,
    value_semantics: ValueSemantics | str = ValueSemantics.MEASUREMENT,
    priority_order: Iterable[Any] | None = None,
    quantile: float = 0.5,
) -> Any:
    """Dispatch to the explicit numeric, category, ordinal, or range aggregator."""
    if value_type == "numeric":
        if value_column is None:
            raise ValidationError("value_column is required for numeric aggregation")
        return aggregate_numeric(
            frame,
            value_column,
            cell_column=cell_column,
            rule=rule or NumericRule.MEAN,
            weight_column=weight_column,
            value_semantics=value_semantics,
            quantile=quantile,
        )
    if value_type == "categorical":
        if value_column is None:
            raise ValidationError("value_column is required for categorical aggregation")
        return aggregate_categorical(
            frame,
            value_column,
            cell_column=cell_column,
            rule=rule or CategoryRule.MAJORITY_WEIGHTED,
            weight_column=weight_column,
            priority_order=priority_order,
        )
    if value_type == "ordinal":
        if value_column is None or priority_order is None:
            raise ValidationError("value_column and priority_order are required for ordinal aggregation")
        return aggregate_ordinal(
            frame,
            value_column,
            cell_column=cell_column,
            priority_order=priority_order,
            weight_column=weight_column,
        )
    if value_type == "range":
        if lower_column is None or upper_column is None:
            raise ValidationError("lower_column and upper_column are required for range aggregation")
        return aggregate_range(
            frame,
            lower_column,
            upper_column,
            cell_column=cell_column,
            rule=rule or RangeRule.FULL_RANGE,
            weight_column=weight_column,
        )
    raise ValidationError("value_type must be numeric, categorical, ordinal, or range")


def _contribution_weights(
    frame: Any,
    *,
    coverage_column: str,
    length_column: str,
) -> Any:
    """Return one explicit per-row geometry allocation factor."""
    pd = _require_pandas()
    _validate_columns(
        frame,
        [column for column in (coverage_column, length_column) if column in frame.columns],
    )
    weights: list[float] = []
    for row_number, (_, row) in enumerate(frame.iterrows()):
        coverage = row[coverage_column] if coverage_column in frame.columns else None
        length = row[length_column] if length_column in frame.columns else None
        coverage_present = coverage is not None and not bool(pd.isna(coverage))
        length_present = length is not None and not bool(pd.isna(length))
        if coverage_present and length_present:
            raise ValidationError(
                f"contribution row {row_number} must not contain both {coverage_column} and {length_column}"
            )
        value = coverage if coverage_present else length if length_present else 1.0
        try:
            numeric = float(value)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"contribution weight at row {row_number} must be numeric") from exc
        if not math.isfinite(numeric) or not 0 <= numeric <= 1:
            raise ValidationError(f"contribution weight at row {row_number} must be in [0, 1]")
        weights.append(numeric)
    return pd.Series(weights, index=frame.index, dtype="float64")


def _annotate_geometry_result(
    result: Any,
    *,
    semantics: ValueSemantics,
    allocation_rule: str,
    value_column: str | None,
) -> Any:
    result.attrs = dict(result.attrs)
    result.attrs["geosquare"] = {
        "value_semantics": semantics.value,
        "allocation_rule": allocation_rule,
        "source_value_column": value_column,
        "stage": "geometry_contributions_to_cells",
    }
    return result


def aggregate_geometry_contributions(
    frame: Any,
    *,
    value_semantics: ValueSemantics | str,
    value_column: str | None = None,
    lower_column: str | None = None,
    upper_column: str | None = None,
    cell_column: str = "gid",
    output_column: str | None = None,
    allocation_rule: str | None = None,
    coverage_column: str = "coverage_ratio",
    length_column: str = "length_ratio",
    numerator_column: str | None = None,
    denominator_column: str | None = None,
    category_rule: CategoryRule | str = CategoryRule.MAJORITY_WEIGHTED,
    priority_order: Iterable[Any] | None = None,
    range_rule: RangeRule | str = RangeRule.FULL_RANGE,
) -> Any:
    """Allocate and aggregate auditable geometry contributions by explicit semantics.

    ``TOTAL`` values are multiplied by the row's area or length ratio and summed.
    ``DENSITY`` and ``MEASUREMENT`` values use a ratio-weighted mean. ``RATE`` can
    aggregate explicit numerator/denominator columns or use the same weighted-mean
    fallback. ``COUNT``, categorical, ordinal, and range values use dedicated rules.
    The selected semantics and allocation rule are recorded in ``DataFrame.attrs``.
    """
    pd = _require_pandas()
    if not isinstance(frame, pd.DataFrame):
        raise ValidationError("frame must be a pandas.DataFrame")
    if cell_column not in frame.columns:
        raise ValidationError(f"missing table columns: ['{cell_column}']")
    semantics = _as_enum(value_semantics, ValueSemantics, "value semantics")
    work = frame.copy()
    weights = _contribution_weights(
        work,
        coverage_column=coverage_column,
        length_column=length_column,
    )
    weight_column = "__geosquare_geometry_weight"
    work[weight_column] = weights

    default_rules = {
        ValueSemantics.COUNT: "unit_count",
        ValueSemantics.TOTAL: "ratio_weighted_sum",
        ValueSemantics.DENSITY: "ratio_weighted_mean",
        ValueSemantics.MEASUREMENT: "ratio_weighted_mean",
        ValueSemantics.RATE: "ratio_weighted_rate",
        ValueSemantics.ORDINAL: "priority_order",
        ValueSemantics.CATEGORICAL: "category_rule",
        ValueSemantics.RANGE: "range_rule",
    }
    selected_allocation = allocation_rule or default_rules[semantics]
    if not isinstance(selected_allocation, str) or not selected_allocation.strip():
        raise ValidationError("allocation_rule must be a non-empty string")

    if semantics is ValueSemantics.COUNT:
        count_column = value_column or "__geosquare_unit_count"
        if value_column is None:
            work[count_column] = 1
        result = aggregate_numeric(
            work,
            count_column,
            cell_column=cell_column,
            rule=NumericRule.COUNT,
            output_column=output_column or "count",
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics is ValueSemantics.TOTAL:
        if value_column is None:
            raise ValidationError("value_column is required for TOTAL aggregation")
        _validate_columns(work, [value_column])
        allocated_column = "__geosquare_allocated_value"
        work[allocated_column] = work[value_column].astype(float) * work[weight_column]
        result = aggregate_numeric(
            work,
            allocated_column,
            cell_column=cell_column,
            rule=NumericRule.SUM,
            output_column=output_column or value_column,
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics in {ValueSemantics.DENSITY, ValueSemantics.MEASUREMENT}:
        if value_column is None:
            raise ValidationError(f"value_column is required for {semantics.value} aggregation")
        result = aggregate_numeric(
            work,
            value_column,
            cell_column=cell_column,
            rule=NumericRule.WEIGHTED_MEAN,
            weight_column=weight_column,
            output_column=output_column or value_column,
            value_semantics=semantics,
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics is ValueSemantics.RATE:
        if (numerator_column is None) != (denominator_column is None):
            raise ValidationError("numerator_column and denominator_column must be supplied together")
        if numerator_column is not None and denominator_column is not None:
            _validate_columns(work, [numerator_column, denominator_column])
            numerator_allocated = "__geosquare_allocated_numerator"
            denominator_allocated = "__geosquare_allocated_denominator"
            work[numerator_allocated] = work[numerator_column].astype(float) * work[weight_column]
            work[denominator_allocated] = work[denominator_column].astype(float) * work[weight_column]
            group_columns = _group_columns(work, cell_column)
            numerator = aggregate_numeric(
                work,
                numerator_allocated,
                cell_column=cell_column,
                rule=NumericRule.SUM,
                output_column="__geosquare_numerator",
            )
            denominator = aggregate_numeric(
                work,
                denominator_allocated,
                cell_column=cell_column,
                rule=NumericRule.SUM,
                output_column="__geosquare_denominator",
            )
            merged = numerator.merge(denominator, on=group_columns, suffixes=("", "__denominator"))
            if (merged["__geosquare_denominator"] == 0).any():
                raise ValidationError("aggregated rate denominator must not be zero")
            result = merged[group_columns].copy()
            result[output_column or "rate"] = (
                merged["__geosquare_numerator"] / merged["__geosquare_denominator"]
            )
            result["feature_count"] = merged["feature_count"]
            return _annotate_geometry_result(
                result,
                semantics=semantics,
                allocation_rule=selected_allocation,
                value_column=f"{numerator_column}/{denominator_column}",
            )
        if value_column is None:
            raise ValidationError("value_column or numerator_column/denominator_column is required for RATE aggregation")
        result = aggregate_numeric(
            work,
            value_column,
            cell_column=cell_column,
            rule=NumericRule.WEIGHTED_MEAN,
            weight_column=weight_column,
            output_column=output_column or value_column,
            value_semantics=semantics,
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics is ValueSemantics.CATEGORICAL:
        if value_column is None:
            raise ValidationError("value_column is required for CATEGORICAL aggregation")
        selected_rule = _as_enum(category_rule, CategoryRule, "category rule")
        result = aggregate_categorical(
            work,
            value_column,
            cell_column=cell_column,
            rule=selected_rule,
            weight_column=weight_column,
            output_column=output_column,
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics is ValueSemantics.ORDINAL:
        if value_column is None or priority_order is None:
            raise ValidationError("value_column and priority_order are required for ORDINAL aggregation")
        result = aggregate_ordinal(
            work,
            value_column,
            cell_column=cell_column,
            priority_order=priority_order,
            weight_column=weight_column,
            output_column=output_column,
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=value_column,
        )

    if semantics is ValueSemantics.RANGE:
        if lower_column is None or upper_column is None:
            raise ValidationError("lower_column and upper_column are required for RANGE aggregation")
        selected_rule = _as_enum(range_rule, RangeRule, "range rule")
        result = aggregate_range(
            work,
            lower_column,
            upper_column,
            cell_column=cell_column,
            rule=selected_rule,
            weight_column=weight_column,
            output_prefix=output_column or "range",
        )
        return _annotate_geometry_result(
            result,
            semantics=semantics,
            allocation_rule=selected_allocation,
            value_column=f"{lower_column}/{upper_column}",
        )

    raise ValidationError(f"unsupported geometry value semantics: {semantics.value}")


def aggregate_geometry_table_to_cells(
    source: Any,
    service: Any,
    domain_code: str,
    level: int,
    *,
    value_semantics: ValueSemantics | str,
    value_column: str | None = None,
    geometry_options: dict[str, Any] | None = None,
    **aggregation_options: Any,
) -> Any:
    """Run geometry-table conversion, explicit allocation, and cell aggregation."""
    from .table import geometry_table_to_cells

    contributions = geometry_table_to_cells(
        source,
        service,
        domain_code,
        level,
        **(geometry_options or {}),
    )
    result = aggregate_geometry_contributions(
        contributions,
        value_semantics=value_semantics,
        value_column=value_column,
        **aggregation_options,
    )
    result.attrs = dict(result.attrs)
    result.attrs["geosquare"]["stage"] = "geometry_table_to_cells_to_aggregate"
    return result
