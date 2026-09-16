# CCE-MVM v0.1 author-confirmed license map

Status: author decisions and release rights confirmed; license materials staged
locally; repository publication not authorized

The author confirmed on 2 September 2026 that the materials may be released
under the following selected licenses. This local staging record does not by
itself authorize repository publication or arXiv submission.

| Material | Selected license | Intended public-release paths |
|---|---|---|
| Python source, tests, and CI workflow | Apache License 2.0 (`Apache-2.0`) | `cce/**/*.py`, `verify_package.py`, `test_verify_package.py`, `.github/workflows/*.yml` |
| Specification, analytical notes, protocols, README files, safety notices, and other explanatory documents | Creative Commons Attribution 4.0 International (`CC-BY-4.0`) | `**/*.md`, except standard-license texts |
| Synthetic experiment configurations and generated outputs | Creative Commons Attribution 4.0 International (`CC-BY-4.0`) | `cce/experiments/config/**/*.json`, `cce/experiments/results/**/*.{csv,json}` |
| Citation and package metadata created for the release | Creative Commons Attribution 4.0 International (`CC-BY-4.0`) | `CITATION.cff`, `PACKAGE-MANIFEST.json`, `PUBLICATION-STATUS.md` |
| Paper deposited in arXiv | arXiv perpetual, non-exclusive license (`arxiv-perpetual-non-exclusive`) | selected in the arXiv submission form; not governed by the software repository license |
| Standard license texts | their own terms and verbatim legal text | `LICENSES/Apache-2.0.txt`, `LICENSES/CC-BY-4.0.txt` |

## Attribution and copyright

Creator and copyright holder confirmed for this release: Daiki Morimoto,
2026. AI systems are not authors or rightsholders.

## Safety statements are not additional license restrictions

CCE-MVM v0.1 is an unvalidated research explanation model. It is not a
clinical decision tool, capacity assessment, legal determination, medical
device, or validated measure of personal sovereignty. These scientific and
safety warnings must remain visible, but they do not add field-of-use
restrictions to Apache-2.0 or CC BY 4.0.

## Still required before publication

- create and verify the sanitized private repository;
- add its public URL, clean commit, release tag, and CI evidence;
- finalize `CITATION.cff` with the repository URL and release date;
- move the exact license texts and this map into their final repository paths;
- obtain separate authorization to make the repository public;
- verify the released files from an external, unauthenticated view.

