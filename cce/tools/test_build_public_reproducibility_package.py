import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from cce.tools.build_public_reproducibility_package import build_public_package


class PublicPackageBuilderTests(unittest.TestCase):
    def make_fixture(self, root: Path):
        repository = root / "repository"
        repository.mkdir()
        files = {
            "README.md": "# CCE MVM\nPublic source repository.\n",
            "CITATION.cff": (
                "cff-version: 1.2.0\n"
                "title: CCE MVM\n"
                "authors:\n  - family-names: Morimoto\n    given-names: Daiki\n"
                "repository-code: https://github.com/example/cce-mvm\n"
                "license: Apache-2.0\n"
            ),
            "LICENSE-MAP.md": (
                "paper: arxiv-perpetual-non-exclusive\n"
                "code: Apache-2.0\n"
                "documentation: CC-BY-4.0\n"
                "synthetic outputs: CC-BY-4.0\n"
            ),
            "LICENSES/Apache-2.0.txt": "Apache License 2.0 fixture\n",
            "LICENSES/CC-BY-4.0.txt": "CC BY 4.0 fixture\n",
            ".github/workflows/verify.yml": "name: verify\n",
            "cce/paper1/reproducibility/internal-readme.md": "internal\n",
            "cce/paper1/reproducibility/internal-notice.md": "internal notice\n",
            "cce/paper1/reproducibility/internal-gates.md": "open gates\n",
            "cce/paper1/reproducibility/base-manifest.json": "{}\n",
            "cce/paper1/reproducibility/PUBLIC-PACKAGE-README.md": (
                "# Public package\nRun python3 verify_package.py.\n"
            ),
            "cce/paper1/reproducibility/PUBLIC-RELEASE-STATUS.md": (
                "# Public status\nIndependent reproduction: not completed; disclosed.\n"
            ),
            "base.txt": "synthetic fixture\n",
            "verify_package.py": "print('{\"status\": \"verified\"}')\n",
        }
        for relative, text in files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        base_manifest = {
            "schema_version": "0.2",
            "package_name": "cce-mvm-v0.1-reproducibility",
            "release_status": "internal_candidate",
            "entries": [
                {
                    "source": "cce/paper1/reproducibility/internal-readme.md",
                    "destination": "README.md",
                },
                {
                    "source": "cce/paper1/reproducibility/internal-notice.md",
                    "destination": "INTERNAL-REVIEW-NOTICE.md",
                },
                {
                    "source": "cce/paper1/reproducibility/internal-gates.md",
                    "destination": "PUBLICATION-GATES.md",
                },
                {
                    "source": "cce/paper1/reproducibility/base-manifest.json",
                    "destination": "PACKAGE-MANIFEST.json",
                },
                {"source": "base.txt", "destination": "base.txt"},
                {"source": "verify_package.py", "destination": "verify_package.py"},
            ],
            "forbidden_path_fragments": [],
            "forbidden_suffixes": [],
            "forbidden_content_patterns": [],
        }
        base_path = repository / "cce/paper1/reproducibility/PACKAGE-MANIFEST-v0.1.json"
        base_path.write_text(json.dumps(base_manifest), encoding="utf-8")

        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.name", "Release Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(repository), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        head = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()

        license_hashes = {
            path: hashlib.sha256((repository / path).read_bytes()).hexdigest()
            for path in (
                "LICENSES/Apache-2.0.txt",
                "LICENSES/CC-BY-4.0.txt",
            )
        }
        gates = {
            "schema_version": "0.1",
            "status": "public_release_candidate",
            "author_name": "Daiki Morimoto",
            "affiliation_display": "Independent Researcher, Japan",
            "repository_url": "https://github.com/example/cce-mvm",
            "paper_license": "arxiv-perpetual-non-exclusive",
            "code_license": "Apache-2.0",
            "documentation_license": "CC-BY-4.0",
            "synthetic_output_license": "CC-BY-4.0",
            "expected_git_head": head,
            "ci_run_url": "https://github.com/example/cce-mvm/actions/runs/123456789",
            "ci_git_head": head,
            "ci_jobs_expected": 19,
            "ci_jobs_passed": 19,
            "required_files": [
                "README.md",
                "CITATION.cff",
                "LICENSE-MAP.md",
                "LICENSES/Apache-2.0.txt",
                "LICENSES/CC-BY-4.0.txt",
                ".github/workflows/verify.yml",
            ],
            "license_file_sha256": license_hashes,
            "reproducibility_archive": None,
            "reproducibility_archive_sha256": None,
            "ci_platforms_verified": ["ubuntu", "macos", "windows"],
            "ci_python_versions_verified": ["3.9", "3.14"],
            "author_decisions_applied": True,
            "license_applied": True,
            "citation_finalized": True,
            "clean_commit_confirmed": True,
            "ci_passed": True,
            "reproducibility_package_verified": False,
            "final_content_scan_passed": False,
            "publication_authorized": True,
            "author_approval_utc": "2026-08-31T00:00:00Z",
        }
        gates_path = root / "gates.json"
        gates_path.write_text(json.dumps(gates), encoding="utf-8")

        overlay = {
            "schema_version": "0.1",
            "status": "public_package_overlay_authorized",
            "publication_authorized": True,
            "base_manifest": "cce/paper1/reproducibility/PACKAGE-MANIFEST-v0.1.json",
            "package_name": "cce-mvm-v0.1-reproducibility",
            "release_status": "public_release",
            "independent_reproduction_status": "not_completed_disclosed",
            "exclude_destinations": [
                "README.md",
                "INTERNAL-REVIEW-NOTICE.md",
                "PUBLICATION-GATES.md",
                "PACKAGE-MANIFEST.json",
            ],
            "replacement_entries": [
                {
                    "source": "cce/paper1/reproducibility/PUBLIC-PACKAGE-README.md",
                    "destination": "README.md",
                },
                {
                    "source": "cce/paper1/reproducibility/PUBLIC-RELEASE-STATUS.md",
                    "destination": "PUBLICATION-STATUS.md",
                },
                {"source": "CITATION.cff", "destination": "CITATION.cff"},
                {"source": "LICENSE-MAP.md", "destination": "LICENSE-MAP.md"},
                {
                    "source": "LICENSES/Apache-2.0.txt",
                    "destination": "LICENSES/Apache-2.0.txt",
                },
                {
                    "source": "LICENSES/CC-BY-4.0.txt",
                    "destination": "LICENSES/CC-BY-4.0.txt",
                },
            ],
            "license_identifiers": {
                "paper": "arxiv-perpetual-non-exclusive",
                "code": "Apache-2.0",
                "documentation": "CC-BY-4.0",
                "synthetic_outputs": "CC-BY-4.0",
            },
        }
        overlay_path = root / "overlay.json"
        overlay_path.write_text(json.dumps(overlay), encoding="utf-8")
        return repository, gates_path, overlay_path

    def test_authorized_clean_public_package_is_built_and_archived(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository, gates, overlay = self.make_fixture(root)
            output = root / "package"
            archive = root / "package.tar.gz"
            result = build_public_package(
                repository, output, archive, overlay, gates
            )
            self.assertEqual(
                result["status"], "built_verified_public_package_candidate"
            )
            self.assertTrue(archive.is_file())
            manifest = json.loads((output / "PACKAGE-MANIFEST.json").read_text())
            metadata = json.loads((output / "BUILD-METADATA.json").read_text())
            self.assertEqual(manifest["release_status"], "public_release")
            self.assertTrue(manifest["publication_authorized"])
            self.assertEqual(
                manifest["independent_reproduction_status"],
                "not_completed_disclosed",
            )
            self.assertTrue(metadata["license_included"])
            self.assertFalse(metadata["independent_reproduction_completed"])
            self.assertFalse((output / "INTERNAL-REVIEW-NOTICE.md").exists())

    def test_template_overlay_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository, gates, overlay = self.make_fixture(root)
            record = json.loads(overlay.read_text())
            record["status"] = "template_not_authorized_for_public_package"
            overlay.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "overlay is not authorized"):
                build_public_package(
                    repository,
                    root / "package",
                    root / "package.tar.gz",
                    overlay,
                    gates,
                )

    def test_existing_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository, gates, overlay = self.make_fixture(root)
            archive = root / "package.tar.gz"
            archive.write_bytes(b"keep\n")
            with self.assertRaises(FileExistsError):
                build_public_package(
                    repository,
                    root / "package",
                    archive,
                    overlay,
                    gates,
                )


if __name__ == "__main__":
    unittest.main()
