# Time cube (`cell_time_values`)

This page is the full guide to the time cube. It explains the rules, the labels, the intervals, the joins, and the platform API. It also lists what is not built yet.

The time cube stores values that change over time, one row per cell and period. It is the L7 feature of GeoSquare V2.

The rules live in `src/geosquare_v2/timecube.py`. The writer and reader live in `src/geosquare_v2/time_store.py`. The test cases live in `conformance/spec-2.0/time-values.json`.

## 1. What it is

| Question | Answer |
|---|---|
| What is one row? | One cell (`gid`) and one period (`period`) |
| How many rows per cell? | One per period. Many periods are expected |
| Can one cell have two rows for one period? | No. The pair `(gid, period)` is unique |
| Can a dataset mix cell levels? | No. One level per dataset |
| Can a dataset mix period types? | No. One `period_type` per dataset |
| Is time zone allowed? | Only UTC |
| Are gaps allowed? | Yes. The range may have missing periods |

Compared with `cell_values`:

| | `cell_values` | `cell_time_values` |
|---|---|---|
| Key | `gid` | `(gid, period)` |
| Time | none | `period_type`, `period_start`, `period_end` |
| Rows per cell | one | many |
| Sort order | `gid` | `gid`, then `period` |

## 2. Words you need

| Word | Meaning |
|---|---|
| Period | One calendar slot, such as a day or an hour |
| Label | The text that names a period, such as `2026-11-19` |
| Period type | The kind of label: `year`, `month`, `day`, or `hour` |
| Bucket | A block of hours inside a day. Used only by `hour` |
| Interval | The start and end instants of a label, in UTC |
| Half-open | Start is included, end is excluded. `[start, end)` |
| Relation | How two intervals compare: `equal`, `contained`, `contains`, `overlap`, or `disjoint` |

## 3. Labels

A label is text. Each period type has one format.

| Period type | Format | Example | Meaning |
|---|---|---|---|
| `year` | `YYYY` | `2026` | Whole year |
| `month` | `YYYY-MM` | `2026-11` | Whole month |
| `day` | `YYYY-MM-DD` | `2026-11-19` | Whole day |
| `hour` | `YYYY-MM-DDTHH` | `2026-11-19T04` | Start hour of a bucket |

Rules:

- Use four digits for the year. Years 0001 to 9999 are allowed. Year 0000 is not.
- Use ASCII digits only.
- No offset, no space, no short form. `2026-11-19 04`, `2026-11-19T04+07`, and `2026-1-1` are rejected.
- Dates must be real. `2023-02-29` is rejected. `2024-02-29` is accepted, because 2024 is a leap year.
- For `hour`, the bucket size must be one of **1, 2, 3, 4, 6, 8, 12** hours. The hour must start a bucket. With a 4-hour bucket, labels start at `00`, `04`, `08`, `12`, `16`, or `20`.
- `bucket_hours` is required for `hour`. It is not allowed for any other period type.

Examples of rejected labels:

| Label | Period type | Bucket | Why |
|---|---|---|---|
| `2023-02-29` | `day` | | Not a real date |
| `2026-11-19T02` | `hour` | 4 | 02 does not start a 4-hour bucket |
| `2026-11-19T04+07` | `hour` | 4 | Offsets are not allowed |
| `2026-11-19` | `day` | 4 | `bucket_hours` is only for `hour` |
| `2026-11-19T00` | `hour` | 5 | 5 is not an allowed bucket size |

## 4. Intervals

Each label stands for `[start, end)` in UTC. The end is the first instant outside the period.

| Label | Period type | Bucket | Start (UTC) | End (UTC, excluded) |
|---|---|---|---|---|
| `2026` | `year` | | 2026-01-01 00:00 | 2027-01-01 00:00 |
| `2026-12` | `month` | | 2026-12-01 00:00 | 2027-01-01 00:00 |
| `2026-11-19` | `day` | | 2026-11-19 00:00 | 2026-11-20 00:00 |
| `2026-11-19T04` | `hour` | 4 | 2026-11-19 04:00 | 2026-11-19 08:00 |

The year 9999 has no end inside the allowed range. The reader rejects it when an end is needed.

## 5. Time zone

Store UTC only. Convert local time before writing.

| Local time | Zone | UTC |
|---|---|---|
| 07:00 on 2026-11-19 | WIB (UTC+7) | 00:00 on 2026-11-19 |
| 08:00 on 2026-11-19 | WITA (UTC+8) | 00:00 on 2026-11-19 |
| 09:00 on 2026-11-19 | WIT (UTC+9) | 00:00 on 2026-11-19 |

The manifest field `timezone` must be `UTC`. Any other value is rejected. The reader checks this on every read.

## 6. Manifest

Each dataset has one `manifest.json`. These fields are required:

```json
{
  "dataset_type": "cell_time_values",
  "manifest_version": "1.0",
  "grid_system": "geosquare",
  "grid_version": "v2",
  "domain_code": "ID",
  "domain_id": 1,
  "level": 9,
  "period_type": "hour",
  "bucket_hours": 4,
  "timezone": "UTC",
  "period_start": "2026-11-01T00",
  "period_end": "2026-12-01T00",
  "identity": {
    "gid_column": "gid",
    "period_column": "period",
    "unique_gid": false,
    "unique_key": ["gid", "period"]
  },
  "storage": {
    "parquet_compression": "zstd",
    "sorted_by": ["gid", "period"],
    "partitioning": [],
    "row_count": 1000
  },
  "value_fields": [
    {"name": "devices", "semantics": "COUNT", "logical_type": "numeric", "unit": null},
    {"name": "rain_mm", "semantics": "MEASUREMENT", "logical_type": "numeric", "unit": "mm", "time_aggregation": "mean"}
  ]
}
```

Checks on the manifest:

- `dataset_type` must be `cell_time_values`.
- `timezone` must be `UTC`.
- `period_start` must be before `period_end`. The range must not be empty.
- Both bounds must use the label format of `period_type`.
- `identity.unique_gid` must be `false`, and `unique_key` must be `["gid", "period"]`.
- `storage.sorted_by` must be `["gid", "period"]`.
- The name `period` is reserved. It cannot be a value field.

`period_start` is included. `period_end` is excluded. A month window for January 2026 is `period_start: "2026-01"` and `period_end: "2026-02"`.

## 7. Rows

Each row needs `gid` and `period`. Value columns follow.

Checks on the rows:

- Every `gid` is at the manifest `level`.
- Every `period` is a valid label of the manifest `period_type` and `bucket_hours`.
- Every `period` lies inside `[period_start, period_end)`. The end is not allowed.
- No two rows have the same `(gid, period)`.
- Rows are sorted by `gid`, then `period`. The writer sorts them. The reader rejects unsorted rows.

Example of a valid file for one day and two cells:

```text
gid,period,rain_mm
222222222,2026-11-19,12.4
222222222,2026-11-20,0.0
222222223,2026-11-19,3.1
```

## 8. Value fields and time rollup

A time rollup combines the periods of one cell into a coarser period. The rule depends on the field's semantics.

| Semantics | Time rollup | What you must declare |
|---|---|---|
| `COUNT` | Sum | Nothing |
| `TOTAL` | Sum | Nothing |
| `MEASUREMENT` | `mean`, `min`, or `max` | `time_aggregation` in the value field |
| `CATEGORICAL` | Not allowed | Nothing. The field cannot roll up in time |

Examples:

- Daily rain in millimetres is a `MEASUREMENT`. Declare `time_aggregation: "mean"` if the monthly value is an average.
- Daily device counts are `COUNT`. Their monthly value is the sum.
- A land-cover class is `CATEGORICAL`. It cannot be averaged over a year.

## 9. Relations between labels

A relation compares the intervals of two labels. Each side is a label, its period type, and its bucket.

| Relation | Meaning | Example |
|---|---|---|
| `equal` | Same start and same end | `2026-11-19` and `2026-11-19` |
| `contained` | Left lies inside right | `2026-11-19T04` (bucket 4) inside `2026-11-19` |
| `contains` | Left covers right | `2026` covers `2026-11-19` |
| `overlap` | Some overlap, but neither covers the other | Two different buckets that share part of an interval |
| `disjoint` | No shared instant | `2026-11-19` and `2026-11-20` |

If A contains B, then B is contained in A. This is always true. The test suite checks it for many label pairs.

## 10. Joins

A join matches rows of two datasets. Rows match when:

1. they have the same `gid`, and
2. the periods have the chosen relation.

The platform join counts left rows, not pairs. A left row is counted once, even if several right rows match it.

Example. Daily rain (left) and an annual population table (right). Use `relation: "contained"`. Each day lies inside the year, so every daily row matches the annual row of the same cell.

```text
Left rows (daily, cell A):   2026-11-01, 2026-11-02
Right rows (annual, cell A): 2026
Relation:                    contained
Matched left rows:           2
Sum of rain_mm:              sum over both days
```

Choose the relation on purpose:

- Use `contained` to bring coarse values down to fine rows, such as a year onto each day.
- Use `contains` to find which coarse periods hold a fine row.
- Use `overlap` for periods of different sizes that may share time.
- Use `equal` for the same period in both datasets.

## 11. Writing and reading

The Python functions are in `geosquare_v2.time_store`:

```python
from geosquare_v2.time_store import write_time_values, read_time_values

manifest = write_time_values(
    "data/tv-2026-11",
    rows,                      # list of dicts with "gid", "period", and the value fields
    domain_code="ID",
    domain_id=1,
    level=9,
    period_type="day",
    period_start="2026-11-01",
    period_end="2026-12-01",
    value_fields=[{"name": "rain_mm", "semantics": "MEASUREMENT", "time_aggregation": "mean"}],
)

manifest, rows = read_time_values("data/tv-2026-11")
```

The writer:

- refuses a folder that already exists;
- checks the manifest and every row before it writes anything;
- writes to a temporary folder, then renames it, so a failed write leaves no partial dataset.

The reader:

- checks the manifest, the Parquet columns, and the row count;
- checks every row against the rules above;
- rejects the dataset if any rule breaks. It never repairs data.

Stored files are one folder with `manifest.json` and `data/time_values.parquet`. The Parquet columns are `gid`, `period`, and the value fields, in that order.

## 12. Platform API

The platform stores and joins time datasets. The routes are in `geosquare-platform`, file `src/geosquare_platform/timestore.py`.

### Upload

`POST /time-datasets` takes a CSV file and form fields:

| Field | Example |
|---|---|
| `file` | CSV with columns `gid,period,<value fields>` |
| `level` | `9` |
| `period_type` | `day` |
| `period_start` | `2026-11-01` |
| `period_end` | `2026-12-01` |
| `value_fields` | `[{"name":"rain_mm","semantics":"MEASUREMENT","time_aggregation":"mean"}]` |
| `bucket_hours` | `4` (only for `hour`) |

The response is `201` with `dataset_id` (format `TIME-` and 12 hex characters), `rows`, `period_type`, and `bucket_hours`.

The ID comes from the file content and the settings. The same upload twice is refused.

### Join

`POST /query/time-join` is an internal route. It answers 404 unless `GSQ_INTERNAL_ROUTES=1` is set on the server.

```json
{
  "left_id": "TIME-aaaaaaaaaaaa",
  "right_id": "TIME-bbbbbbbbbbbb",
  "relation": "contained",
  "sum": ["rain_mm"]
}
```

`relation` is one of `equal`, `contained`, `contains`, or `overlap`. The default is `contained`. The response has `matched_rows`, `sums`, `relation`, `left_id`, and `right_id`.

Errors:

- `422` for an unknown relation, an unknown column, or a dataset that fails the checks.
- `404` for a bad ID, or when the internal routes are off.

## 13. Scale

The row count of a time dataset grows with cells times periods. Use these numbers to plan storage. They assume every cell has a value for every period. Real data is sparser.

Jakarta Barat has about 49,067 cells at 50 m (level 12). Level 14 cells are 5 m. A 5 m grid has about 100 times as many cells as a 50 m grid.

| Grain | Rows per variable, 50 m, one month | Rows per variable, 5 m, one month |
|---|---|---|
| Day | about 1.5 million | about 147 million |
| 4-hour bucket | about 8.8 million | about 883 million |
| Hour | about 35 million | about 3.5 billion |

The 5 m hourly case is far too large for one file. That is why the store must be sparse and why partitioning is planned. See section 15.

## 14. Decisions taken

| Date | Decision |
|---|---|
| 2026-11-19 | Day is the first period type. Mobile data may use hour buckets. |
| 2026-11-20 | Store all times in UTC. |
| 2026-11-20 | The first window is one month, not several years. |
| 2026-11-20 | Mobile data is proprietary. It is not published. Only internal joins may use it. |
| 2026-11-20 | Keep one file per dataset while the window is one month. |

Still open:

- The grain for mobile data: 4-hour buckets, or hourly.
- Whether the k rule applies to time outputs, and how. It is not defined yet.

## 15. Not built yet

| Item | Why it matters | Status |
|---|---|---|
| Partitioning by day or month | One file cannot hold very large hourly data | Not defined in the spec. Needs a rule in the contract first |
| Partitioning by cell prefix | Joins read only the cells they need | Not defined |
| JSON schema for `cell_time_values` | Tools can check manifests without Python | Not written. The Python rules are the reference |
| Completeness metadata | Tells users which periods exist | Not defined. Gaps are allowed for now |
| k rule for time outputs | Hourly counts at fine cells can reveal people | Not defined |
| Storage per source | Several sources with different grains | Not built |

## 16. Tests

The reference tests are in `tests/test_timecube.py`. The vector file has 28 cases. They cover six operations:

| Operation | What it checks |
|---|---|
| `parse` | Valid and invalid labels, leap days, buckets, offsets, separators |
| `interval` | Start and end of a label |
| `manifest` | Required fields, time zone, reserved names, identity |
| `rows` | Level, range, duplicates, sort order |
| `rollup` | Time rollup rule per semantics |
| `relation` | Relation between two labels |

The store tests are in `tests/test_stores.py`. They cover round trips, a duplicate pair, a period outside the range, a local time zone in a stored file, and an hour-bucket dataset.

The platform tests are in `tests/test_time_store.py`. They cover upload, a bad period, the join count, the internal gate, and an unknown relation.

## 17. Sources

| What | Where |
|---|---|
| Rules | `src/geosquare_v2/timecube.py` |
| Writer and reader | `src/geosquare_v2/time_store.py` |
| Contract section | `docs/cell-dataset-contract.md`, section 2, `cell_time_values` |
| Vectors | `conformance/spec-2.0/time-values.json` |
| Platform routes | `geosquare-platform`, `src/geosquare_platform/timestore.py` and `app.py` |
| Spec pull request | [geosquare-v2 #22](https://github.com/geosquareai/geosquare-v2/pull/22) |
| Store pull request | [geosquare-v2 #23](https://github.com/geosquareai/geosquare-v2/pull/23) |
| Platform pull request | [geosquare-platform #13](https://github.com/geosquareai/geosquare-platform/pull/13) |
