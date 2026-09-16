# CCE-MVM v0.1 reproducibility package

Status: `__PUBLIC_RELEASE_STATUS__`

This fixed package contains the mathematical specification, standard-library
Python implementation, tests, protocols, configurations, and canonical
synthetic outputs used for CCE-MVM v0.1.

It contains no patient data or human-participant data. CCE-MVM v0.1 is a
research explanation model, not a clinical decision tool, capacity assessment,
legal determination, medical device, or validated measure of personal
sovereignty.

## Verify

From the extracted package root, run:

```bash
python3 verify_package.py
```

The verifier checks the exact inventory and hashes, configuration provenance,
references, verifier tests, core tests, and byte-for-byte regeneration of all
declared synthetic outputs. A successful result establishes internal
computational consistency in that environment; it does not establish clinical,
legal, ethical, or external validity.

## Release identity

- source repository: `__PUBLIC_REPOSITORY_URL__`
- source commit: `__CLEAN_GIT_COMMIT__`
- release tag: `__RELEASE_TAG__`
- archive SHA-256: published beside the archive
- tested environments: `__TESTED_ENVIRONMENTS__`
- independent human reproduction: `__INDEPENDENT_REPRODUCTION_STATUS__`

## Licenses and citation

See `LICENSE-MAP.md`, the exact texts under `LICENSES/`, and `CITATION.cff`.
Safety warnings describe the artifact's scientific limits; they are not
additional clauses inserted into the standard licenses.
