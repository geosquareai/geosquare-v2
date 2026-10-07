# Automated publishing with GitHub Actions

The repository can publish through GitHub Actions without storing a PyPI API token in GitHub. The workflow is [`.github/workflows/publish.yml`](../.github/workflows/publish.yml).

## One-time setup

Configure trusted publishing separately on [TestPyPI](https://test.pypi.org/) and [PyPI](https://pypi.org/):

1. Open the project’s publishing/trusted-publisher settings on the target index.
2. Add GitHub as the publisher.
3. Select the repository owner and repository name.
4. Set the workflow file to `.github/workflows/publish.yml`.
5. Use the GitHub environment name `testpypi` for TestPyPI and `pypi` for PyPI if the index asks for an environment.
6. In GitHub repository settings, create environments named `testpypi` and `pypi`.
7. Add required reviewers to the `pypi` environment so a PyPI publication cannot run without approval.

The workflow uses OpenID Connect (`id-token: write`) and `pypa/gh-action-pypi-publish`. It does not use `.pypirc`, a long-lived API token, or a secret stored in the repository. Keep local `.pypirc` for manual macOS uploads only.

For the first PyPI publication, manual upload may be simpler. After the project exists on PyPI, configure trusted publishing and use the workflow for later releases.

## Publishing sequence

1. Update the version in `pyproject.toml`; a published version cannot be overwritten.
2. Review the README, changelog, license/attribution records, signed registry, and release gates.
3. Commit and push the release inputs to the intended branch.
4. Open **Actions → Publish package → Run workflow**.
5. Select `testpypi` and select the exact release commit or tag.
6. Verify the TestPyPI project in a clean Python 3.11+ environment.
7. Run the workflow again with `pypi`; the `pypi` environment should require an approval.
8. Verify the PyPI project and install it from the public index.

Do not automatically publish to PyPI on every tag until the TestPyPI verification and environment approval policy are proven. Keep TestPyPI and PyPI as separate targets and separate trusted-publisher configurations.

## Local manual commands

For the current `0.1.0rc1` candidate, the validated files are:

```text
release/artifacts/phase-c-license-final/geosquare_v2-0.1.0rc1-py3-none-any.whl
release/artifacts/phase-c-license-final/geosquare_v2-0.1.0rc1.tar.gz
```

Manual TestPyPI upload:

```zsh
.venv/bin/python -m twine check release/artifacts/phase-c-license-final/*
.venv/bin/python -m twine upload --repository testpypi release/artifacts/phase-c-license-final/*
```

Manual PyPI upload after TestPyPI verification and explicit release approval:

```zsh
.venv/bin/python -m twine upload --repository pypi release/artifacts/phase-c-license-final/*
```

Never use `--skip-existing` to hide a version or artifact mismatch. If a published candidate needs content changes, increment the version.
