# Release and security guide

## 1. Current release state

The package target is `0.1.0rc1`, a technical candidate uploaded to TestPyPI and verified in a clean Python 3.14 environment. It has not been uploaded to PyPI or Conda. The signed SQLite registry is distributed at:

```text
src/geosquare_v2/db/registry.db
src/geosquare_v2/db/registry.db.sig
```

The current signed candidate contains all 11 ASEAN domains. The profiles and
boundaries remain candidates until datum, boundary, epoch, redistribution,
package-size, and production-approval gates pass. See [NOTICE](../NOTICE) for
the evidence-backed boundary attribution and open redistribution gate.

## 2. Release artifacts

A release contains:

- package source;
- signed registry database;
- detached database signature;
- profile metadata;
- boundary files;
- boundary source notes and `NOTICE`;
- scale reports; and
- reproducible build information.

The trusted public key is an external verification input. It is not a private
key and is not a substitute for keeping the new private signing key outside
this repository and all package artifacts.

The database and signature are a pair. Change one and regenerate the other.

## 3. Signing keys

The private Ed25519 key must:

- stay outside the Git repository;
- stay outside distributed packages;
- have restricted file permissions;
- be kept offline or in a secure signing service; and
- never be pasted into chat or committed.

The public key is not secret.

Applications use a trusted public key to verify the detached signature.

The signing scripts reject private-key paths inside the repository.

## 4. Registry verification

A verified loader checks:

1. the database signature;
2. the SHA-256 digest of the database;
3. registry structure;
4. domain/profile identity;
5. profile hashes;
6. scale metadata hashes;
7. boundary hashes when enabled;
8. CRS parseability;
9. exact PROJ version; and
10. PROJ database/resource hashes.

A local PROJ mismatch is not a reason to bypass verification. Use the pinned environment.

## 5. Generate a candidate database

Generate from reviewed source artifacts:

```zsh
python tools/generate_release_candidates.py
```

Inspect:

- profiles;
- boundary sources;
- scale reports;
- CRS WKT2;
- domain IDs;
- registry rows; and
- generated diffs.

## 6. Sign the database

Use a private key outside the repository:

```zsh
python tools/sign_registry_db.py \
  --private-key /secure/location/geosquare-registry-private.pem \
  --db src/geosquare_v2/db/registry.db \
  --output src/geosquare_v2/db/registry.db.sig \
  --key-id geosquare-registry-YYYY-MM
```

Update the trusted public key in the application trust store.

Do not put the private key in the project repository.

## 7. Package data

`pyproject.toml` includes:

```text
src/geosquare_v2/db/*.db
src/geosquare_v2/db/*.sig
src/geosquare_v2/data/registry/boundaries/*.geojson
src/geosquare_v2/data/registry/boundaries/*.json
src/geosquare_v2/data/registry/boundaries/*.md
```

Build both a wheel and an sdist.

Install them in a clean environment.

Load the signed registry from the installed package.

## 8. Release gates

For this local `0.1.0rc1` preparation, verify:

- no private key is in Git, source inputs, or either candidate archive;
- the clean package contains the database and signature;
- the trusted public key verifies the signature;
- the pinned PROJ environment passes;
- scalar conformance tests pass;
- geometry and boundary tests pass;
- batch outputs match scalar outputs;
- table, dataset, and aggregation tests pass;
- migration fixtures pass;
- candidate profile and static-epoch status remain clearly non-production;
- boundary attribution is present in [NOTICE](../NOTICE), and the project release owner has accepted redistribution under the recorded file-specific terms; this is not an independent legal determination;
- the candidate package size is explicitly reviewed; and
- the full candidate wheel/sdist inspection and clean installs pass.

TestPyPI upload and clean-install verification are complete. No PyPI or Conda upload, tag, commit, or push is part of this preparation.

## 9. Validation commands

```zsh
.venv/bin/python -m compileall -q src tools tests
.venv/bin/python -B -m pytest -q
.venv/bin/python -m pip check
.venv/bin/python -m twine check release/artifacts/dist-candidate/*
```

The current suite collects 195 tests. Candidate artifacts are built only in
`release/artifacts/dist-candidate/`; the archived 0.1.0 files under `release/artifacts/dist/` are preserved and are not release inputs.

## 10. Do not edit signed artifacts by hand

Do not edit:

- `registry.db`;
- `registry.db.sig`;
- signed profiles; or
- trusted release metadata.

Change the source artifact. Regenerate the database. Review it. Sign it again.

## 11. Candidate preparation boundary

This task prepared and verified local `0.1.0rc1` artifacts and verified the TestPyPI publication. It does not run a PyPI or Conda upload. PyPI publication remains a separate, explicitly authorized step after the file-level attribution decision and final release review.
