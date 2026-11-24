# DuckDB engine and Iceberg: handover

**Last updated:** 2026-11-24
**Scope:** `geosquare-engine` (DuckDB extension `geosquare_v2`), the manifest 1.1 work, and
the spec it follows in `geosquare-v2` (`docs/dataset-metadata.md`).
**Audience:** the next session, and whoever on the team takes over the engine.

This file is the starting point. Read it first, then check live state with `gh` before you
report any PR status. Do not trust a status from this file or from memory.

## 1. Where things stand

| Repo | Head on main | Notes |
|---|---|---|
| `geosquare-engine` | `62c1ea2` (PR #36) | All PRs from this round are merged. No DuckDB extension release exists yet. |
| `geosquare-v2` | `2a09f11` (PR #30) | Spec freeze merged. Python package `1.3.0` released (commit `2fcb880`). |

### Merged in the engine, in order

| PR | What | Merged |
|---|---|---|
| #26 | Colleague's branch `feat/duckdb-extension`. **Merged by accident.** Its code is in main, but main's code now equals the reviewed tree (#30). A revert would also undo the #30 fixes, so it was not reverted. | 2026-11-24 06:08 |
| #30 | Review of #26: spec rollup rules, RATE as weighted mean, expire dry run by default, legacy profile, Wasm fix, DuckDB 1.5.0 test fix | 2026-11-24 06:08 |
| #31 | Content hash in the engine (spec 3.1). Merged into the review branch. | 2026-11-24 04:02 |
| #32 | Manifest 1.1 writer. Merged into the review branch, **not into main**. Same commit as #35. | 2026-11-24 06:09 |
| #33 | Four local tests declare rollup rules. They failed on main after the spec rollup change. | 2026-11-24 06:53 |
| #34 | `compact_cell_dataset` keeps NULL numbers. It used to write them as 0. | 2026-11-24 06:53 |
| #35 | Manifest 1.1 writer, opt-in. Brought to main as a cherry-pick of #32. | 2026-11-24 06:52 |
| #36 | `expire_snapshots` default `retain_last` is 2 (was 1). | 2026-11-24 07:09 |

## 2. What is verified

- **Manifest 1.1 writer** (`bindings/duckdb/src/manifest11.rs`, `docs/manifest-1.1.md`).
  Flat, partitioned and Iceberg writes, compact, Iceberg append, and the refusals listed in
  the doc. Covered by `tests/test_manifest_11.py`.
- **Python cross-check.** A flat 1.1 folder passes `geosquare_v2.dataset.read_cell_dataset(path).validate()`
  (geosquare-v2 1.3.0). That checks the content hash and the statistics.
- **Iceberg interop with pyiceberg.** `tests/test_metadata.py`, `tests/test_iceberg_metrics.py`,
  and the three oracle scripts (`test_oracles.py`, `test_area_valid_oracle.py`,
  `test_polyfill_oracle.py`) pass on the current main build. They need pyiceberg, shapely,
  cryptography and the pinned pyproj (see section 6).
- **Migration 1.0 to 1.1 by overwrite.** Checked on flat, partitioned and Iceberg datasets.
  Row counts, sums and hashes match before and after.
- **DuckDB versions.** The CI list (`.github/workflows/duckdb.yml`, `TESTS`) passed on DuckDB
  1.4.0, 1.4.5, 1.5.0, 1.5.6 and 2.0.0 for the same writer code, as PR #32 (before it moved to main
  as #35). Rerun it on the current main before a release.

## 3. Known risks, most serious first

1. **Iceberg tables have no catalog, and Glue needs a pointer update after every write.** The
   engine finds the current table through `metadata/version-hint.text`. Glue can register the
   table, but Glue keeps its own pointer. Each write must update it. Otherwise Athena and any
   Glue-based reader see old data without an error. DuckDB, Spark and pyiceberg read the path
   directly, so they are not affected. See section 8.
2. **Commits on real S3 are untested.** The version hint uses a conditional PUT. Tests ran
   against a local S3 emulator only (`tests/test_s3.py`). Concurrent writers have not been
   tried on AWS.
3. **Writes stage the rows in memory.** `write_cell_dataset` stages the query result in an
   in-memory DuckDB table. Very large writes need enough RAM. Test with the largest table
   before relying on it. The largest table is `hazard_v2026`: 753M rows, 10.3 GB. It is not tested at that size.
4. **Compacted data before #34 has zeros.** `compact_cell_dataset` wrote NULL numbers as 0
   until #34. Datasets compacted before that keep the zeros. A new compact does not restore
   them. Find these datasets and rebuild them from the source.
5. **Manifest 1.1 has no upsert and no column changes.** Upsert, add, drop and rename are
   refused for 1.1 tables. Tables that need them stay on 1.0 for now.
6. **`update_cell_metadata` on a 1.0 flat or partitioned folder breaks the Python reader.** It
   rewrites `manifest.json` but not the Parquet footers, and the reader requires them to match.
   This is not fixed. Iceberg is not affected.
7. **Builds are on S3, but there is no release.** The data engineer uploaded builds to
   `s3://geosquare-static/geosquare-v2/`. He tested the install on DuckDB 1.4.0 and later, on one
   platform only. He has not tested Windows or macOS. We do not know which commit the builds came
   from. `Cargo.toml` still says `0.1.0` for every build, so old and new builds look the same.
8. **Default `fill_nulls` writes NULL numbers as 0** for new writes. That keeps the existing
   behaviour, so `null_share` is 0 for such columns. Pass `fill_nulls := false` to keep NULLs.
9. **DuckDB 1.5.0 Python bug.** `min()` on a VARCHAR column read from Parquet can return a
   truncated value. The DuckDB CLI on 1.5.3 is correct. Report it upstream. Tests work around
   it with `ORDER BY ... LIMIT 1`.
10. **Wasm CI can flake.** The browser job downloads DuckDB's Parquet extension from
    extensions.duckdb.org. A failed download fails the job. A rerun passed (PR #34).
11. **Small files.** `hazard_v2026` has about 23k files, about 450 KB each. `people_v2023` has
    about 27k files, about 150 KB each. Many small files slow reads. Compaction fixes that, but
    compaction stages the whole table in memory (risk 3).
12. **Wide table.** `people_v2023` has 228 columns. Manifest 1.1 needs every value column to be
    an integer, a float or text. Check the types before any 1.1 plan.

## 4. Decisions made, and why

- **Manifest 1.1 is opt-in.** The default stays 1.0. Changing it would break upsert, compact and
  alter paths. Readers older than geosquare-v2 1.3.0 reject 1.1.
- **Parent rules default to `none`** for every semantics except COUNT, TOTAL (`sum`) and DENSITY
  (`weighted_mean` by area). The spec sets no default for MEASUREMENT, so `none` is the safe
  choice. Confirm this with the team.
- **Column rename is refused on 1.1.** The content hash is read by column name, so a renamed
  column cannot be checked. Allowing rename needs a mapping by field id. Not done.
- **`update_cell_metadata` is refused on 1.1 folders.** Same reason as risk 6.
- **`retain_last` default is 2.** A plain `expire_snapshots` keeps the current snapshot and the
  one before it. Pass `retain_last := 1` for the old behaviour. Datasets use more space until
  expired.
- **Dry run is still the default for `expire_snapshots`.**
- **Compact runs with `fill_nulls := false`.** Compaction must not change values.
- **Candidate domains (VN, TH) cannot be 1.1.** The extent is in lon/lat and needs a released
  CRS.

## 5. Open decisions

- Which catalog the data team uses, and which engines read the tables (section 7).
- Whether 1.1 needs upsert, rename, add and drop soon. Each one is engine work.
- Which platform datasets are still on 1.0, and whether to migrate them.
- Whether `fill_nulls` should default to off for new writes.
- Whether to tell the colleague about #26 in writing. It was merged by accident. This is a
  courtesy step, not a code step.

## 6. Environment and how to work

Scratch directories do not survive between sessions. Recreate them:

```text
uv venv --python 3.12 venv-duck150
uv pip install --python venv-duck150/bin/python duckdb==1.5.0 pyarrow pytest

uv venv --python 3.12 venv-pyice
uv pip install --python venv-pyice/bin/python duckdb==1.5.0 pyarrow pytest pyiceberg shapely cryptography "pyproj==3.7.2"
```

Pin `pyproj==3.7.2`. It bundles PROJ 9.5.1, which the signed registry expects. Newer pyproj
bundles PROJ 9.8.1, and the registry check then fails with "installed PROJ version does not
match signed registry database".

Build and package (from `bindings/duckdb`). `build.sh` does not work with `CARGO_TARGET_DIR`
set, so package by hand:

```text
CARGO_TARGET_DIR=<scratch>/target-engine-duck cargo build --release --locked
python3 scripts/append_extension_metadata.py -l <scratch>/target-engine-duck/release/libgeosquare_v2.dylib \
  -n geosquare_v2 -p osx_arm64 -dv v1.2.0 -ev "v0.1.0" -o <scratch>/ext/geosquare_v2.duckdb_extension
```

Run tests (from `bindings/duckdb`, with the extension path as the argument):

```text
PYTHONPATH=<geosquare-v2>/src <venv>/bin/python tests/test_manifest_11.py <ext>
PYTHONPATH=<geosquare-v2>/src <venv>/bin/python tests/test_oracles.py <ext> <geosquare-v2 checkout>
```

The lists are in `bindings/duckdb/Makefile` (`test_versions`) and in `.github/workflows/duckdb.yml`
(`TESTS`). Run the CI list before opening a PR. Use targeted tests on a small machine.

Working rules for this repo:

- Work on a feature branch named by the task. Push it by its explicit name. Open a PR.
  The user merges.
- Branch from `origin/main`. Keep the local main checkout on main and fast-forward it after
  each merge.
- Remove scratch worktrees before finishing. Never `git stash` in a shared worktree.
- macOS has no `timeout` command. Quote `*.rs` in zsh globs.
- The engine README is bilingual. If the README changes, update the Bahasa Indonesia section
  at the bottom too.

## 7. Next steps, in order

1. **Keep the five tables on 1.0.** They use upsert and alter, which 1.1 refuses.
2. **Measure memory on `hazard_v2026`.** Write a 5% sample with `write_cell_dataset`, and record
   the peak RAM. If it does not fit, the engine needs a writer that does not stage the whole
   table. That is engine work.
3. **Decide whether Athena is needed.** If yes, update the Glue pointer after every write.
   Test that on a test table first.
4. **Get the commit for the S3 builds.** Bump the version in `Cargo.toml` before the next build.
5. **Check whether any table was compacted before #34.** The engineer says the tables are new,
   so confirm it. If one was, rebuild it (risk 4).
6. **Test on Windows and macOS** before calling the extension supported.
7. **Fix risk 6** (`update_cell_metadata` on 1.0 folders), in its own PR.
8. **Decide on 1.1 upsert and rename** (section 5). Engine work if yes.
9. **Release** only after steps 2 and 4. Then tag `duckdb-v*`.

## 8. Data engineer answers (2026-11-24)

| Question | Answer | What it means |
|---|---|---|
| Catalog | Plain folder with `metadata/version-hint.text`. Can register in Glue. | Glue needs a pointer update after every write (risk 1). |
| Readers | DuckDB (extension or `iceberg_scan`), Spark and pyiceberg read the path. Athena needs Glue first. | Path readers work now. |
| Tables | Five tables. 0.6 to 10.3 GB, 16 to 753 million rows, 6 to 228 columns, 17k to 27k files each. | Risks 3, 11 and 12. |
| Operations | Upsert, append, overwrite and create through `write_cell_dataset`. Column changes through `alter_cell_dataset`. | Upsert and alter are refused on 1.1. Keep 1.0. |
| Versions | Tested on DuckDB 1.4.0 and later. Builds are in `s3://geosquare-static/geosquare-v2/`. Installed with `INSTALL ... FROM`. | Risk 7. Windows and macOS are untested by him. |

## 9. Pointers

- Spec: `geosquare-v2/docs/dataset-metadata.md`. Section 3.1 is the content hash, frozen.
- Engine write guide: `bindings/duckdb/docs/write-guide.md`.
- Manifest 1.1 guide: `bindings/duckdb/docs/manifest-1.1.md`.
- Engine README: `bindings/duckdb/README.md`.
- Python package release status: `geosquare-v2/HANDOVER.md` (local-only, stale) and
  `internal/handover/RELEASE_CANDIDATE.md`.
