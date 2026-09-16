# CCE-MVM v0.1 Python test matrix

Last checked: 2026-08-31
Status: current portable internal candidate checked on one patch release from each Python 3.9–3.14 minor line; not independent reproduction

## Verified versions

The same freshly built schema 0.2 internal candidate package passed on the following runtimes.

| Python | Operating system | Architecture | SHA-256 files | Core tests | Experiment groups | Regenerated files compared | Result |
|---|---|---|---:|---:|---:|---:|---|
| 3.9.6 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |
| 3.10.21 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |
| 3.11.16 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |
| 3.12.13 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |
| 3.13.15 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |
| 3.14.7 | macOS 26.5.2 | arm64 | 65 | 96 | 6 | 17 | pass |

Each run used the packaged `verify_package.py` from the fixed archive identified by its associated internal verification record. All six rejected undeclared inventory by design, verified 65 immutable-file hashes, checked 78 references extracted by the verifier from supported packaged text formats, validated all six configuration hashes with zero pending, ran 16 verifier tests and 96 CCE-MVM v0.1 core tests with zero skips, regenerated six synthetic experiment groups in a new temporary directory, and matched 17 declared CSV/JSON outputs byte-for-byte. The reference count is extraction coverage under the verifier's documented rules, not a claim that every possible human-readable reference syntax was parsed.

Python 3.10.21, 3.11.16, 3.13.15, and 3.14.7 were temporary, relocatable arm64 macOS builds from the `astral-sh/python-build-standalone` immutable release `20260825`. The downloaded assets were checked against the GitHub release digests before extraction:

- 3.10.21 asset SHA-256: `7fedf2035ce497b0ce01643cc5e8ed2aabfb8cfa730440e97af0330b56ce0608`
- 3.11.16 asset SHA-256: `2e50ed6ec49d8714a83c093e9ce74e1b8b21a2c64a49c3b603471d9c4caac76b`
- 3.13.15 asset SHA-256: `d681f7cebf4885637242cba807d22f476b9ea8555ac2dc7307172426dbf161e1`
- 3.14.7 asset SHA-256: `4c4a4114bc35f9d76d194fd72f43d8375b2f30686ddfe6b40c9258cfe6c16e40`
- release: https://github.com/astral-sh/python-build-standalone/releases/tag/20260825

The earlier 55-hash, 68-test candidate remains documented only in the development workspace as historical pre-hardening evidence. That record is intentionally excluded from the recipient package and is not used as the current pass record.

## What this establishes

The hardened internal candidate passed one measured patch release in every Python minor line from 3.9 through 3.14 on the same machine and operating-system family.

## What this does not establish

- Python 3.15 or later was not tested.
- Windows, Linux, and Intel macOS were not tested.
- All six runs were performed by the developer-side workflow on one Mac, so none is an independent reproduction.
- Testing one patch release from each minor line does not prove that every patch release or other Python implementation works.

## Public-release decision still required

Before release, choose one of the following and state it exactly:

1. support only the versions actually verified in the release matrix;
2. add automated tests for every claimed version and operating system;
3. state a minimum version as provisional and clearly distinguish tested from expected compatibility.

The recommended publication practice is to report the six exact versions above. A broader claim such as every Python 3.9–3.14 patch release or cross-platform support still requires a clean CI matrix or additional recorded tests.

Byte identity is not inferred from the Python version number alone. The noisy
experiments call `random.Random.gauss`, and the result files also depend on
floating-point text formatting. The six passes above are measured facts for
the exact CPython builds listed; they do not establish that distribution
functions use the same internal draw pattern in every untested runtime. This
candidate deliberately fails rather than silently switching to an undeclared
numeric tolerance. A tolerance-based comparison, if adopted, requires a new
versioned rule, thresholds, tests, and result provenance.
