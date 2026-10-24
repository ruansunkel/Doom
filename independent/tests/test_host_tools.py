"""Safety checks use synthetic archives and never run downloaded compilers."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "host_tools", Path(__file__).resolve().parents[1] / "scripts/host-tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


def member(name, content=b"tool", kind=tarfile.REGTYPE, link="", mode=0o755):
    entry = tarfile.TarInfo(name)
    entry.type, entry.linkname, entry.mode = kind, link, mode
    entry.size = len(content) if entry.isfile() else 0
    return entry, io.BytesIO(content)


class HostToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.destination = self.root / "cache" / tools.SOURCE_NAME

    def archive(self, extras=(), required=True):
        entries = []
        if required:
            entries.append(member(f"{tools.SOURCE_NAME}/bin/clang-wrapper.sh", b"#!/bin/sh\nexit 99\n"))
            for arch in ("i686", "x86_64"):
                target = f"{arch}-w64-mingw32"
                entries.extend([
                    member(f"{tools.SOURCE_NAME}/bin/{target}-clang", kind=tarfile.SYMTYPE, link="clang-wrapper.sh"),
                    member(f"{tools.SOURCE_NAME}/{target}/include/windows.h"),
                    member(f"{tools.SOURCE_NAME}/{target}/lib/libkernel32.a"),
                ])
        archive_path = self.root / "fixture.tar.xz"
        with tarfile.open(archive_path, "w:xz") as output:
            for entry, content in entries + list(extras):
                output.addfile(entry, content)
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        mocked = patch.object(tools, "SHA256", digest)
        mocked.start()
        self.addCleanup(mocked.stop)
        return archive_path

    def main(self, *arguments, system="Darwin"):
        with patch.object(tools, "ROOT", self.root), patch.object(tools.platform, "system", return_value=system), \
                patch.object(sys, "argv", ["host-tools.py", *arguments]):
            tools.main()

    def test_corrupt_archive_leaves_no_destination(self):
        archive_path = self.root / "corrupt.tar.xz"
        archive_path.write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            tools.extract(archive_path, self.destination)
        self.assertFalse(self.destination.parent.exists())

    def test_extracts_internal_links_and_preserves_executable_bits(self):
        archive_path = self.archive()
        tools.extract(archive_path, self.destination)
        compiler = self.destination / "bin/i686-w64-mingw32-clang"
        self.assertTrue(compiler.is_symlink())
        self.assertEqual(compiler.read_bytes(), b"#!/bin/sh\nexit 99\n")
        self.assertEqual(compiler.stat().st_mode & 0o777, 0o755)
        with self.assertRaisesRegex(ValueError, "already exists"):
            tools.extract(archive_path, self.destination)

    def test_rejects_unsafe_archive_entries(self):
        for unsafe in (
            member(f"{tools.SOURCE_NAME}/../escape"),
            member(f"/{tools.SOURCE_NAME}/absolute"),
            member("other-root/file"),
            member(f"{tools.SOURCE_NAME}/hardlink", kind=tarfile.LNKTYPE, link="bin/clang-wrapper.sh"),
            member(f"{tools.SOURCE_NAME}/fifo", kind=tarfile.FIFOTYPE),
            member(f"{tools.SOURCE_NAME}/device", kind=tarfile.CHRTYPE),
            member(f"{tools.SOURCE_NAME}/link", kind=tarfile.SYMTYPE, link="../../escape"),
            member(f"{tools.SOURCE_NAME}/absolute-link", kind=tarfile.SYMTYPE, link="/tmp/outside"),
            member(f"{tools.SOURCE_NAME}/bin/clang-wrapper.sh"),
        ):
            with self.subTest(name=unsafe[0].name):
                archive_path = self.archive([unsafe])
                with self.assertRaises(ValueError):
                    tools.extract(archive_path, self.destination)
                self.assertFalse(self.destination.exists())
                self.assertEqual(list(self.destination.parent.iterdir()), [])
                self.assertFalse((self.root / "escape").exists())

    def test_rejects_write_through_link_parent_before_extraction(self):
        archive_path = self.archive([
            member(f"{tools.SOURCE_NAME}/linked", kind=tarfile.SYMTYPE, link="bin"),
            member(f"{tools.SOURCE_NAME}/linked/injected"),
        ])
        with self.assertRaisesRegex(ValueError, "non-directory parent"):
            tools.extract(archive_path, self.destination)
        self.assertFalse(self.destination.exists())

    def test_rejects_link_chain_escape_and_cycles(self):
        for entries in (
            [member(f"{tools.SOURCE_NAME}/sub/deeper", kind=tarfile.SYMTYPE, link="../bin"),
             member(f"{tools.SOURCE_NAME}/escape", kind=tarfile.SYMTYPE, link="sub/deeper/../../outside")],
            [member(f"{tools.SOURCE_NAME}/cycle", kind=tarfile.SYMTYPE, link="cycle")],
            [member(f"{tools.SOURCE_NAME}/cycle-a", kind=tarfile.SYMTYPE, link="cycle-b"),
             member(f"{tools.SOURCE_NAME}/cycle-b", kind=tarfile.SYMTYPE, link="cycle-a")],
            [member(f"{tools.SOURCE_NAME}/dangling", kind=tarfile.SYMTYPE, link="missing")],
        ):
            with self.subTest(entries=entries):
                archive_path = self.archive(entries)
                with self.assertRaises(ValueError):
                    tools.extract(archive_path, self.destination)
                self.assertFalse(self.destination.exists())

    def test_missing_layout_is_not_published(self):
        archive_path = self.archive([member(f"{tools.SOURCE_NAME}/README")], required=False)
        with self.assertRaisesRegex(ValueError, "Required toolchain file"):
            tools.extract(archive_path, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertEqual(list(self.destination.parent.iterdir()), [])

    def test_existing_folder_and_dangling_link_are_untouched(self):
        archive_path = self.archive()
        self.destination.mkdir(parents=True)
        (self.destination / "keep").write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            tools.extract(archive_path, self.destination)
        self.assertEqual((self.destination / "keep").read_bytes(), b"existing")
        linked = self.root / "dangling"
        linked.symlink_to(self.root / "absent")
        with self.assertRaisesRegex(ValueError, "already exists"):
            tools.extract(archive_path, linked)
        self.assertTrue(linked.is_symlink())

    def test_symlink_destination_parent_is_rejected(self):
        archive_path = self.archive()
        real = self.root / "real"
        real.mkdir()
        linked = self.root / "linked"
        linked.symlink_to(real)
        with self.assertRaisesRegex(ValueError, "symlink parent"):
            tools.extract(archive_path, linked / tools.SOURCE_NAME)
        self.assertEqual(list(real.iterdir()), [])

    def test_default_reuses_verified_cached_archive_without_network(self):
        archive_path = self.archive()
        cache = self.root / ".cache/host-tools"
        cache.mkdir(parents=True)
        archive_path.rename(cache / tools.ARCHIVE_NAME)
        with patch.object(tools, "urlopen", side_effect=AssertionError("No network expected")):
            self.main()
        self.assertTrue((cache / tools.SOURCE_NAME / "bin/i686-w64-mingw32-clang").is_file())

    def test_existing_toolchain_cli_refuses_without_download(self):
        (self.root / ".cache/host-tools" / tools.SOURCE_NAME).mkdir(parents=True)
        stderr = io.StringIO()
        with patch.object(tools, "urlopen", side_effect=AssertionError("No network expected")), \
                contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            self.main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn("--verify-only", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_linux_guard_and_verify_only_local_archive(self):
        archive_path = self.archive()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.main("--archive", str(archive_path), system="Linux")
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(tools, "urlopen", side_effect=AssertionError("No network expected")):
            self.main("--archive", str(archive_path), "--verify-only", system="Linux")
        self.assertIn("Verified LLVM-MinGW", output.getvalue())
        self.assertFalse((self.root / ".cache").exists())

    def test_download_is_streamed_and_rejects_corruption(self):
        class Stream(io.BytesIO):
            def read(stream, size=-1):
                self.assertEqual(size, tools.CHUNK_SIZE)
                return super(Stream, stream).read(size)

        destination = self.root / "download" / tools.ARCHIVE_NAME
        payload = b"archive payload"
        with patch.object(tools, "urlopen", side_effect=lambda *args, **kwargs: Stream(payload)):
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                tools.download(destination)
            self.assertEqual(list(destination.parent.iterdir()), [])
            with patch.object(tools, "SHA256", hashlib.sha256(payload).hexdigest()):
                tools.download(destination)
            self.assertEqual(destination.read_bytes(), payload)
            with self.assertRaisesRegex(ValueError, "already exists"):
                tools.download(destination)
            self.assertEqual(destination.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
