# CCE-MVM v0.1 independent reproduction record template

Status: immutable blank template; complete a copy outside the supplied package

This form records whether a person other than the CCE developer could verify the supplied package in a fresh folder or separate computer by following `README.md`. It is not a clinical, ethical, legal, or peer-review endorsement. Copy this template outside the extracted package before entering any result; do not edit the hashed template.

## 1. Reviewer and package

| Item | Record |
|---|---|
| Review ID or anonymous role label |  |
| Date |  |
| Package filename or location |  |
| Package SHA-256, if supplied as an archive |  |
| How the package was obtained |  |
| Relationship or potential conflict of interest |  |
| Permission to quote or publish this record | not requested / no / conditional / yes |

Do not enter patient information, clinical cases, workplace-confidential information, passwords, or other personal identifiers.

## 2. Environment

| Item | Record |
|---|---|
| Operating system and version |  |
| Hardware or architecture |  |
| Python command used |  |
| Python version |  |
| Internet connection required during verification | yes / no / unclear |
| Additional packages installed | none / list: |

## 3. First attempt using only README.md

| Check | Result |
|---|---|
| `python3 verify_package.py` started | pass / fail |
| Exact package inventory and privacy checks passed | pass / fail / unclear |
| SHA-256 files verified | pass / fail / unclear |
| Expected 16 recipient-verifier tests ran | pass / fail / unclear |
| Expected 96 core tests ran | pass / fail / unclear |
| Six experiment groups regenerated | pass / fail / unclear |
| Seventeen CSV/JSON outputs matched | pass / fail / unclear |
| H1c-R or institutional materials were absent | pass / fail / unclear |

Exact command:

```text

```

Exact final output or error:

```text

```

## 4. Ambiguities and intervention

1. Which instruction was unclear or incomplete?

2. Did you need to inspect files beyond README.md before the first successful run?

3. Did the author or developer give additional instructions, modify files, or troubleshoot during the run?

4. If intervention occurred, what was required before verification succeeded?

5. Did the verification overwrite any supplied canonical result files?

## 5. File and result observations

Record missing files, unexpected files, checksum problems, environment assumptions, nondeterministic output, or differences between documentation and implementation.

```text

```

## 6. Reproduction classification

Select the closest result.

- [ ] Reproduced independently on the first attempt using only README.md.
- [ ] Reproduced after clarification, without changing the model, code, settings, or expected outputs.
- [ ] Reproduced only after files or code were changed.
- [ ] Not reproduced.
- [ ] Inconclusive because the environment or record is incomplete.

Reason:

```text

```

## 7. Scope statement

By completing this record, the reviewer is not confirming that CCE predicts real human behaviour, improves care, is clinically safe, is legally valid, or is ethically correct. The record concerns only computational rerun and artifact consistency within the recorded environment. An AI model running the package, or the author repeating it on another machine, can be useful technical evidence but is not classified as independent human reproduction; that label requires a different person following the supplied package workflow and documenting intervention.
