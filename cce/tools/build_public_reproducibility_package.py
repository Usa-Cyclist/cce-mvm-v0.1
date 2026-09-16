"""Build a public CCE reproducibility package from an authorized clean repository."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Dict, Iterable, List, Mapping, Set, Tuple

try:
    from cce.tools.build_reproducibility_package import (
        create_portable_archive,
        load_source_only_forbidden_patterns,
        safe_relative_path,
        sha256_file,
        validate_destination,
        validate_text_content,
    )
    from cce.tools.verify_public_release import validate_public_release
except ModuleNotFoundError:  # Direct execution from cce/tools/.
    from build_reproducibility_package import (  # type: ignore
        create_portable_archive,
        load_source_only_forbidden_patterns,
        safe_relative_path,
        sha256_file,
        validate_destination,
        validate_text_content,
    )
    from verify_public_release import validate_public_release  # type: ignore


DEFAULT_OVERLAY = Path(
    "cce/paper1/release-preparation/PUBLIC-PACKAGE-OVERLAY.template.json"
)
GENERATED_MANIFEST = Path("PACKAGE-MANIFEST.json")
EXPECTED_EXCLUSIONS = {
    Path("README.md"),
    Path("INTERNAL-REVIEW-NOTICE.md"),
    Path("PUBLICATION-GATES.md"),
    GENERATED_MANIFEST,
}


def load_json(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def entry_pairs(records: object, label: str) -> List[Tuple[Path, Path]]:
    if not isinstance(records, list):
        raise ValueError(f"{label} must be a list")
    pairs: List[Tuple[Path, Path]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{label} entries must be objects")
        source = record.get("source")
        destination = record.get("destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise ValueError(f"{label} entries require source and destination")
        pairs.append((safe_relative_path(source), safe_relative_path(destination)))
    return pairs


def public_manifest_and_pairs(
    repository: Path, overlay_path: Path, gate_record: Mapping[str, object]
) -> Tuple[Dict[str, object], List[Tuple[Path, Path]]]:
    overlay = load_json(overlay_path)
    if overlay.get("status") != "public_package_overlay_authorized":
        raise ValueError("public package overlay is not authorized")
    if overlay.get("publication_authorized") is not True:
        raise ValueError("overlay publication_authorized must be true")
    if overlay.get("release_status") != "public_release":
        raise ValueError("overlay release_status must be public_release")

    raw_base_manifest = overlay.get("base_manifest")
    if not isinstance(raw_base_manifest, str):
        raise ValueError("base_manifest must be a relative path")
    base_manifest = load_json(repository / safe_relative_path(raw_base_manifest))
    if base_manifest.get("release_status") != "internal_candidate":
        raise ValueError("base manifest must be the reviewed internal candidate")

    raw_exclusions = overlay.get("exclude_destinations")
    if not isinstance(raw_exclusions, list) or any(
        not isinstance(item, str) for item in raw_exclusions
    ):
        raise ValueError("exclude_destinations must be a list of strings")
    exclusions = {safe_relative_path(item) for item in raw_exclusions}
    if exclusions != EXPECTED_EXCLUSIONS:
        raise ValueError("public package exclusions must match the fixed internal-only set")

    pairs = [
        pair
        for pair in entry_pairs(base_manifest.get("entries"), "base entries")
        if pair[1] not in exclusions
    ]
    pairs.extend(entry_pairs(overlay.get("replacement_entries"), "replacement entries"))

    destinations = [destination for _source, destination in pairs]
    if len(set(destinations)) != len(destinations):
        raise ValueError("public package has duplicate destinations")
    required_public_destinations = {
        Path("README.md"),
        Path("PUBLICATION-STATUS.md"),
        Path("CITATION.cff"),
        Path("LICENSE-MAP.md"),
    }
    if not required_public_destinations.issubset(destinations):
        raise ValueError("public package replacements are incomplete")
    if not any(path.parts and path.parts[0] == "LICENSES" for path in destinations):
        raise ValueError("public package has no license text")

    license_identifiers = overlay.get("license_identifiers")
    if not isinstance(license_identifiers, dict):
        raise ValueError("license_identifiers must be an object")
    expected_licenses = {
        "paper": gate_record.get("paper_license"),
        "code": gate_record.get("code_license"),
        "documentation": gate_record.get("documentation_license"),
        "synthetic_outputs": gate_record.get("synthetic_output_license"),
    }
    if license_identifiers != expected_licenses:
        raise ValueError("overlay licenses do not match the author gate record")

    independent_status = overlay.get("independent_reproduction_status")
    if independent_status not in {
        "not_completed_disclosed",
        "completed_with_external_record",
    }:
        raise ValueError("invalid independent_reproduction_status")

    manifest = dict(base_manifest)
    manifest.update(
        {
            "package_name": overlay.get("package_name"),
            "release_status": "public_release",
            "publication_authorized": True,
            "independent_reproduction_status": independent_status,
            "license_identifiers": license_identifiers,
            "entries": [
                {"source": source.as_posix(), "destination": destination.as_posix()}
                for source, destination in pairs
            ]
            + [
                {
                    "source": "generated/PACKAGE-MANIFEST.json",
                    "destination": GENERATED_MANIFEST.as_posix(),
                }
            ],
            "publication_gates": [
                "Author-approved licenses and citation are included",
                "Package is built from the clean authorized Git commit",
                "CI evidence is recorded in the external release gate",
                "Independent human reproduction status is explicitly disclosed",
                "Final archive SHA-256 is verified outside the archive",
            ],
        }
    )
    return manifest, pairs


def build_public_package(
    repository: Path,
    output_dir: Path,
    archive_path: Path,
    overlay_path: Path,
    gates_path: Path,
) -> Dict[str, object]:
    repository = repository.resolve()
    output_dir = output_dir.resolve()
    archive_path = archive_path.resolve()
    gates_path = gates_path.resolve()
    overlay_path = overlay_path if overlay_path.is_absolute() else repository / overlay_path

    prepackage = validate_public_release(
        repository, gates_path, phase="prepackage"
    )
    gate_record = load_json(gates_path)
    manifest, pairs = public_manifest_and_pairs(repository, overlay_path, gate_record)

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    if archive_path.exists():
        raise FileExistsError(f"archive path already exists: {archive_path}")
    output_dir.mkdir(parents=True, exist_ok=True)

    fragments = manifest.get("forbidden_path_fragments", [])
    suffixes = manifest.get("forbidden_suffixes", [])
    patterns = manifest.get("forbidden_content_patterns", [])
    if not isinstance(fragments, list) or not isinstance(suffixes, list) or not isinstance(patterns, list):
        raise ValueError("base manifest forbidden rules must be lists")
    forbidden_patterns: Iterable[str] = [
        *patterns,
        *load_source_only_forbidden_patterns(repository),
    ]

    copied: List[Path] = []
    for source_relative, destination_relative in pairs:
        validate_destination(destination_relative, fragments, suffixes)
        source = repository / source_relative
        if source.is_symlink():
            raise ValueError(f"source entry is a symbolic link: {source_relative}")
        if not source.is_file():
            raise FileNotFoundError(f"missing public package source: {source_relative}")
        destination = output_dir / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        validate_text_content(destination, destination_relative, forbidden_patterns)
        copied.append(destination_relative)

    manifest_path = output_dir / GENERATED_MANIFEST
    manifest_path.write_bytes(
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )
    copied.append(GENERATED_MANIFEST)

    independent_completed = (
        manifest["independent_reproduction_status"] == "completed_with_external_record"
    )
    metadata = {
        "package_name": manifest["package_name"],
        "release_status": "public_release",
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "python_implementation": __import__("platform").python_implementation(),
        "platform": __import__("platform").platform(),
        "source_git_head": prepackage["git_head"],
        "source_git_dirty": False,
        "source_file_count": len(copied),
        "license_included": True,
        "independent_reproduction_completed": independent_completed,
    }
    metadata_path = output_dir / "BUILD-METADATA.json"
    metadata_path.write_bytes(
        (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )

    hashed_paths = sorted(copied + [Path("BUILD-METADATA.json")])
    (output_dir / "SHA256SUMS").write_text(
        "\n".join(
            f"{sha256_file(output_dir / path)}  {path.as_posix()}"
            for path in hashed_paths
        )
        + "\n",
        encoding="utf-8",
    )

    expected = set(copied) | {Path("BUILD-METADATA.json"), Path("SHA256SUMS")}
    actual = {
        path.relative_to(output_dir)
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    if actual != expected:
        raise ValueError("public package inventory is not exact")

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "verify_package.py"],
        cwd=str(output_dir),
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError("generated public package verification failed:\n" + completed.stdout)

    archive_sha256 = create_portable_archive(output_dir, archive_path)
    return {
        "status": "built_verified_public_package_candidate",
        "output_dir": str(output_dir),
        "archive_path": str(archive_path),
        "archive_sha256": archive_sha256,
        "git_head": prepackage["git_head"],
        "file_count": len(actual),
        "publication_authorized": True,
        "independent_reproduction_status": manifest["independent_reproduction_status"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an authorized public CCE reproducibility package."
    )
    parser.add_argument("--repository-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--archive-path", required=True, type=Path)
    parser.add_argument("--overlay", required=True, type=Path)
    parser.add_argument("--gates", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    try:
        result = build_public_package(
            arguments.repository_dir,
            arguments.output_dir,
            arguments.archive_path,
            arguments.overlay,
            arguments.gates,
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(f"PUBLIC PACKAGE BUILD FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
