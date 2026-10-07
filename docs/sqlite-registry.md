# SQLite registry

The runtime registry is a signed SQLite database containing the manifest, domain rows, profile definitions, scale metadata, and required PROJ-resource hashes. It replaces the older collection of runtime JSON files.

## Packaged resources

```text
src/geosquare_v2/db/registry.db       SQLite registry database
src/geosquare_v2/db/registry.db.sig   Detached Ed25519 signature sidecar
src/geosquare_v2/data/registry/boundaries/  Boundary metadata and GeoJSON files used for release verification
release/registry-trust.json           Candidate public-key example for this checkout
```

The database and signature are a pair. Boundary GeoJSON files are not read by grid indexing or geometry calculations; they are release resources whose hashes can be checked by the loader. The loader is fail-closed: it verifies the signature, signed hashes, exact PROJ resources, and profile definitions before returning a registry. Boundary hashes are checked when `verify_boundaries=True`.

## Load a verified registry

Install the registry extra first:

```zsh
python -m pip install -e ".[registry]"
```

From a repository checkout:

```python
import base64
import json
from pathlib import Path

from geosquare_v2 import DbRegistryLoader

root = Path(__file__).resolve().parents[1]
keys = json.loads((root / "release/registry-trust.json").read_text())
trust = {
    key_id: base64.b64decode(value, validate=True)
    for key_id, value in keys.items()
}

registry = DbRegistryLoader(
    trust,
    root / "src/geosquare_v2/db",
    boundary_root=root / "src/geosquare_v2/data/registry",
    verify_boundaries=True,
).load()

profile = registry.get("ID")
```

For a complete service example, see [`examples/quickstart.py`](../examples/quickstart.py). The trust file is a public-key example for the local candidate, not a production trust policy.

If boundary files are intentionally unavailable, the loader can skip boundary verification:

```python
registry = DbRegistryLoader(
    trust,
    root / "src/geosquare_v2/db",
    verify_boundaries=False,
).load()
```

Use this only when the application has an explicit reason not to verify the release boundary resources. Signature, PROJ, and profile checks still run.

## Inspect domains without trusting the registry

`list_registry_domains()` is a metadata-only inspection helper. It does not verify the signature, PROJ resources, boundary hashes, or CRS definitions:

```python
from geosquare_v2 import list_registry_domains

for domain in list_registry_domains("src/geosquare_v2/db"):
    print(domain.domain_code, domain.name, domain.min_level, domain.max_level)
```

Use `DbRegistryLoader.load()` for application logic.

## Maintainer workflow

Do not edit `registry.db` by hand. Generate a new candidate, review it, and sign it with a private key stored outside the repository:

```zsh
.venv/bin/python tools/generate_asean_release_candidates.py
sqlite3 src/geosquare_v2/db/registry.db ".dump"
.venv/bin/python tools/sign_registry_db.py \
  --private-key /secure/path/geosquare-registry-private.pem \
  --db src/geosquare_v2/db/registry.db \
  --output src/geosquare_v2/db/registry.db.sig \
  --key-id geosquare-registry-2026-09
```

For migration of an older JSON release input during maintenance or testing:

```zsh
.venv/bin/python tools/migrate_registry_to_db.py \
  --source release \
  --destination src/geosquare_v2/db/registry.db
```

Every database change requires a new signature. Never commit, publish, or paste a private signing key. See [release and security](release.md) for approval gates and attribution requirements.
