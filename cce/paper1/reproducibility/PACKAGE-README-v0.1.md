# CCE-MVM v0.1 reproducibility package

Status: internal candidate for independent review; not a public release

## What this package contains

This package contains the minimum mathematical specification, Python standard-library reference implementation, core tests, synthetic experiment protocols, fixed configurations, and canonical CSV/JSON outputs for CCE-MVM v0.1.

CCE-MVM v0.1 is a research explanation model. It does not use patient data or other human-participant data. It is not a clinical decision tool, capacity assessment, legal determination, medical device, or validated measure of personal sovereignty.

`cce/PROHIBITED-USES-AND-MISUSE-REGISTER-v0.1.md` lists concrete uses that this package must not support. `INTERNAL-REVIEW-NOTICE.md` gives invited reviewers only the temporary permission needed to inspect and run this internal candidate; it is not a public software license.

## What this package does not contain

- future H1c-R human-participant study materials, code, configurations, or outputs
- institution-specific documents or consultation drafts
- patient, family, employee, or reviewer information
- formative feedback records
- XLSX viewing derivatives
- the CCE paper manuscript

CSV and JSON files are the canonical computational outputs. XLSX files are intentionally excluded because their generation path has not been fixed.

## One-command verification

Required runtime: Python 3.9 or newer. Verified versions are listed below; the minimum requirement is not a claim that every later version and operating system has already been tested.

From this package root, run:

```bash
python3 verify_package.py
```

The verifier performs separate integrity, privacy, provenance, reference, test,
and reproduction checks:

1. rejects missing files, symbolic links, and files not declared by the manifest;
2. applies a limited generic denylist for paths, file types, and content;
3. verifies that `SHA256SUMS` exactly covers every immutable package file;
4. validates build metadata, Git provenance when available, experiment metadata,
   and declared configuration hashes;
5. checks local Markdown links and inline-code references whose targets use the
   declared text or forbidden-file extensions, after excluding fenced code, and
   rejects unresolved targets unless the exact exception and reason are declared;
6. runs 16 tests of the recipient-side verifier and rejects skipped tests;
7. runs the 96 CCE-MVM v0.1 core tests and rejects skipped tests;
8. regenerates the six paper-1 synthetic experiment groups in a new temporary
   directory and compares every declared CSV/JSON file byte-for-byte with the
   saved canonical output.

The verifier does not run the 41 future H1c-R preparation tests because they are outside CCE-MVM v0.1 and are not included.

The verifier disables Python bytecode creation during its subprocess runs. If you run an individual protocol command manually inside the extracted package, use the documented `python3 -B ...` form. A manual command without `-B` can create `__pycache__`; strict inventory verification will then correctly reject the modified package. Run experiments into a folder outside the package rather than deleting or ignoring undeclared files. If an accidental command creates undeclared files, discard that extracted copy and re-extract the fixed archive before verification.

The generic denylist is not a patient-information, personal-information, or secret-scanning system. Institution-specific source checks are performed by the author-side builder but the identifying terms are deliberately not placed in this distributed manifest. Review notes and all real-person information must remain outside the extracted package.

## Environment status

The current portable schema 0.2 internal candidate passed on Python 3.9.6, 3.10.21,
3.11.16, 3.12.13, 3.13.15, and 3.14.7 on macOS 26.5.2 arm64. These are exact
observations on one machine, with one tested patch release from each minor line;
they do not prove every patch release or another operating system. The
implementation and verifier use only the Python standard library. See
`PYTHON-TEST-MATRIX.md`.

The byte-for-byte result is an empirical observation for those exact CPython
versions. The noisy experiments use `random.Random.gauss`, and byte identity
also depends on the distribution-function implementation and floating-point
text formatting. Python does not make this package's byte identity a general
guarantee for every untested patch release, alternative implementation, or
future runtime. The current verifier has no tolerance fallback; a broader
support claim requires a separately specified and tested comparison rule.

`BUILD-METADATA.json` records the Python and platform used to build this candidate, the source Git HEAD when available, and whether the source worktree was dirty. Its `built_at_utc` field is UTC; dates in the Japanese-language project documents use Japan Standard Time (UTC+9) unless another timezone is stated. A dirty internal build is acceptable for review but is not acceptable as the final public release.

The verifier reports both checked and pending configuration hashes. A nonzero
`config_hashes_pending` value is permitted only while this package remains an
internal candidate; the publication gate requires zero pending hashes.

## Interpreting a successful verification

A successful run means that the packaged implementation, tests, and synthetic outputs are internally consistent in that environment. It does not establish:

- independent reproduction until a separate person and environment complete and document the run;
- empirical validity for real people;
- clinical usefulness, safety, legality, or ethical correctness;
- superiority over another model.

The checksum file and manifest are inside the same archive. They detect accidental or partial modification but do not independently authenticate who produced the archive. Before public release, the final archive SHA-256 or a detached signature must also be published through a separate trusted release page. Until that external anchor exists, a successful verification is an internal-consistency result only.

## Independent reproduction record

`INDEPENDENT-REPRODUCTION-RECORD-TEMPLATE.md` is an immutable, hashed blank
template. Do not type results into that file. Before the first attempt, copy it
outside the extracted package and complete the copy. This keeps the supplied
package unchanged and avoids a self-hash cycle.

```bash
cp INDEPENDENT-REPRODUCTION-RECORD-TEMPLATE.md ../CCE-INDEPENDENT-REPRODUCTION-RECORD.md
```

Do not place the completed record beside the package files. The manifest rejects
all additional files so that the supplied comparison baseline remains unchanged.
Keep the completed record outside the package and identify the package archive
SHA-256 in that record. Individual experiment protocols likewise write example
reproduction outputs outside the saved canonical result directories.

## Publication status

See `PUBLICATION-GATES.md`. A license, clean release identifier, supported Python range, final frozen hashes, and an accurate independent-reproduction status are still required before public release. A completed human reproduction record is recommended but is not required when the public release explicitly states `not completed`.
