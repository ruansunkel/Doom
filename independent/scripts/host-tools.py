#!/usr/bin/env python3
"""Fetch verified LLVM-MinGW for native macOS Wine builds; never execute tools."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import platform
import posixpath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = "20261020"
SOURCE_NAME = f"llvm-mingw-{VERSION}-ucrt-macos-universal"
ARCHIVE_NAME = f"{SOURCE_NAME}.tar.xz"
SHA256 = "e9c13e4ede38e715003ffc674d4d00a1088df8235439d1f0c16188ff0704c17e"
URL = f"https://github.com/mstorsjo/llvm-mingw/releases/download/{VERSION}/{ARCHIVE_NAME}"
ROOT = Path(__file__).resolve().parents[2]
CHUNK_SIZE = 1024 * 1024


def verify(archive_path):
    """Hash a regular archive without reading it all into memory."""
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError(f"Expected a regular archive: {archive_path}")
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError("LLVM-MinGW archive SHA-256 mismatch; refusing extraction")


def unused(destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Destination already exists: {destination}; use --verify-only to verify the archive without trusting or changing an existing toolchain")
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError(f"Destination has a symlink parent: {destination}")


def download(destination):
    """Publish a verified cache file without replacing an existing entry."""
    unused(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        archive_path = Path(staging) / ARCHIVE_NAME
        with urlopen(URL, timeout=120) as response, archive_path.open("xb") as output:
            shutil.copyfileobj(response, output, length=CHUNK_SIZE)
        verify(archive_path)
        # A hard link publishes the complete cache file and refuses overwrite.
        os.link(archive_path, destination)


def checked_members(archive):
    members = {}
    for member in archive.getmembers():
        path = PurePosixPath(member.name)
        if (path.is_absolute() or not path.parts or path.parts[0] != SOURCE_NAME
                or ".." in path.parts or path in members
                or not (member.isfile() or member.isdir() or member.issym())
                or (path == PurePosixPath(SOURCE_NAME) and not member.isdir())):
            raise ValueError(f"Unsafe archive entry: {member.name}")
        if member.issym():
            link = posixpath.normpath(posixpath.join(str(path.parent), member.linkname))
            if (not member.linkname or posixpath.isabs(member.linkname)
                    or not link.startswith(SOURCE_NAME + "/")):
                raise ValueError(f"Escaping symlink: {member.name}")
        members[path] = member
    for path in members:
        if any(parent in members and not members[parent].isdir() for parent in path.parents):
            raise ValueError(f"Archive entry has a non-directory parent: {path}")
    return members


def check_layout(tree):
    for arch in ("i686", "x86_64"):
        target = f"{arch}-w64-mingw32"
        for relative in (f"bin/{target}-clang", f"{target}/include/windows.h", f"{target}/lib/libkernel32.a"):
            path = tree / relative
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"Required toolchain file missing or empty: {relative}")
            if relative.startswith("bin/") and not path.stat().st_mode & 0o111:
                raise ValueError(f"Compiler is not executable: {relative}")


def extract(archive_path, destination):
    """Stage files before links, validate link resolution, then publish the tree."""
    unused(destination)
    verify(archive_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
        tree = Path(staging) / SOURCE_NAME
        with tarfile.open(archive_path, "r:xz") as archive:
            members = checked_members(archive)
            # No writes can follow an archive symlink: create every link last.
            for path, member in sorted(members.items(), key=lambda item: item[1].issym()):
                output = Path(staging).joinpath(*path.parts)
                output.parent.mkdir(parents=True, exist_ok=True)
                if member.isdir():
                    output.mkdir(exist_ok=True)
                elif member.issym():
                    output.symlink_to(member.linkname)
                else:
                    with archive.extractfile(member) as source, output.open("xb") as target:
                        shutil.copyfileobj(source, target, length=CHUNK_SIZE)
                    output.chmod(member.mode & 0o777)
            for path, member in members.items():
                if member.issym():
                    try:
                        # Python 3.13+ tolerates link loops in non-strict mode.
                        # Every compiler-bundle link must resolve to a real file.
                        Path(staging).joinpath(*path.parts).resolve(strict=True).relative_to(tree.resolve())
                    except (OSError, RuntimeError, ValueError) as error:
                        raise ValueError(f"Escaping, missing or cyclic symlink: {path}") from error
        check_layout(tree)
        unused(destination)
        tree.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a local archive (no network)")
    parser.add_argument("--verify-only", action="store_true", help="Verify archive only; also allowed on Linux")
    args = parser.parse_args()
    try:
        if platform.system() != "Darwin" and not args.verify_only:
            raise ValueError("LLVM-MinGW host tool extraction requires macOS; use --verify-only elsewhere")
        cache = ROOT / ".cache" / "host-tools"
        destination = cache / SOURCE_NAME
        if not args.verify_only:
            unused(destination)
        archive_path = args.archive or cache / ARCHIVE_NAME
        if args.archive is None and not (archive_path.exists() or archive_path.is_symlink()):
            download(archive_path)
        if args.verify_only:
            verify(archive_path)
        else:
            extract(archive_path, destination)
        print(f"Verified LLVM-MinGW archive {VERSION}: SHA-256 {SHA256}")
        if not args.verify_only:
            print(f"Host tools ready: {destination}")
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
