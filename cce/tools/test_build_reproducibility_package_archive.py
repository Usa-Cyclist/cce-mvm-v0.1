from pathlib import Path
import json
import tarfile
import tempfile
import unittest

from cce.tools.build_reproducibility_package import (
    build_package,
    create_portable_archive,
)


class PortableArchiveTests(unittest.TestCase):
    def test_archive_has_only_expected_root_and_no_appledouble(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            (package / "README.md").write_text("test\n", encoding="utf-8")
            nested = package / "nested"
            nested.mkdir()
            (nested / "value.txt").write_text("value\n", encoding="utf-8")
            archive_path = root / "package.tar.gz"

            create_portable_archive(package, archive_path)

            with tarfile.open(str(archive_path), "r:gz") as archive:
                names = [member.name for member in archive.getmembers()]
            self.assertEqual(
                names,
                [
                    "package",
                    "package/README.md",
                    "package/nested",
                    "package/nested/value.txt",
                ],
            )
            self.assertFalse(any(Path(name).name.startswith("._") for name in names))

    def test_same_directory_contents_produce_same_archive_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            (package / "value.txt").write_text("stable\n", encoding="utf-8")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            first_hash = create_portable_archive(package, first)
            second_hash = create_portable_archive(package, second)

            self.assertEqual(first_hash, second_hash)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_existing_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            package = root / "package"
            package.mkdir()
            archive_path = root / "package.tar.gz"
            archive_path.write_bytes(b"existing")

            with self.assertRaises(FileExistsError):
                create_portable_archive(package, archive_path)

    def test_git_unavailable_is_never_reported_as_clean(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "source"
            root.mkdir()
            (root / "input.txt").write_text("safe\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "package_name": "test",
                        "release_status": "internal_candidate",
                        "entries": [
                            {"source": "input.txt", "destination": "input.txt"}
                        ],
                        "forbidden_path_fragments": [],
                        "forbidden_suffixes": [],
                        "forbidden_content_patterns": [],
                    }
                ),
                encoding="utf-8",
            )
            output = Path(temp_dir) / "output"
            build_package(root, output, manifest_path)
            metadata = json.loads((output / "BUILD-METADATA.json").read_text())
            self.assertIsNone(metadata["source_git_head"])
            self.assertTrue(metadata["source_git_dirty"])


if __name__ == "__main__":
    unittest.main()
