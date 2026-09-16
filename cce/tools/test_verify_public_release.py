import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from cce.tools.verify_public_release import validate_public_release


class PublicReleaseVerifierTests(unittest.TestCase):
    def make_repository(self, root: Path) -> tuple[Path, Path, Path]:
        repository = root / "repository"
        repository.mkdir()
        files = {
            "README.md": "# CCE MVM\nPublic computational research source.\n",
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
            "LICENSES/Apache-2.0.txt": "Apache License 2.0 test fixture\n",
            "LICENSES/CC-BY-4.0.txt": "CC BY 4.0 test fixture\n",
            ".github/workflows/verify.yml": "name: verify\n",
            "model.py": "VALUE = 1\n",
        }
        for relative, text in files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

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
        archive = root / "cce-mvm-v0.1.tar.gz"
        archive.write_bytes(b"fixed reproducibility fixture\n")
        archive_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
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
            "reproducibility_archive": "cce-mvm-v0.1.tar.gz",
            "reproducibility_archive_sha256": archive_hash,
            "ci_platforms_verified": ["ubuntu", "macos", "windows"],
            "ci_python_versions_verified": ["3.9", "3.14"],
            "author_decisions_applied": True,
            "license_applied": True,
            "citation_finalized": True,
            "clean_commit_confirmed": True,
            "ci_passed": True,
            "reproducibility_package_verified": True,
            "final_content_scan_passed": True,
            "publication_authorized": True,
            "author_approval_utc": "2026-08-31T00:00:00Z",
        }
        gate_path = root / "gates.json"
        gate_path.write_text(json.dumps(gates), encoding="utf-8")
        return repository, gate_path, archive

    def test_valid_clean_authorized_release_passes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            result = validate_public_release(repository, gates, archive)
            self.assertEqual(result["status"], "verified_public_release_candidate")
            self.assertTrue(result["publication_authorized"])

    def test_prepackage_phase_passes_before_archive_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, _archive = self.make_repository(Path(temp_dir))
            record = json.loads(gates.read_text())
            record["reproducibility_archive"] = None
            record["reproducibility_archive_sha256"] = None
            record["reproducibility_package_verified"] = False
            record["final_content_scan_passed"] = False
            gates.write_text(json.dumps(record), encoding="utf-8")
            result = validate_public_release(
                repository, gates, phase="prepackage"
            )
            self.assertEqual(result["status"], "verified_public_repository_prepackage")

    def test_authorization_false_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            record = json.loads(gates.read_text())
            record["publication_authorized"] = False
            gates.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "publication_authorized"):
                validate_public_release(repository, gates, archive)

    def test_dirty_repository_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            (repository / "untracked.txt").write_text("new\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not clean"):
                validate_public_release(repository, gates, archive)

    def test_draft_marker_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            marker = repository / ("DRAFT" + "-NOT-FOR-PUBLICATION.md")
            marker.write_text("stop\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "marker"],
                check=True,
            )
            record = json.loads(gates.read_text())
            record["expected_git_head"] = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            record["ci_git_head"] = record["expected_git_head"]
            gates.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "draft or template"):
                validate_public_release(repository, gates, archive)

    def test_license_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            record = json.loads(gates.read_text())
            record["license_file_sha256"]["LICENSES/Apache-2.0.txt"] = "b" * 64
            gates.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "license SHA-256 mismatch"):
                validate_public_release(repository, gates, archive)

    def test_unresolved_citation_placeholder_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            citation = repository / "CITATION.cff"
            unresolved = "_" * 2 + "DOI" + "_" * 2
            citation.write_text(
                citation.read_text() + f"doi: {unresolved}\n", encoding="utf-8"
            )
            subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(repository), "commit", "-q", "-m", "placeholder"],
                check=True,
            )
            record = json.loads(gates.read_text())
            record["expected_git_head"] = subprocess.run(
                ["git", "-C", str(repository), "rev-parse", "HEAD"],
                check=True,
                stdout=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            record["ci_git_head"] = record["expected_git_head"]
            gates.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unresolved placeholder"):
                validate_public_release(repository, gates, archive)

    def test_reproducibility_archive_hash_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            archive.write_bytes(b"changed after approval\n")
            with self.assertRaisesRegex(ValueError, "archive SHA-256 mismatch"):
                validate_public_release(repository, gates, archive)

    def test_ci_commit_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository, gates, archive = self.make_repository(Path(temp_dir))
            record = json.loads(gates.read_text())
            record["ci_git_head"] = "a" * 40
            gates.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ci_git_head must match"):
                validate_public_release(repository, gates, archive)


if __name__ == "__main__":
    unittest.main()
