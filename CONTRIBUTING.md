# Contributing to GeoSquare V2

Thanks for helping. This page explains how to make a change and get it merged.

## Before you start

- Open an issue for a bug or a feature. Say what you want to change and why.
- Do not report a security problem in an issue. See [SECURITY.md](SECURITY.md).
- Read [concepts](docs/concepts.md) so you know the identity and CRS rules.

## Set up

Python 3.11 or newer is required.

```zsh
python -m pip install -e ".[analytics,registry,table,filesystem,s3,dev]"
```

## Check your change

CI runs these checks on Python 3.11 to 3.14. Run the same checks before you open a pull request:

```zsh
python -m compileall -q src tools tests examples
python -B -m pytest -q -W error::DeprecationWarning
python -m pip check
python examples/quickstart.py
```

Run the tests for the code you changed first. CI runs the full suite on every pull request.

## Pull requests

1. Make a branch from `main`. Do not commit to `main`.
2. Keep one topic in each pull request. Keep a separate commit for each change.
3. Describe what changed and how you checked it.
4. Wait for CI to pass. The maintainers review and merge.

## Rules for changes

- **Code and specs follow the same rules.** A change to the grid rules must also change the spec, the docs, and the test vectors in `conformance/spec-2.0/`.
- **Do not change country profiles by hand.** The registry is built and signed by the release tools. See [release guide](docs/release.md). Do not edit `src/geosquare_v2/db/` or the signature files by hand.
- **Keep the 1.0.0 datasets readable.** Changes to profiles or manifests must still read the fixtures in `tests/fixtures/legacy_v1_0_0/`.

## Licence

By contributing, you agree that your code is released under the Apache-2.0 licence. Boundary data keeps its own licence. See [licenses](docs/data-licenses.md).
