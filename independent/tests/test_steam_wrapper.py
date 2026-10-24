"""The installer only sees synthetic executables in disposable directories."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "steam_wrapper", Path(__file__).resolve().parents[1] / "scripts/install-steam-wrapper.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class SteamWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.cef = self.root / "cef"
        self.cef.mkdir()
        self.helper = self.cef / "steamwebhelper.exe"
        self.real = self.cef / "steamwebhelper_real.exe"
        self.original = b"MZ" + b"Valve fixture" * 100000
        self.helper.write_bytes(self.original)
        self.wrapper = self.root / "wrapper.exe"
        self.wrapper.write_bytes(b"MZ synthetic wrapper")

    def test_install_repeat_and_restore_preserve_original(self):
        installer.install(self.cef, self.wrapper)
        self.assertEqual(self.real.read_bytes(), self.original)
        self.assertEqual(self.helper.read_bytes(), self.wrapper.read_bytes())
        self.assertIn("already installed", installer.install(self.cef, self.wrapper))
        installer.install(self.cef, self.wrapper, restore=True)
        self.assertEqual(self.helper.read_bytes(), self.original)
        self.assertEqual(self.real.read_bytes(), self.original)

    def test_client_update_preserves_both_original_versions(self):
        installer.install(self.cef, self.wrapper)
        newer = self.original + b"new version"
        self.helper.write_bytes(newer)
        installer.install(self.cef, self.wrapper)
        self.assertEqual(self.real.read_bytes(), newer)
        backups = list(self.cef.glob("steamwebhelper_original_*.exe"))
        self.assertEqual({file.read_bytes() for file in backups}, {self.original, newer})

    def test_unmanaged_original_and_tampered_backup_are_refused(self):
        self.real.write_bytes(b"preexisting")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            installer.install(self.cef, self.wrapper)
        self.assertEqual(self.helper.read_bytes(), self.original)
        self.real.unlink()
        installer.install(self.cef, self.wrapper)
        self.real.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            installer.install(self.cef, self.wrapper, restore=True)
        self.assertEqual(self.helper.read_bytes(), self.wrapper.read_bytes())

    def test_symlink_parent_is_refused(self):
        linked = self.root / "linked"
        linked.symlink_to(self.cef)
        with self.assertRaisesRegex(ValueError, "symlink"):
            installer.install(linked, self.wrapper)
        self.assertEqual(self.helper.read_bytes(), self.original)
