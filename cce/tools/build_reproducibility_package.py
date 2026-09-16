"""Build an explicit, review-only CCE-MVM v0.1 reproducibility package."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional


DEFAULT_MANIFEST = Path(
    "cce/paper1/reproducibility/PACKAGE-MANIFEST-v0.1.json"
)
DEFAULT_SOURCE_ONLY_FORBIDDEN_CONTENT_FILE = Path(
    "cce/paper1/reproducibility/SOURCE-ONLY-FORBIDDEN-CONTENT.local.json"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"unsafe package path: {raw_path!r}")
    return path


def git_value(root: Path, *arguments: str) -> Optional[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def validate_destination(
    relative_path: Path,
    forbidden_fragments: Iterable[str],
    forbidden_suffixes: Iterable[str],
) -> None:
    normalized = relative_path.as_posix().lower()
    for fragment in forbidden_fragments:
        if fragment.lower() in normalized:
            raise ValueError(
                f"forbidden path fragment {fragment!r} in {relative_path.as_posix()!r}"
            )
    suffixes = tuple(suffix.lower() for suffix in forbidden_suffixes)
    if relative_path.suffix.lower() in suffixes:
        raise ValueError(f"forbidden file type: {relative_path.as_posix()}")


def validate_text_content(
    path: Path, relative_path: Path, forbidden_patterns: Iterable[str]
) -> None:
    if relative_path == Path("PACKAGE-MANIFEST.json"):
        return
    if path.suffix.lower() not in {
        ".csv",
        ".json",
        ".md",
        ".py",
        ".txt",
        ".yml",
        ".yaml",
        ".cff",
        ".template",
    }:
        return
    content = path.read_text(encoding="utf-8").lower()
    for pattern in forbidden_patterns:
        if pattern.lower() in content:
            raise ValueError(
                f"forbidden content pattern {pattern!r} in {relative_path.as_posix()!r}"
            )


def load_manifest(root: Path, manifest_path: Path) -> Dict[str, object]:
    absolute = manifest_path if manifest_path.is_absolute() else root / manifest_path
    with absolute.open("r", encoding="utf-8") as stream:
        manifest = json.load(stream)
    if manifest.get("release_status") != "internal_candidate":
        raise ValueError("builder only accepts an internal_candidate manifest")
    return manifest


def load_source_only_forbidden_patterns(
    root: Path,
    pattern_file: Path = DEFAULT_SOURCE_ONLY_FORBIDDEN_CONTENT_FILE,
) -> Iterable[str]:
    absolute = pattern_file if pattern_file.is_absolute() else root / pattern_file
    if not absolute.exists():
        return ()
    with absolute.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict) or payload.get("status") != "local_not_for_distribution":
        raise ValueError("invalid source-only forbidden-content file status")
    patterns = payload.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise ValueError("source-only forbidden-content patterns must be a non-empty list")
    if any(not isinstance(pattern, str) or not pattern for pattern in patterns):
        raise ValueError("source-only forbidden-content patterns must be strings")
    return tuple(patterns)


def build_package(root: Path, output_dir: Path, manifest_path: Path) -> Dict[str, object]:
    manifest = load_manifest(root, manifest_path)
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("manifest entries must be a non-empty list")

    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    forbidden_fragments = manifest.get("forbidden_path_fragments", [])
    forbidden_suffixes = manifest.get("forbidden_suffixes", [])
    manifest_content_patterns = manifest.get("forbidden_content_patterns", [])
    if not isinstance(forbidden_fragments, list) or not isinstance(
        forbidden_suffixes, list
    ) or not isinstance(manifest_content_patterns, list):
        raise ValueError("forbidden path rules must be lists")
    forbidden_content_patterns = [
        *manifest_content_patterns,
        *load_source_only_forbidden_patterns(root),
    ]

    copied_paths = []
    seen_destinations = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("every manifest entry must be an object")
        source_relative = safe_relative_path(str(entry.get("source", "")))
        destination_relative = safe_relative_path(str(entry.get("destination", "")))
        validate_destination(
            destination_relative, forbidden_fragments, forbidden_suffixes
        )
        if destination_relative in seen_destinations:
            raise ValueError(f"duplicate destination: {destination_relative}")
        seen_destinations.add(destination_relative)

        source = root / source_relative
        if not source.is_file():
            raise FileNotFoundError(f"missing source file: {source_relative}")
        destination = output_dir / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        validate_text_content(
            destination, destination_relative, forbidden_content_patterns
        )
        copied_paths.append(destination_relative)

    git_head = git_value(root, "rev-parse", "--verify", "HEAD")
    git_status = git_value(root, "status", "--porcelain", "--untracked-files=all")
    source_git_dirty = True if git_head is None or git_status is None else bool(git_status)
    metadata = {
        "package_name": manifest["package_name"],
        "release_status": manifest["release_status"],
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "source_git_head": git_head,
        "source_git_dirty": source_git_dirty,
        "source_file_count": len(copied_paths),
        "license_included": False,
        "independent_reproduction_completed": False,
    }
    metadata_path = output_dir / "BUILD-METADATA.json"
    metadata_path.write_bytes(
        (json.dumps(metadata, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )

    hashed_paths = sorted(copied_paths + [Path("BUILD-METADATA.json")])
    checksum_lines = [
        f"{sha256_file(output_dir / relative)}  {relative.as_posix()}"
        for relative in hashed_paths
    ]
    (output_dir / "SHA256SUMS").write_bytes(
        ("\n".join(checksum_lines) + "\n").encode("utf-8")
    )

    for file_path in output_dir.rglob("*"):
        if file_path.is_file():
            validate_destination(
                file_path.relative_to(output_dir),
                forbidden_fragments,
                forbidden_suffixes,
            )
            validate_text_content(
                file_path,
                file_path.relative_to(output_dir),
                forbidden_content_patterns,
            )

    return {
        "status": "built",
        "output_dir": str(output_dir),
        "copied_files": len(copied_paths),
        "hashed_files": len(hashed_paths),
        "release_status": manifest["release_status"],
        "source_git_dirty": metadata["source_git_dirty"],
    }


def normalized_tar_info(info: tarfile.TarInfo) -> tarfile.TarInfo:
    """Remove host-specific ownership, timestamps, modes, and pax metadata."""
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = 0
    info.mode = 0o755 if info.isdir() else 0o644
    info.pax_headers = {}
    return info


def create_portable_archive(package_dir: Path, archive_path: Path) -> str:
    """Create a deterministic gzip tar without macOS AppleDouble entries."""
    package_dir = package_dir.resolve()
    archive_path = archive_path.resolve()
    if not package_dir.is_dir():
        raise FileNotFoundError(f"package directory is missing: {package_dir}")
    if archive_path.exists():
        raise FileExistsError(f"archive path already exists: {archive_path}")
    if package_dir == archive_path.parent or package_dir in archive_path.parents:
        raise ValueError("archive path must be outside the package directory")

    members = [package_dir, *sorted(package_dir.rglob("*"), key=lambda p: p.relative_to(package_dir).as_posix())]
    for member in members:
        if member.is_symlink():
            raise ValueError(f"archive source contains a symbolic link: {member}")
        if not (member.is_file() or member.is_dir()):
            raise ValueError(f"archive source contains a special file: {member}")

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("wb") as raw_stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_stream, mtime=0) as gzip_stream:
            with tarfile.open(
                fileobj=gzip_stream,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for member in members:
                    if member == package_dir:
                        arcname = package_dir.name
                    else:
                        arcname = (
                            Path(package_dir.name) / member.relative_to(package_dir)
                        ).as_posix()
                    archive.add(
                        str(member),
                        arcname=arcname,
                        recursive=False,
                        filter=normalized_tar_info,
                    )
    return sha256_file(archive_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the explicit CCE-MVM v0.1 reproducibility package."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="A new or empty directory for the internal candidate package.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Package manifest path relative to the workspace root.",
    )
    parser.add_argument(
        "--archive-path",
        type=Path,
        help="Optional new .tar.gz path outside the package directory.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        output_dir = arguments.output_dir.resolve()
        result = build_package(root, output_dir, arguments.manifest)
        if arguments.archive_path is not None:
            archive_path = arguments.archive_path.resolve()
            checksum_path = archive_path.with_name(archive_path.name + ".sha256")
            if checksum_path.exists():
                raise FileExistsError(
                    f"archive checksum path already exists: {checksum_path}"
                )
            result["archive_path"] = str(archive_path)
            result["archive_sha256"] = create_portable_archive(
                output_dir, archive_path
            )
            checksum_path.write_bytes(
                (
                    f"{result['archive_sha256']}  {archive_path.name}\n"
                ).encode("utf-8")
            )
            result["archive_sha256_path"] = str(checksum_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f"BUILD FAILED: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
