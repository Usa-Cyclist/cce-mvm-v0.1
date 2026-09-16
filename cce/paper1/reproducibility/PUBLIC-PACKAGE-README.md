# CCE-MVM v0.1 reproducibility package

This fixed artifact accompanies **Computational Care Ecology: Synthetic Experiments and Internal Verification of CCE-MVM v0.1**, by Daiki Morimoto (Independent Researcher, Japan).

It contains the frozen model specification, implementation, six synthetic experiment configurations, and 17 canonical output files. It contains no patient or human-participant data. CCE-MVM v0.1 is an unvalidated research explanation model, not a clinical decision tool or validated sovereignty scale. Computational consistency does not establish real-world efficacy, safety, or external validity. Independent human reproduction has not been completed.

## Verification

After checking the downloaded archive against the adjacent SHA-256 checksum and extracting it, run:

```bash
python verify_package.py
```

Use Python with its standard library. The verifier checks exact file inventory, hashes, configurations, relative-path references, verifier tests, 96 core tests, and reproduction of six experiment groups with 17 canonical output files. Additional unlisted files cause verification to fail.

## Source and version

- Repository: https://github.com/Usa-Cyclist/cce-mvm-v0.1
- Fixed release: https://github.com/Usa-Cyclist/cce-mvm-v0.1/releases/tag/v0.1
- Model and release version: v0.1.
- Exact source commit: `BUILD-METADATA.json` → `source_git_head`.
- Archive integrity: SHA-256 checksum published beside the archive.
- CI scope: Ubuntu, macOS, Windows; Python 3.9–3.14. Exact versions and commit are recorded in the linked release CI run.

The commit is recorded in generated build metadata rather than inserted into a source file that would itself change that commit. Publication metadata does not revise the frozen model or results.

## Licenses and citation

See `LICENSE-MAP.md`, `LICENSES/`, `CITATION.cff`, and `PUBLICATION-STATUS.md`. Code is Apache-2.0; documentation and synthetic outputs are CC-BY-4.0. The manuscript is separately licensed. No arXiv identifier is asserted before one is assigned.
