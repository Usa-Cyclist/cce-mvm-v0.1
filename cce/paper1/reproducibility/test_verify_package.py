import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from . import verify_package as verifier
except ImportError:  # Packaged tests run from the extracted package root.
    import verify_package as verifier


class PackageVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cce-verifier-test-")
        self.root = Path(self.temporary.name)
        self.manifest = {
            "package_name": "test-package",
            "release_status": "internal_candidate",
            "entries": [
                {"destination": "PACKAGE-MANIFEST.json"},
                {"destination": "README.md"},
                {
                    "destination": "INDEPENDENT-REPRODUCTION-RECORD-TEMPLATE.md"
                },
            ],
            "allowed_mutable_files": [
                {
                    "path": "INDEPENDENT-REPRODUCTION-RECORD.md",
                    "template": "INDEPENDENT-REPRODUCTION-RECORD-TEMPLATE.md",
                    "purpose": "independent_reproduction_record",
                }
            ],
            "forbidden_path_fragments": ["private-evidence"],
            "forbidden_suffixes": [".pdf"],
            "forbidden_content_patterns": ["restricted-facility"],
        }
        self._write("PACKAGE-MANIFEST.json", json.dumps(self.manifest))
        self._write("README.md", "# Read me\n")
        self._write(
            "INDEPENDENT-REPRODUCTION-RECORD-TEMPLATE.md", "# Blank record\n"
        )
        self._write("BUILD-METADATA.json", "{}\n")
        self._write("SHA256SUMS", "placeholder\n")

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def _write_exact_checksums(self, extra_paths=()):
        destinations = verifier.manifest_destinations(self.manifest)
        paths = destinations | {verifier.BUILD_METADATA_PATH} | {
            Path(value) for value in extra_paths
        }
        lines = [
            f"{verifier.sha256_file(self.root / path)}  {path.as_posix()}"
            for path in sorted(paths)
        ]
        self._write("SHA256SUMS", "\n".join(lines) + "\n")

    def test_inventory_rejects_unlisted_file(self):
        self._write("unexpected.txt", "unexpected\n")
        with self.assertRaisesRegex(ValueError, "unlisted package files"):
            verifier.verify_inventory(self.manifest, self.root)

    def test_inventory_allows_only_declared_mutable_record(self):
        self._write("INDEPENDENT-REPRODUCTION-RECORD.md", "review result\n")
        self.assertEqual(verifier.verify_inventory(self.manifest, self.root), 6)
        self._write("ANOTHER-MUTABLE.md", "not declared\n")
        with self.assertRaisesRegex(ValueError, "ANOTHER-MUTABLE.md"):
            verifier.verify_inventory(self.manifest, self.root)

    def test_inventory_rejects_symbolic_link(self):
        target = self._write("target.tmp", "target\n")
        link = self.root / "linked.tmp"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("symbolic links are unavailable")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            verifier.verify_inventory(self.manifest, self.root)

    def test_hashes_must_exactly_cover_immutable_files(self):
        self._write_exact_checksums()
        self.assertEqual(verifier.verify_hashes(self.manifest, self.root), 4)

        mutable = self._write(
            "INDEPENDENT-REPRODUCTION-RECORD.md", "review result\n"
        )
        mutable_hash = verifier.sha256_file(mutable)
        with (self.root / "SHA256SUMS").open("a", encoding="utf-8") as stream:
            stream.write(
                f"{mutable_hash}  INDEPENDENT-REPRODUCTION-RECORD.md\n"
            )
        with self.assertRaisesRegex(ValueError, "mutable files must not"):
            verifier.verify_hashes(self.manifest, self.root)

    def test_forbidden_content_is_rechecked_in_mutable_record(self):
        self._write(
            "INDEPENDENT-REPRODUCTION-RECORD.md",
            "The restricted-facility name must not be shared.\n",
        )
        with self.assertRaisesRegex(ValueError, "forbidden content pattern"):
            verifier.validate_no_forbidden_files(self.manifest, self.root)

    def test_forbidden_suffix_and_path_are_rechecked(self):
        self._write("private-evidence/report.pdf", "not a real PDF\n")
        with self.assertRaisesRegex(ValueError, "forbidden path"):
            verifier.validate_no_forbidden_files(self.manifest, self.root)

    def test_build_metadata_validates_git_and_source_provenance(self):
        metadata = {
            "package_name": "test-package",
            "release_status": "internal_candidate",
            "built_at_utc": "2026-08-30T00:00:00+00:00",
            "python_version": "3.12.0",
            "python_implementation": "CPython",
            "platform": "test-platform",
            "source_git_head": "a" * 40,
            "source_git_dirty": True,
            "source_file_count": 3,
            "license_included": False,
            "independent_reproduction_completed": False,
        }
        self._write("BUILD-METADATA.json", json.dumps(metadata))
        result = verifier.validate_build_metadata(self.manifest, self.root)
        self.assertEqual(result["source_git_head"], "a" * 40)

        metadata["source_file_count"] = 2
        self._write("BUILD-METADATA.json", json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, "source_file_count"):
            verifier.validate_build_metadata(self.manifest, self.root)

    def test_relative_reference_must_resolve(self):
        self.manifest["entries"].append({"destination": "docs/guide.md"})
        self._write("docs/guide.md", "See `missing.md`.\n")
        with self.assertRaisesRegex(FileNotFoundError, "missing.md"):
            verifier.validate_relative_references(self.manifest, self.root)

        self.manifest["entries"].append({"destination": "docs/missing.md"})
        self._write("docs/missing.md", "# Present\n")
        self.assertEqual(
            verifier.validate_relative_references(self.manifest, self.root), 1
        )

    def test_forbidden_suffix_reference_must_also_resolve_or_be_exempted(self):
        self.manifest["entries"].append({"destination": "docs/guide.md"})
        self._write("docs/guide.md", "See `missing.pdf`.\n")
        with self.assertRaisesRegex(FileNotFoundError, "missing.pdf"):
            verifier.validate_relative_references(self.manifest, self.root)

    def test_relative_reference_exemption_is_explicit_and_not_stale(self):
        self.manifest["entries"].append({"destination": "docs/guide.md"})
        self._write("docs/guide.md", "See `external.md`.\n")
        exemption = {
            "source": "docs/guide.md",
            "reference": "external.md",
            "classification": "intentionally_not_packaged",
            "reason": "The supporting archive is distributed separately.",
        }
        self.manifest["relative_reference_exemptions"] = [exemption]
        self.assertEqual(
            verifier.validate_relative_references(self.manifest, self.root), 1
        )

        self._write("docs/external.md", "# Now packaged\n")
        self.manifest["entries"].append({"destination": "docs/external.md"})
        with self.assertRaisesRegex(ValueError, "unused relative reference exemption"):
            verifier.validate_relative_references(self.manifest, self.root)

    def test_config_sha_and_declared_outputs_are_verified(self):
        config = self._write("config/example.json", "{\"fixed\": true}\n")
        config_hash = hashlib.sha256(config.read_bytes()).hexdigest()
        metadata = {
            "model": "CCE-MVM-v0.1",
            "synthetic_only": True,
            "config_sha256": config_hash,
            "files": ["result.csv"],
        }
        self._write("results/example/metadata.json", json.dumps(metadata))
        self._write("results/example/result.csv", "value\n1\n")
        self.manifest["experiments"] = [
            {
                "id": "example",
                "saved_result_dir": "results/example",
                "files": ["metadata.json", "result.csv"],
                "metadata_file": "metadata.json",
                "config_path": "config/example.json",
                "required_metadata": {
                    "model": "CCE-MVM-v0.1",
                    "synthetic_only": True,
                },
            }
        ]
        self.assertEqual(
            verifier.validate_experiment_provenance(self.manifest, self.root),
            (1, 1, 0),
        )

        metadata["config_sha256"] = "0" * 64
        self._write("results/example/metadata.json", json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, "config SHA-256"):
            verifier.validate_experiment_provenance(self.manifest, self.root)

    def test_optional_config_provenance_is_reported_pending(self):
        self._write("config/example.json", "{\"fixed\": true}\n")
        metadata = {
            "model": "CCE-MVM-v0.1",
            "synthetic_only": True,
            "files": ["result.csv"],
        }
        self._write("results/example/metadata.json", json.dumps(metadata))
        self._write("results/example/result.csv", "value\n1\n")
        self.manifest["experiments"] = [
            {
                "id": "example",
                "saved_result_dir": "results/example",
                "files": ["metadata.json", "result.csv"],
                "config_path": "config/example.json",
                "config_sha256_required": False,
            }
        ]
        self.assertEqual(
            verifier.validate_experiment_provenance(self.manifest, self.root),
            (1, 0, 1),
        )

    def test_duplicate_manifest_destination_is_rejected(self):
        self.manifest["entries"].append({"destination": "README.md"})
        with self.assertRaisesRegex(ValueError, "duplicate manifest destination"):
            verifier.manifest_destinations(self.manifest)

    def test_skipped_tests_are_not_reported_as_success(self):
        self.manifest["verifier_test_modules"] = ["example"]
        self.manifest["expected_verifier_test_count"] = 1
        output = "Ran 1 test in 0.001s\n\nOK (skipped=1)\n"
        with mock.patch.object(verifier, "run_command", return_value=output):
            with self.assertRaisesRegex(ValueError, "1 skipped tests"):
                verifier.run_verifier_tests(self.manifest, self.root)

    def test_public_release_requires_all_publication_gates(self):
        release_manifest = {
            "release_status": "public_release",
            "publication_authorized": False,
            "independent_reproduction_status": "not_completed_disclosed",
        }
        metadata = {
            "license_included": False,
            "source_git_dirty": True,
            "independent_reproduction_completed": False,
        }
        with self.assertRaisesRegex(ValueError, "release gates failed"):
            verifier.validate_release_gates(release_manifest, metadata, 1)
        metadata.update(
            {
                "license_included": True,
                "source_git_dirty": False,
                "independent_reproduction_completed": False,
            }
        )
        release_manifest["publication_authorized"] = True
        verifier.validate_release_gates(release_manifest, metadata, 0)

        release_manifest["independent_reproduction_status"] = (
            "completed_with_external_record"
        )
        with self.assertRaisesRegex(ValueError, "metadata true"):
            verifier.validate_release_gates(release_manifest, metadata, 0)
        metadata["independent_reproduction_completed"] = True
        verifier.validate_release_gates(release_manifest, metadata, 0)

    def test_python_39_is_minimum_supported_runtime(self):
        verifier.validate_python_version((3, 9, 0))
        with self.assertRaisesRegex(ValueError, "Python 3.9"):
            verifier.validate_python_version((3, 8, 20))


if __name__ == "__main__":
    unittest.main()
