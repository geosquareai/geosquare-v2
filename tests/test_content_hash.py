"""Content hash (docs/dataset-metadata.md, section 3.1, frozen): conformance vectors and refusals.

The vectors in conformance/spec-2.0/content-hash.json are the contract. Other implementations
must reproduce them. Regenerate them with tools/generate_conformance_vectors.py only when the spec changes.
"""

import importlib.util
import json
from pathlib import Path

import pyarrow as pa
import pytest

from geosquare_v2.cell_metadata import content_sha256

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "conformance" / "spec-2.0" / "content-hash.json").read_text(encoding="utf-8"))

_spec = importlib.util.spec_from_file_location("generate_conformance_vectors", ROOT / "tools" / "generate_conformance_vectors.py")
generator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generator)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=[c["name"] for c in VECTORS["cases"]])
def test_vector_digest_and_encoding(case):
    assert generator.content_hash_encoded(case) == case["encoded"]
    assert content_sha256(generator.content_hash_table(case), case["value_fields"]) == case["sha256"]


def test_row_order_and_duplicates_change_nothing_but_duplicates_count():
    fields = [{"name": "v", "parquet_type": "double"}]
    forward = pa.table({"gid": ["a", "b"], "v": [1.0, 2.0]})
    reverse = pa.table({"gid": ["b", "a"], "v": [2.0, 1.0]})
    doubled = pa.table({"gid": ["a", "a", "b"], "v": [1.0, 1.0, 2.0]})
    assert content_sha256(forward, fields) == content_sha256(reverse, fields)
    assert content_sha256(doubled, fields) != content_sha256(forward, fields)


def test_declared_type_not_storage_type_decides_the_encoding():
    stored_int = pa.table({"gid": ["a"], "v": pa.array([3], type=pa.int64())})
    stored_double = pa.table({"gid": ["a"], "v": pa.array([3.0], type=pa.float64())})
    double_field = [{"name": "v", "parquet_type": "double"}]
    assert content_sha256(stored_int, double_field) == content_sha256(stored_double, double_field)
    int_field = [{"name": "v", "parquet_type": "int64"}]
    assert content_sha256(stored_int, int_field) != content_sha256(stored_double, double_field)


@pytest.mark.parametrize(
    ("values", "parquet_type", "message"),
    [
        ([float("nan")], "double", "NaN"),
        ([float("inf")], "double", "NaN and infinity"),
        ([True], "double", "not a number"),
        ([1.5], "int64", "not an integer"),
        ([True], "int64", "not an integer"),
        ([1], "string", "not a string"),
        ([1], "bool", "not supported"),
    ],
)
def test_unhashable_values_are_refused(values, parquet_type, message):
    table = pa.table({"gid": ["a"] * len(values), "v": pa.array(values, type=pa.float64() if isinstance(values[0], float) else None)})
    field = {"name": "v", "parquet_type": parquet_type}
    with pytest.raises(ValueError, match=message):
        content_sha256(table, [field])
