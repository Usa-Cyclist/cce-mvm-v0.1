# CCE-MVM v0.1 reproducibility package publication gates

Status: open; this candidate must not be described as a final public release

## Required before public release

- [ ] The author selects and adds a code license.
- [ ] The public package is built from a clean, identified Git commit or release tag.
- [x] Python 3.9.6, 3.10.21, 3.11.16, 3.12.13, 3.13.15, and 3.14.7 pass internally on macOS arm64.
- [ ] The public release states only tested versions or adds a clean CI matrix for every claimed continuous Python/OS range.
- [ ] The package passes `python3 verify_package.py` in the release environment.
- [x] The internal candidate's packaged verifier tests reject an injected unlisted file, forbidden content, a broken relative reference, and a configuration-hash mismatch. Re-run this on the final release.
- [ ] The public status explicitly records human independent reproduction as either `not_completed_disclosed` or `completed_with_external_record`.
- [ ] If `completed_with_external_record` is selected, a separate reviewer has run the fixed archive using only `README.md`, and the external record identifies the archive SHA-256, environment, commands, failures, ambiguities, and author intervention.
- [ ] Final `SHA256SUMS` is regenerated after the release contents are frozen.
- [ ] `BUILD-METADATA.json` shows the intended release identifier and no unexplained dirty source state.
- [x] The internal candidate reports zero pending configuration hashes for all six experiment groups. Re-run this on the final release.
- [ ] The manuscript, specification, code, settings, output counts, and reported results agree.
- [ ] H1c-R and institutional or personal materials remain excluded.
- [ ] The repository and archival link used in the manuscript are publicly accessible.
- [ ] Citation information is added after the title, author list, and repository identifier are fixed.

## Meaning of the independent run

The independent reviewer is checking whether the computational artifacts can be rerun as described. This is not a review of clinical validity, ethics, law, or the lived experience of patients and families. Those require separate human review roles. An external AI execution is recorded as independent AI criticism or cross-environment technical evidence, not as independent human reproduction or academic peer review.

A completed human independent run is desirable evidence but is not a prerequisite for the first arXiv release. If no qualifying run exists, the package and manuscript must say so plainly and must not imply that independent reproduction was completed.

## Author-only decisions

The author must decide the license, release location, citation metadata, and sharing scope. Building this internal candidate does not authorize publication or external sharing.
