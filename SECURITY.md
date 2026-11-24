# Security policy

## Report a vulnerability

Please report security problems privately. Do not open a public issue or pull request for them.

Use GitHub private vulnerability reporting:

[Report a vulnerability](https://github.com/geosquareai/geosquare-v2/security/advisories/new)

Include:

- the version or commit you tested;
- the steps to reproduce the problem;
- what you expected, and what happened instead;
- the impact you think it has.

## Scope

In scope:

- the `geosquare_v2` Python package;
- registry loading and signature checks;
- dataset readers and writers, including manifest and content-hash checks.

Out of scope for this policy:

- a wrong grid value that is not a security issue. Report it as a normal issue.
- boundary data licence questions. See [licenses](docs/data-licenses.md).

## Handling

Reports go to the maintainers through the advisory. When a fix is released, the maintainers publish an advisory.

Do not put secrets, private keys or personal data in a report.
