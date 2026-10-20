import contextlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_ipa


class ExtractionComplete(Exception):
    pass


class PackageExtractionTests(unittest.TestCase):
    def test_aliased_temporary_directory_preserves_executable(self):
        # Reproduce the macOS /var -> /private/var temporary path alias.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            actual = root / "actual"
            actual.mkdir()
            alias = root / "alias"
            alias.symlink_to(actual, target_is_directory=True)
            source = root / "client.ipa"
            with zipfile.ZipFile(source, "w") as archive:
                entry = zipfile.ZipInfo("Payload/Telegram.app/Telegram")
                entry.external_attr = 0o100755 << 16
                archive.writestr(entry, b"test executable")
            with mock.patch.object(package_ipa.tempfile, "TemporaryDirectory", return_value=contextlib.nullcontext(str(alias))), \
                    mock.patch.object(package_ipa, "install", side_effect=ExtractionComplete) as install:
                with self.assertRaises(ExtractionComplete):
                    package_ipa.package(source, root / "Python.xcframework", root / "output.ipa")
                install.assert_called_once()
            executable = actual / "Payload/Telegram.app/Telegram"
            self.assertEqual(executable.read_bytes(), b"test executable")
            self.assertEqual(executable.stat().st_mode & 0o777, 0o755)

    def test_parent_escape_is_still_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            destination = root / "extract"
            destination.mkdir()
            source = root / "unsafe.ipa"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../escaped", b"invalid")
            with mock.patch.object(package_ipa.tempfile, "TemporaryDirectory", return_value=contextlib.nullcontext(str(destination))):
                with self.assertRaisesRegex(RuntimeError, "Unsafe IPA archive path"):
                    package_ipa.package(source, root / "framework", root / "output.ipa")
            self.assertFalse((root / "escaped").exists())
