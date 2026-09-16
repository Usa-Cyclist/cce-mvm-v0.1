"""Verify a built CCE-MVM v0.1 reproducibility package without network access."""

from __future__ import annotations

import filecmp
import hashlib
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Set, Tuple
from urllib.parse import unquote, urlsplit


PACKAGE_ROOT = Path(__file__).resolve().parent
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
INLINE_CODE_PATTERN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
FENCED_CODE_PATTERN = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
REFERENCE_SUFFIXES = {".csv", ".json", ".md", ".py", ".txt"}
TEXT_SUFFIXES = REFERENCE_SUFFIXES
INLINE_COMMAND_NAMES = {
    "cp",
    "git",
    "python",
    "python3",
    "python.exe",
    "py",
}
CHECKSUM_PATH = Path("SHA256SUMS")
BUILD_METADATA_PATH = Path("BUILD-METADATA.json")
MANIFEST_PATH = Path("PACKAGE-MANIFEST.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_python_version(version: Tuple[int, ...]) -> None:
    if tuple(version[:2]) < (3, 9):
        raise ValueError("Python 3.9 or newer is required")


def safe_relative_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe package path: {raw_path!r}")
    return path


def load_manifest(package_root: Path = PACKAGE_ROOT) -> Dict[str, object]:
    with (package_root / MANIFEST_PATH).open(
        "r", encoding="utf-8"
    ) as stream:
        manifest = json.load(stream)
    if not isinstance(manifest, dict):
        raise ValueError("PACKAGE-MANIFEST.json must contain an object")
    return manifest


def manifest_destinations(manifest: Mapping[str, object]) -> Set[Path]:
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest entries must be a non-empty list")

    destinations: Set[Path] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"manifest entry {index} is not an object")
        if not isinstance(entry.get("destination"), str):
            raise ValueError(f"manifest entry {index} has no string destination")
        destination = safe_relative_path(entry["destination"])
        if destination in destinations:
            raise ValueError(f"duplicate manifest destination: {destination}")
        destinations.add(destination)

    if MANIFEST_PATH not in destinations:
        raise ValueError("PACKAGE-MANIFEST.json must be a manifest destination")
    return destinations


def allowed_mutable_files(
    manifest: Mapping[str, object], destinations: Set[Path]
) -> Dict[Path, Mapping[str, object]]:
    raw_records = manifest.get("allowed_mutable_files", [])
    if not isinstance(raw_records, list):
        raise ValueError("allowed_mutable_files must be a list")

    records: Dict[Path, Mapping[str, object]] = {}
    for index, record in enumerate(raw_records):
        if not isinstance(record, dict):
            raise ValueError(f"allowed mutable file {index} is not an object")
        raw_path = record.get("path")
        raw_template = record.get("template")
        if not isinstance(raw_path, str) or not isinstance(raw_template, str):
            raise ValueError("allowed mutable files require path and template strings")
        path = safe_relative_path(raw_path)
        template = safe_relative_path(raw_template)
        if path in records:
            raise ValueError(f"duplicate allowed mutable path: {path}")
        if path in destinations or path in {BUILD_METADATA_PATH, CHECKSUM_PATH}:
            raise ValueError(f"mutable path overlaps an immutable package file: {path}")
        if template not in destinations:
            raise ValueError(f"mutable file template is not packaged: {template}")
        if record.get("purpose") != "independent_reproduction_record":
            raise ValueError(
                "unsupported mutable file purpose for "
                f"{path}: {record.get('purpose')!r}"
            )
        if path.suffix.lower() != ".md":
            raise ValueError(f"mutable reproduction record must be Markdown: {path}")
        records[path] = record
    return records


def package_files(package_root: Path) -> Set[Path]:
    files: Set[Path] = set()
    for path in package_root.rglob("*"):
        relative = path.relative_to(package_root)
        if path.is_symlink():
            raise ValueError(
                f"symbolic links are not permitted in the package: {relative}"
            )
        if path.is_file():
            files.add(relative)
    return files


def verify_inventory(manifest: Mapping[str, object], package_root: Path) -> int:
    destinations = manifest_destinations(manifest)
    mutable = set(allowed_mutable_files(manifest, destinations))
    required = destinations | {BUILD_METADATA_PATH, CHECKSUM_PATH}
    actual = package_files(package_root)

    missing = required - actual
    if missing:
        names = ", ".join(sorted(path.as_posix() for path in missing))
        raise FileNotFoundError(f"required package files are missing: {names}")

    unexpected = actual - required - mutable
    if unexpected:
        names = ", ".join(sorted(path.as_posix() for path in unexpected))
        raise ValueError(f"unlisted package files are present: {names}")
    return len(actual)


def parse_checksums(package_root: Path = PACKAGE_ROOT) -> List[Tuple[str, Path]]:
    checksum_file = package_root / CHECKSUM_PATH
    records = []
    for line_number, raw_line in enumerate(
        checksum_file.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line:
            continue
        try:
            expected, raw_path = raw_line.split("  ", 1)
        except ValueError as error:
            raise ValueError(f"malformed SHA256SUMS line {line_number}") from error
        if not SHA256_PATTERN.fullmatch(expected):
            raise ValueError(f"invalid SHA-256 on line {line_number}")
        records.append((expected, safe_relative_path(raw_path)))
    if not records:
        raise ValueError("SHA256SUMS is empty")
    return records


def verify_hashes(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> int:
    records = parse_checksums(package_root)
    listed_paths = set()
    for expected, relative in records:
        if relative in listed_paths:
            raise ValueError(f"duplicate checksum path: {relative}")
        listed_paths.add(relative)
        path = package_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"checksum target is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(f"checksum mismatch: {relative}")

    destinations = manifest_destinations(manifest)
    mutable = set(allowed_mutable_files(manifest, destinations))
    expected_hashed_paths = destinations | {BUILD_METADATA_PATH}
    overlap = mutable & listed_paths
    if overlap:
        names = ", ".join(sorted(path.as_posix() for path in overlap))
        raise ValueError(f"mutable files must not be covered by SHA256SUMS: {names}")
    if listed_paths != expected_hashed_paths:
        missing = expected_hashed_paths - listed_paths
        extra = listed_paths - expected_hashed_paths
        details = []
        if missing:
            details.append(
                "missing=" + ",".join(sorted(path.as_posix() for path in missing))
            )
        if extra:
            details.append(
                "extra=" + ",".join(sorted(path.as_posix() for path in extra))
            )
        raise ValueError(
            "SHA256SUMS does not exactly match immutable files: "
            + "; ".join(details)
        )
    return len(records)


def validate_no_forbidden_files(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> None:
    raw_fragments = manifest.get("forbidden_path_fragments", [])
    raw_suffixes = manifest.get("forbidden_suffixes", [])
    raw_patterns = manifest.get("forbidden_content_patterns", [])
    if not all(
        isinstance(values, list)
        for values in (raw_fragments, raw_suffixes, raw_patterns)
    ):
        raise ValueError("forbidden path, suffix, and content rules must be lists")
    fragments = [
        str(value).casefold() for value in raw_fragments
    ]
    suffixes = {
        str(value).casefold() for value in raw_suffixes
    }
    content_patterns = [
        str(value).casefold() for value in raw_patterns
    ]
    if any(not value for value in fragments + list(suffixes) + content_patterns):
        raise ValueError("forbidden rules must not contain empty strings")

    for path in package_root.rglob("*"):
        if path.is_symlink():
            raise ValueError(
                "symbolic links are not permitted in the package: "
                f"{path.relative_to(package_root)}"
            )
        if not path.is_file():
            continue
        relative = path.relative_to(package_root)
        normalized = relative.as_posix().casefold()
        for fragment in fragments:
            if fragment in normalized:
                raise ValueError(f"forbidden path is present: {relative}")
        if relative.suffix.casefold() in suffixes:
            raise ValueError(f"forbidden file type is present: {relative}")
        if relative == MANIFEST_PATH:
            continue
        if relative.suffix.casefold() in TEXT_SUFFIXES:
            content = path.read_text(encoding="utf-8").casefold()
            for pattern in content_patterns:
                if pattern in content:
                    raise ValueError(
                        "forbidden content pattern "
                        f"{pattern!r} is present in {relative}"
                    )


def validate_build_metadata(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> Dict[str, object]:
    with (package_root / BUILD_METADATA_PATH).open("r", encoding="utf-8") as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError("BUILD-METADATA.json must contain an object")

    for field in ("package_name", "release_status"):
        if metadata.get(field) != manifest.get(field):
            raise ValueError(f"build metadata {field} does not match the manifest")

    expected_source_count = len(manifest_destinations(manifest))
    if metadata.get("source_file_count") != expected_source_count:
        raise ValueError(
            "build metadata source_file_count does not match manifest entries"
        )

    for field in (
        "python_version",
        "python_implementation",
        "platform",
        "built_at_utc",
    ):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"build metadata {field} must be a non-empty string")
    try:
        built_at = datetime.fromisoformat(str(metadata["built_at_utc"]))
    except ValueError as error:
        raise ValueError("build metadata built_at_utc is not ISO-8601") from error
    if built_at.tzinfo is None:
        raise ValueError("build metadata built_at_utc must include a timezone")

    for field in (
        "source_git_dirty",
        "license_included",
        "independent_reproduction_completed",
    ):
        if not isinstance(metadata.get(field), bool):
            raise ValueError(f"build metadata {field} must be boolean")

    git_head = metadata.get("source_git_head")
    if git_head is not None and (
        not isinstance(git_head, str) or not GIT_OBJECT_PATTERN.fullmatch(git_head)
    ):
        raise ValueError("build metadata source_git_head is not a Git object ID")
    return metadata


def validate_release_gates(
    manifest: Mapping[str, object],
    metadata: Mapping[str, object],
    config_hashes_pending: int,
) -> None:
    if manifest.get("release_status") == "internal_candidate":
        return
    if manifest.get("release_status") != "public_release":
        raise ValueError("unsupported non-internal release_status")
    failures = []
    if manifest.get("publication_authorized") is not True:
        failures.append("publication_authorized must be true")
    if metadata.get("license_included") is not True:
        failures.append("license_included must be true")
    if metadata.get("source_git_dirty") is not False:
        failures.append("source_git_dirty must be false")
    independent_status = manifest.get("independent_reproduction_status")
    independent_completed = metadata.get("independent_reproduction_completed")
    if independent_status == "completed_with_external_record":
        if independent_completed is not True:
            failures.append(
                "completed independent reproduction requires metadata true"
            )
    elif independent_status == "not_completed_disclosed":
        if independent_completed is not False:
            failures.append(
                "disclosed incomplete reproduction requires metadata false"
            )
    else:
        failures.append("independent_reproduction_status is invalid")
    if config_hashes_pending != 0:
        failures.append("config_hashes_pending must be zero")
    if failures:
        raise ValueError("release gates failed: " + "; ".join(failures))


def _reference_text_without_fences(text: str) -> str:
    return FENCED_CODE_PATTERN.sub("", text)


def _clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    return target.split(maxsplit=1)[0]


def _is_local_reference(
    raw_reference: str, reference_suffixes: Set[str] = REFERENCE_SUFFIXES
) -> bool:
    reference = raw_reference.strip()
    if not reference or reference.startswith(("#", "/", "//")):
        return False
    if reference.split(maxsplit=1)[0].casefold() in INLINE_COMMAND_NAMES:
        return False
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc:
        return False
    suffix = Path(unquote(parsed.path)).suffix.casefold()
    return suffix in reference_suffixes


def extract_relative_references(
    text: str, reference_suffixes: Set[str] = REFERENCE_SUFFIXES
) -> Set[str]:
    searchable = _reference_text_without_fences(text)
    references = {
        _clean_link_target(target)
        for target in MARKDOWN_LINK_PATTERN.findall(searchable)
    }
    references.update(
        value.strip()
        for value in INLINE_CODE_PATTERN.findall(searchable)
    )
    return {
        reference
        for reference in references
        if _is_local_reference(reference, reference_suffixes)
    }


def resolve_reference(source: Path, raw_reference: str) -> Path:
    parsed = urlsplit(raw_reference)
    raw_path = unquote(parsed.path)
    normalized = posixpath.normpath((source.parent / raw_path).as_posix())
    return safe_relative_path(normalized)


def relative_reference_exemptions(
    manifest: Mapping[str, object], destinations: Set[Path]
) -> Dict[Tuple[Path, str], Mapping[str, object]]:
    raw_exemptions = manifest.get("relative_reference_exemptions", [])
    if not isinstance(raw_exemptions, list):
        raise ValueError("relative_reference_exemptions must be a list")
    exemptions: Dict[Tuple[Path, str], Mapping[str, object]] = {}
    valid_classes = {
        "intentionally_not_packaged",
        "generic_filename",
        "historical_reference",
    }
    for index, exemption in enumerate(raw_exemptions):
        if not isinstance(exemption, dict):
            raise ValueError(f"relative reference exemption {index} is not an object")
        raw_source = exemption.get("source")
        reference = exemption.get("reference")
        reason = exemption.get("reason")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (raw_source, reference, reason)
        ):
            raise ValueError(
                "relative reference exemptions require source, reference, and reason"
            )
        source = safe_relative_path(raw_source)
        if source not in destinations:
            raise ValueError(f"reference exemption source is not packaged: {source}")
        if exemption.get("classification") not in valid_classes:
            raise ValueError(f"invalid reference exemption classification for {source}")
        key = (source, reference)
        if key in exemptions:
            raise ValueError(f"duplicate relative reference exemption: {key}")
        exemptions[key] = exemption
    return exemptions


def validate_relative_references(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> int:
    destinations = manifest_destinations(manifest)
    mutable = set(allowed_mutable_files(manifest, destinations))
    known_paths = destinations | {BUILD_METADATA_PATH, CHECKSUM_PATH} | mutable
    exemptions = relative_reference_exemptions(manifest, destinations)
    raw_forbidden_suffixes = manifest.get("forbidden_suffixes", [])
    if not isinstance(raw_forbidden_suffixes, list):
        raise ValueError("forbidden_suffixes must be a list")
    reference_suffixes = REFERENCE_SUFFIXES | {
        str(value).casefold() for value in raw_forbidden_suffixes
    }
    consumed: Set[Tuple[Path, str]] = set()
    checked = 0
    missing = []

    for source in sorted(destinations):
        if source.suffix.casefold() != ".md":
            continue
        text = (package_root / source).read_text(encoding="utf-8")
        for reference in sorted(
            extract_relative_references(text, reference_suffixes)
        ):
            checked += 1
            target = resolve_reference(source, reference)
            if target in known_paths:
                continue
            key = (source, reference)
            if key in exemptions:
                consumed.add(key)
                continue
            missing.append(f"{source}:{reference}->{target}")

    stale = set(exemptions) - consumed
    if stale:
        names = ", ".join(
            sorted(f"{source}:{reference}" for source, reference in stale)
        )
        raise ValueError(f"unused relative reference exemptions: {names}")
    if missing:
        raise FileNotFoundError(
            "unresolved packaged relative references: " + ", ".join(missing)
        )
    return checked


def validate_experiment_provenance(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> Tuple[int, int, int]:
    experiments = manifest.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("experiment configuration is missing")

    metadata_checked = 0
    config_hashes_checked = 0
    config_hashes_pending = 0
    for experiment in experiments:
        if not isinstance(experiment, dict):
            raise ValueError("experiment entry is invalid")
        experiment_id = str(experiment.get("id", ""))
        if not experiment_id:
            raise ValueError("experiment id is missing")
        saved_dir = safe_relative_path(str(experiment.get("saved_result_dir", "")))
        file_names = experiment.get("files")
        if (
            not isinstance(file_names, list)
            or not file_names
            or any(not isinstance(name, str) for name in file_names)
        ):
            raise ValueError(f"experiment {experiment_id} has no declared files")
        declared = [safe_relative_path(str(name)) for name in file_names]
        if len(set(declared)) != len(declared):
            raise ValueError(f"experiment {experiment_id} has duplicate files")

        raw_metadata_file = experiment.get("metadata_file", "metadata.json")
        metadata_file = safe_relative_path(str(raw_metadata_file))
        if metadata_file not in declared:
            raise ValueError(
                f"experiment {experiment_id} metadata file is not declared"
            )
        metadata_path = package_root / saved_dir / metadata_file
        with metadata_path.open("r", encoding="utf-8") as stream:
            metadata = json.load(stream)
        if not isinstance(metadata, dict):
            raise ValueError(f"experiment {experiment_id} metadata is not an object")

        required_metadata = experiment.get("required_metadata", {})
        if not isinstance(required_metadata, dict):
            raise ValueError(f"experiment {experiment_id} required_metadata is invalid")
        for field, expected in required_metadata.items():
            if metadata.get(field) != expected:
                raise ValueError(
                    f"experiment {experiment_id} metadata {field} does not match"
                )

        expected_output_names = {
            path.as_posix() for path in declared if path != metadata_file
        }
        metadata_output_names = metadata.get("files")
        if not isinstance(metadata_output_names, list) or {
            str(name) for name in metadata_output_names
        } != expected_output_names:
            raise ValueError(
                f"experiment {experiment_id} metadata files do not match the manifest"
            )
        metadata_checked += 1

        raw_config_path = experiment.get("config_path")
        if raw_config_path is not None:
            config_path = package_root / safe_relative_path(str(raw_config_path))
            field = str(experiment.get("config_sha256_field", "config_sha256"))
            declared_hash = metadata.get(field)
            hash_required = experiment.get("config_sha256_required", True)
            if not isinstance(hash_required, bool):
                raise ValueError(
                    f"experiment {experiment_id} config_sha256_required is not boolean"
                )
            if declared_hash is None and not hash_required:
                config_hashes_pending += 1
                continue
            if not isinstance(declared_hash, str) or not SHA256_PATTERN.fullmatch(
                declared_hash
            ):
                raise ValueError(
                    f"experiment {experiment_id} has no valid {field} provenance"
                )
            if sha256_file(config_path) != declared_hash:
                raise ValueError(
                    f"experiment {experiment_id} config SHA-256 does not match"
                )
            config_hashes_checked += 1
    return metadata_checked, config_hashes_checked, config_hashes_pending


def run_command(
    arguments: Iterable[str], package_root: Path = PACKAGE_ROOT
) -> str:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        list(arguments),
        cwd=str(package_root),
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(arguments)}):\n{completed.stdout}"
        )
    return completed.stdout


def run_test_modules(
    manifest: Mapping[str, object],
    *,
    modules_field: str,
    count_field: str,
    package_root: Path = PACKAGE_ROOT,
) -> int:
    modules = manifest.get(modules_field)
    expected_count = manifest.get(count_field)
    if not isinstance(modules, list) or not isinstance(expected_count, int):
        raise ValueError(f"test configuration is invalid: {modules_field}")
    output = run_command(
        [sys.executable, "-m", "unittest", "-v", *modules], package_root
    )
    match = re.search(r"Ran\s+(\d+)\s+tests?", output)
    if not match:
        raise ValueError("could not determine the unittest count")
    actual_count = int(match.group(1))
    if actual_count != expected_count:
        raise ValueError(
            f"expected {expected_count} tests for {modules_field} "
            f"but unittest ran {actual_count}"
        )
    skipped = re.search(r"skipped\s*=\s*(\d+)", output)
    if skipped and int(skipped.group(1)) != 0:
        raise ValueError(
            f"{modules_field} reported {int(skipped.group(1))} skipped tests"
        )
    return actual_count


def run_core_tests(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> int:
    return run_test_modules(
        manifest,
        modules_field="core_test_modules",
        count_field="expected_core_test_count",
        package_root=package_root,
    )


def run_verifier_tests(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> int:
    return run_test_modules(
        manifest,
        modules_field="verifier_test_modules",
        count_field="expected_verifier_test_count",
        package_root=package_root,
    )


def compare_experiments(
    manifest: Mapping[str, object], package_root: Path = PACKAGE_ROOT
) -> Tuple[int, int]:
    experiments = manifest.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("experiment configuration is missing")

    compared_files = 0
    with tempfile.TemporaryDirectory(prefix="cce-mvm-reproduction-") as temporary:
        temporary_root = Path(temporary)
        for experiment in experiments:
            if not isinstance(experiment, dict):
                raise ValueError("experiment entry is invalid")
            experiment_id = str(experiment["id"])
            module = str(experiment["module"])
            saved_dir = package_root / safe_relative_path(
                str(experiment["saved_result_dir"])
            )
            file_names = experiment.get("files")
            if not isinstance(file_names, list) or not file_names:
                raise ValueError(f"experiment {experiment_id} has no declared files")

            generated_dir = temporary_root / experiment_id
            run_command(
                [
                    sys.executable,
                    "-m",
                    module,
                    "--output-dir",
                    str(generated_dir),
                ],
                package_root,
            )
            declared = {safe_relative_path(str(name)) for name in file_names}
            generated = {
                path.relative_to(generated_dir)
                for path in generated_dir.rglob("*")
                if path.is_file()
            }
            if generated != declared:
                raise ValueError(
                    f"generated files for {experiment_id} do not match the manifest: "
                    f"generated={sorted(path.as_posix() for path in generated)}, "
                    f"declared={sorted(path.as_posix() for path in declared)}"
                )
            for relative in sorted(declared):
                expected = saved_dir / relative
                actual = generated_dir / relative
                if not expected.is_file():
                    raise FileNotFoundError(
                        "saved canonical output is missing: "
                        f"{expected.relative_to(package_root)}"
                    )
                if not filecmp.cmp(expected, actual, shallow=False):
                    raise ValueError(
                        f"regenerated output differs for {experiment_id}: {relative}"
                    )
                compared_files += 1
    return len(experiments), compared_files


def main() -> int:
    try:
        validate_python_version(sys.version_info[:3])
        manifest = load_manifest()
        inventory_count = verify_inventory(manifest, PACKAGE_ROOT)
        validate_no_forbidden_files(manifest)
        hash_count = verify_hashes(manifest)
        build_metadata = validate_build_metadata(manifest)
        reference_count = validate_relative_references(manifest)
        (
            metadata_count,
            config_hash_count,
            config_hash_pending_count,
        ) = validate_experiment_provenance(manifest)
        validate_release_gates(
            manifest, build_metadata, config_hash_pending_count
        )
        verifier_test_count = run_verifier_tests(manifest)
        core_test_count = run_core_tests(manifest)
        experiment_count, compared_file_count = compare_experiments(manifest)
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as error:
        print(f"VERIFICATION FAILED: {error}", file=sys.stderr)
        return 1

    result = {
        "status": (
            "verified"
            if config_hash_pending_count == 0
            else "verified_internal_with_pending_provenance"
        ),
        "release_status": manifest.get("release_status"),
        "package_files": inventory_count,
        "sha256_files": hash_count,
        "source_git_head": build_metadata.get("source_git_head"),
        "source_git_dirty": build_metadata.get("source_git_dirty"),
        "relative_references_checked": reference_count,
        "experiment_metadata_checked": metadata_count,
        "config_hashes_checked": config_hash_count,
        "config_hashes_pending": config_hash_pending_count,
        "verifier_tests": verifier_test_count,
        "core_tests": core_test_count,
        "experiment_groups": experiment_count,
        "regenerated_files_compared": compared_file_count,
        "independent_reproduction": False,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
