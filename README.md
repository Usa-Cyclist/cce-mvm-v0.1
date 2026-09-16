# CCE-MVM v0.1

Research software accompanying **Computational Care Ecology: Synthetic Experiments and Internal Verification of CCE-MVM v0.1**, by Daiki Morimoto (Independent Researcher, Japan).

- Source repository: https://github.com/Usa-Cyclist/cce-mvm-v0.1
- Fixed release: https://github.com/Usa-Cyclist/cce-mvm-v0.1/releases/tag/v0.1

## Scope and limitations

This repository contains the frozen CCE-MVM v0.1 specification, Python standard-library implementation, tests, six synthetic experiment configurations, and 17 canonical output files. It contains no patient or human-participant data and no future empirical extension.

CCE-MVM v0.1 is an unvalidated research explanation model, not a clinical decision tool, capacity assessment, legal determination, medical device, or validated measure of personal sovereignty. Internal verification does not establish empirical, clinical, ethical, or external validity. Independent human reproduction has not been completed.

## Verify the source

```bash
python -m unittest discover -v -s cce -p 'test_*.py'
python -m unittest -v cce.tools.test_build_reproducibility_package_archive cce.tools.test_verify_public_release cce.tools.test_build_public_reproducibility_package
```

The first command runs 96 core tests; the second runs 16 release-tool tests. The CI workflow covers Ubuntu, macOS, and Windows with Python 3.9 through 3.14. Consult the CI logs for exact versions and the tested commit; a passing run on one commit is not evidence for a later commit.

## Fixed reproducibility package

Download `cce-mvm-v0.1-reproducibility.tar.gz` and its `.sha256` checksum from the fixed release. Check the archive checksum, extract it, and run from the extracted directory:

```bash
python verify_package.py
```

This checks the exact inventory, SHA-256 hashes, configuration and relative-path references, verifier tests, core tests, and reproduction of the 17 canonical outputs. The exact source commit is recorded in `BUILD-METADATA.json` as `source_git_head`. The release tag, CI run, build metadata, and checksum provide the version-specific evidence.

Historical internal manifests and notices remain unchanged under `cce/paper1/reproducibility/` for provenance. The original builder generates an internal candidate. The controlled public-package builder applies a separate authorized overlay that replaces internal release notices and adds licenses and citation metadata; it does not change the frozen scientific content.

## Licensing and citation

Python code and the CI workflow are licensed under Apache-2.0. Documentation, citation and release metadata, synthetic configurations, and synthetic outputs are licensed under CC-BY-4.0. See `LICENSE-MAP.md`, `LICENSES/`, and `CITATION.cff`. The manuscript has a separate distribution license.

Do not infer an arXiv identifier from this repository: one can be cited only after arXiv assigns it. The research-use warnings describe limitations and are not additional license restrictions.

Administrative publication preparation was authorized on 2026-09-16. The frozen model, test conditions, results, and claim boundaries are unchanged.
