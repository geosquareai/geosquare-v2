# GitHub About and release checklist

This guide contains the project text and checklist for the proposed stable `0.2.0` GitHub Release and future PyPI publication. The prior `0.1.0rc2` candidate is historical and its artifacts must not be reused.

## Repository About

Use this short description:

```text
Country-scoped metric grid for durable square-cell IDs, signed profiles, geometry, batch indexing, and aggregation.
```

Suggested topics:

```text
geospatial
gis
spatial-indexing
coordinate-reference-system
metric-grid
python
geodata
geojson
pyproj
shapely
data-engineering
```

Suggested website after PyPI publication:

```text
https://pypi.org/project/geosquare-v2/
```

Until PyPI publication, use the repository URL or the TestPyPI project page. The About description should not call unpublished artifacts production geodetic data.

## GitHub Release `v0.2.0`

Create this release only after the stable worktree has been reviewed, Gate A/B/C records are approved, the registry is regenerated and signed, and the exact artifacts have passed clean TestPyPI verification.

- Tag: `v0.2.0`
- Release title: `GeoSquare V2 0.2.0`
- Mark as a pre-release: no, only after final authorization
- Attach only the wheel and sdist built from that exact tag

The release notes must include the support matrix:

- `BN`, `ID`, `LA`, `MY`, `PH`, `SG`, and `VN`: production-ready within the GeoSquare support scope;
- `KH`, `MM`, `TH`, and `TL`: technical/provisional, with no official national-datum or production-accuracy guarantee; and
- all custom projected CRSs: GeoSquare-owned definitions, not claims of official national projected CRS authority.

The release notes must also retain the file-specific boundary licenses, attribution, material-change disclosure, and explicit non-endorsement wording.

## TestPyPI promotion

Build from the exact reviewed `v0.2.0` tag into one fresh artifact directory. Before upload:

1. run the complete Gate D validation suite;
2. verify the detached registry signature and trusted public key;
3. inspect wheel and sdist contents for the database, signature, boundaries, notices, and support matrix;
4. install both exact artifacts in clean Python 3.11+ environments;
5. load the signed registry with boundary verification enabled; and
6. run the point-indexing quickstart and stable support-matrix checks.

## PyPI promotion

After successful clean TestPyPI verification and explicit release authorization, upload the exact same files:

```zsh
.venv/bin/python -m twine upload --repository pypi release/artifacts/<reviewed-release>/dist/*
```

Never overwrite a published version. If any release content changes, increment the version.

## Historical rc2 note

`0.1.0rc2` was a technical candidate. Its old artifact path and release text are retained only as historical context; they are not valid inputs for the `0.2.0` stable release.

## Future releases

Use [the automated publishing guide](release-automation.md) after the first PyPI project exists and trusted publishers are configured. The intended sequence is TestPyPI, clean verification, GitHub environment approval, then PyPI.
