# CCE-MVM v0.1 public source candidate

Status: private draft; not licensed or authorized for public release

This repository candidate contains the sanitized source files needed to inspect,
test, and build the CCE-MVM v0.1 reproducibility artifact. It contains synthetic
experiments only. It contains no patient data, human-participant data,
institutional review material, formative feedback, or future H1c-R materials.

CCE-MVM v0.1 is a research explanation model. It is not a clinical decision
tool, capacity assessment, legal determination, medical device, or validated
measure of personal sovereignty.

## Verify the source candidate

```bash
python -m unittest discover -v -s cce -p 'test_*.py'
```

## Build an isolated reproducibility artifact

Build outside this repository so that the generated package does not make the
source worktree dirty:

```bash
python cce/tools/build_reproducibility_package.py \
  --output-dir /tmp/cce-mvm-v0.1-package \
  --archive-path /tmp/cce-mvm-v0.1-package.tar.gz
```

Then enter the generated package directory and run:

```bash
python verify_package.py
```

The package verifier intentionally rejects unlisted files. Git metadata,
repository workflows, licenses, and source-development files therefore remain
outside the generated package.

## Publication blockers

- The author has not confirmed the final author name, affiliation, licenses, or
  repository URL.
- `CITATION.cff.template` and `LICENSE-MAP.template.md` are placeholders, not
  applied metadata or legal licenses.
- The generated reproducibility manifest still identifies an internal candidate.
- A clean public release and independent reproduction have not been completed.

Do not make this candidate public or describe it as an open-source release.

