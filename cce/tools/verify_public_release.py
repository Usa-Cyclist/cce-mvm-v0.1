"""Fail-closed verification for an author-approved public CCE source release."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set


REQUIRED_BASE_TRUE_FIELDS = (
    "author_decisions_applied",
    "license_applied",
    "citation_finalized",
    "clean_commit_confirmed",
    "ci_passed",
    "publication_authorized",
)
REQUIRED_FINAL_TRUE_FIELDS = (
    "reproducibility_package_verified",
    "final_content_scan_passed",
)
REQUIRED_TEXT_FIELDS = (
    "author_name",
    "affiliation_display",
    "repository_url",
    "paper_license",
    "code_license",
    "documentation_license",
    "synthetic_output_license",
    "expected_git_head",
    "ci_run_url",
    "ci_git_head",
    "author_approval_utc",
)
ALLOWED_PAPER_LICENSES = {
    "arxiv-perpetual-non-exclusive",
    "CC-BY-4.0",
}
ALLOWED_CODE_LICENSES = {"Apache-2.0", "MIT"}
ALLOWED_CONTENT_LICENSES = {"CC-BY-4.0", "CC0-1.0"}
FORBIDDEN_PATHS = {
    Path("DRAFT" + "-NOT-FOR-PUBLICATION.md"),
    Path("CITATION.cff.template"),
    Path("LICENSE-MAP.template.md"),
    Path("PUBLIC-SOURCE-CANDIDATE-METADATA.json"),
}
FORBIDDEN_SUFFIXES = {
    ".docx",
    ".xlsx",
    ".pages",
    ".zip",
    ".tar",
    ".gz",
}
TEXT_SUFFIXES = {
    ".cff",
    ".csv",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
PLACEHOLDER_PATTERN = re.compile(r"__[A-Z0-9][A-Z0-9_]*__")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_HEAD_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


def load_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def string_list(record: Mapping[str, object], key: str) -> List[str]:
    value = record.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings")
    return value


def safe_relative_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if not raw_path or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe relative path: {raw_path!r}")
    return path


def git_output(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def repository_files(repository: Path) -> Set[Path]:
    files: Set[Path] = set()
    for path in repository.rglob("*"):
        relative = path.relative_to(repository)
        if relative.parts and relative.parts[0] == ".git":
            continue
        if path.is_symlink():
            raise ValueError(f"symbolic links are forbidden: {relative}")
        if path.is_file():
            files.add(relative)
    return files


def validate_text_files(repository: Path, files: Iterable[Path]) -> None:
    for relative in files:
        if relative.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = (repository / relative).read_text(encoding="utf-8")
        if PLACEHOLDER_PATTERN.search(text):
            raise ValueError(f"unresolved placeholder in {relative}")
        lowered = text.lower()
        if ("draft" + "-not-for-publication") in lowered:
            raise ValueError(f"draft publication marker in {relative}")
        if ("status: private draft;" + " not licensed") in lowered:
            raise ValueError(f"private-draft status in {relative}")


def validate_citation(repository: Path, record: Mapping[str, object]) -> None:
    text = (repository / "CITATION.cff").read_text(encoding="utf-8")
    required_fragments = (
        "cff-version:",
        "title:",
        "authors:",
        "repository-code:",
        "license:",
        str(record["repository_url"]),
        str(record["code_license"]),
    )
    missing = [fragment for fragment in required_fragments if fragment not in text]
    if missing:
        raise ValueError("CITATION.cff is incomplete: " + ", ".join(missing))
    for token in str(record["author_name"]).split():
        if token not in text:
            raise ValueError(f"CITATION.cff does not contain author-name token: {token}")


def validate_license_map(repository: Path, record: Mapping[str, object]) -> None:
    text = (repository / "LICENSE-MAP.md").read_text(encoding="utf-8")
    for key in (
        "paper_license",
        "code_license",
        "documentation_license",
        "synthetic_output_license",
    ):
        if str(record[key]) not in text:
            raise ValueError(f"LICENSE-MAP.md does not mention {key}")


def validate_public_release(
    repository: Path,
    gate_record: Path,
    reproducibility_archive: Optional[Path] = None,
    phase: str = "final",
) -> Dict[str, object]:
    repository = repository.resolve()
    record = load_json(gate_record.resolve())
    if phase not in {"prepackage", "final"}:
        raise ValueError("phase must be prepackage or final")
    if record.get("schema_version") != "0.1":
        raise ValueError("unsupported release-gate schema")
    if record.get("status") != "public_release_candidate":
        raise ValueError("status must be public_release_candidate")

    for key in REQUIRED_BASE_TRUE_FIELDS:
        if record.get(key) is not True:
            raise ValueError(f"{key} must be true")
    if phase == "prepackage":
        for key in REQUIRED_FINAL_TRUE_FIELDS:
            if record.get(key) is not False:
                raise ValueError(f"{key} must remain false before package verification")
    else:
        for key in REQUIRED_FINAL_TRUE_FIELDS:
            if record.get(key) is not True:
                raise ValueError(f"{key} must be true")
    for key in REQUIRED_TEXT_FIELDS:
        if not isinstance(record.get(key), str) or not str(record[key]).strip():
            raise ValueError(f"{key} must be a non-empty string")

    if record["paper_license"] not in ALLOWED_PAPER_LICENSES:
        raise ValueError("paper_license is not an allowed choice")
    if record["code_license"] not in ALLOWED_CODE_LICENSES:
        raise ValueError("code_license is not an allowed choice")
    if record["documentation_license"] not in ALLOWED_CONTENT_LICENSES:
        raise ValueError("documentation_license is not an allowed choice")
    if record["synthetic_output_license"] not in ALLOWED_CONTENT_LICENSES:
        raise ValueError("synthetic_output_license is not an allowed choice")
    if not str(record["repository_url"]).startswith("https://"):
        raise ValueError("repository_url must use https")
    if not GIT_HEAD_PATTERN.fullmatch(str(record["expected_git_head"])):
        raise ValueError("expected_git_head must be a full hexadecimal commit id")
    if not str(record["ci_run_url"]).startswith("https://"):
        raise ValueError("ci_run_url must use https")
    if not GIT_HEAD_PATTERN.fullmatch(str(record["ci_git_head"])):
        raise ValueError("ci_git_head must be a full hexadecimal commit id")
    if record["ci_git_head"] != record["expected_git_head"]:
        raise ValueError("ci_git_head must match expected_git_head")
    ci_jobs_expected = record.get("ci_jobs_expected")
    ci_jobs_passed = record.get("ci_jobs_passed")
    if (
        not isinstance(ci_jobs_expected, int)
        or isinstance(ci_jobs_expected, bool)
        or ci_jobs_expected < 1
    ):
        raise ValueError("ci_jobs_expected must be a positive integer")
    if (
        not isinstance(ci_jobs_passed, int)
        or isinstance(ci_jobs_passed, bool)
        or ci_jobs_passed != ci_jobs_expected
    ):
        raise ValueError("ci_jobs_passed must equal ci_jobs_expected")
    approval_timestamp = str(record["author_approval_utc"])
    if not approval_timestamp.endswith("Z"):
        raise ValueError("author_approval_utc must be an explicit UTC timestamp ending in Z")
    try:
        approval_time = datetime.fromisoformat(approval_timestamp[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("author_approval_utc is not a valid ISO 8601 timestamp") from error
    if approval_time.utcoffset() != timedelta(0):
        raise ValueError("author_approval_utc must use UTC")

    if phase == "prepackage":
        if reproducibility_archive is not None:
            raise ValueError("prepackage verification does not accept an archive")
        if record.get("reproducibility_archive") is not None or record.get(
            "reproducibility_archive_sha256"
        ) is not None:
            raise ValueError("prepackage gate must leave archive name and SHA-256 null")
    else:
        for key in ("reproducibility_archive", "reproducibility_archive_sha256"):
            if not isinstance(record.get(key), str) or not str(record[key]).strip():
                raise ValueError(f"{key} must be a non-empty string in final phase")
        if reproducibility_archive is None:
            raise ValueError("final verification requires a reproducibility archive")
        reproducibility_archive = reproducibility_archive.resolve()
        if not reproducibility_archive.is_file():
            raise ValueError("reproducibility archive does not exist")
        if reproducibility_archive.name != record["reproducibility_archive"]:
            raise ValueError("reproducibility archive name does not match gate record")
        if not SHA256_PATTERN.fullmatch(str(record["reproducibility_archive_sha256"])):
            raise ValueError("reproducibility_archive_sha256 must be SHA-256")
        if sha256_file(reproducibility_archive) != record["reproducibility_archive_sha256"]:
            raise ValueError("reproducibility archive SHA-256 mismatch")

    platforms = string_list(record, "ci_platforms_verified")
    python_versions = string_list(record, "ci_python_versions_verified")
    if len(set(platforms)) < 3:
        raise ValueError("at least three distinct CI platforms must be recorded")
    if len(set(python_versions)) < 2:
        raise ValueError("at least two distinct Python versions must be recorded")

    files = repository_files(repository)
    if any(path in files for path in FORBIDDEN_PATHS):
        raise ValueError("draft or template release files remain in repository")
    forbidden_suffixes = sorted(
        path.as_posix() for path in files if path.suffix.lower() in FORBIDDEN_SUFFIXES
    )
    if forbidden_suffixes:
        raise ValueError("forbidden release artifacts: " + ", ".join(forbidden_suffixes))

    required_files = [safe_relative_path(path) for path in string_list(record, "required_files")]
    if len(set(required_files)) != len(required_files):
        raise ValueError("required_files contains duplicates")
    missing_files = [path.as_posix() for path in required_files if path not in files]
    if missing_files:
        raise ValueError("missing required release files: " + ", ".join(missing_files))

    raw_license_hashes = record.get("license_file_sha256")
    if not isinstance(raw_license_hashes, dict) or not raw_license_hashes:
        raise ValueError("license_file_sha256 must be a non-empty object")
    for raw_path, expected_hash in raw_license_hashes.items():
        if not isinstance(raw_path, str) or not isinstance(expected_hash, str):
            raise ValueError("license_file_sha256 must map paths to SHA-256 strings")
        path = safe_relative_path(raw_path)
        if path not in files:
            raise ValueError(f"missing declared license file: {path}")
        if not SHA256_PATTERN.fullmatch(expected_hash):
            raise ValueError(f"invalid license SHA-256 for {path}")
        if sha256_file(repository / path) != expected_hash:
            raise ValueError(f"license SHA-256 mismatch for {path}")

    validate_text_files(repository, files)
    validate_citation(repository, record)
    validate_license_map(repository, record)

    if not (repository / ".git").exists():
        raise ValueError("repository must be a Git working tree")
    actual_head = git_output(repository, "rev-parse", "HEAD")
    if actual_head != record["expected_git_head"]:
        raise ValueError("Git HEAD does not match expected_git_head")
    if git_output(repository, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Git working tree is not clean")

    return {
        "status": (
            "verified_public_repository_prepackage"
            if phase == "prepackage"
            else "verified_public_release_candidate"
        ),
        "file_count": len(files),
        "git_head": actual_head,
        "author_name": record["author_name"],
        "publication_authorized": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify an author-approved public CCE source release."
    )
    parser.add_argument("--repository-dir", required=True, type=Path)
    parser.add_argument("--gates", required=True, type=Path)
    parser.add_argument("--phase", choices=("prepackage", "final"), default="final")
    parser.add_argument("--reproducibility-archive", type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        result = validate_public_release(
            arguments.repository_dir,
            arguments.gates,
            arguments.reproducibility_archive,
            arguments.phase,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"PUBLIC RELEASE VERIFICATION FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
