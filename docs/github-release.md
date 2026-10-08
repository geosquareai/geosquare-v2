# GitHub About and release checklist

This guide contains the project text and checklist for the GitHub repository page, the staged `0.1.0rc2` GitHub Release, and the future PyPI promotion.

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

Until PyPI publication, use the repository URL or the TestPyPI project page. The About description should not call the candidate production geodetic data.

## GitHub Release `v0.1.0rc2`

Create the release only after the staged successor commit has been reviewed:

- Tag: `v0.1.0rc2`
- Release title: `GeoSquare V2 0.1.0rc2`
- Mark as a pre-release: yes
- Mark as the latest release: no, unless the project explicitly wants the release candidate highlighted
- Attach the exact wheel and sdist from `release/artifacts/phase-datum-rc2/project/dist/`

Suggested release summary:

```markdown
## GeoSquare V2 0.1.0rc2

This is a technical release candidate for GeoSquare V2, a country-scoped hierarchical metric grid for durable square-cell identifiers.

### Static CRS updates

- BN: GDBD2009-based custom GeoSquare CRS;
- ID: SRGI2013 static realization at epoch 2012.0;
- LA: Lao 1997-based custom GeoSquare CRS;
- MY: GDM2000-based custom GeoSquare CRS;
- PH: PRS92-based custom GeoSquare CRS;
- SG: SVY21-based custom GeoSquare CRS; and
- VN: existing VN-2000 baseline.

### Candidate limitations

- These are GeoSquare-owned custom projected CRSs, not claims that all are official national projected CRSs.
- ID input coordinates must already be normalized to the SRGI2013 static realization at epoch 2012.0.
- KH and MM remain pending authoritative CRS packages.
- TH remains on its existing technical profile; TGM2017 is a vertical/geoid model, not a horizontal CRS.
- TL remains provisional because no verified modern national horizontal datum is available.
- Bundled boundary data remains under its recorded file-specific licenses.
- The package is approximately 17 MB as a wheel and 33 MB as an sdist.

### Verification

The staged wheel and sdist passed the 195-test suite, signed-registry verification for all 11 domains, clean wheel and sdist installation, boundary-hash checks, and ID static-2012 point smoke tests.

TestPyPI and PyPI publication are separate steps.
```

## TestPyPI promotion

The staged successor artifacts are:

```text
release/artifacts/phase-datum-rc2/project/dist/geosquare_v2-0.1.0rc2-py3-none-any.whl
release/artifacts/phase-datum-rc2/project/dist/geosquare_v2-0.1.0rc2.tar.gz
```

Before upload:

1. review the staged profile and CRS changes;
2. run `twine check` on both files;
3. verify the detached registry signature and public trust key;
4. install from TestPyPI in a clean Python 3.11+ environment; and
5. verify the ID static-2012 input limitation in the release notes.

## PyPI promotion

After TestPyPI verification and explicit release approval:

```zsh
.venv/bin/python -m twine upload --repository pypi release/artifacts/phase-datum-rc2/project/dist/*
```

Never overwrite a published version. If any release content changes, increment the version.

## Future releases

Use [the automated publishing guide](release-automation.md) after the first PyPI project exists and trusted publishers are configured. The intended sequence is TestPyPI, clean verification, GitHub environment approval, then PyPI.
