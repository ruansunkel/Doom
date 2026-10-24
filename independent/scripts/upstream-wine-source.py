#!/usr/bin/env python3
"""Fetch the pinned upstream Wine source without changing installed runtimes."""
import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen

VERSION = "11.20"
NAME = f"wine-{VERSION}"
SHA256 = "eac8ca448f9c0087f963026b4dc276d1e2b7fbb64056edc093e59bbb7e56fe28"
URL = f"https://dl.winehq.org/wine/source/11.x/{NAME}.tar.xz"
ROOT = Path(__file__).resolve().parents[2]


def verify(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected a regular Wine source archive.")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != SHA256:
        raise ValueError("Upstream Wine archive SHA-256 mismatch.")


def extract(archive_path, destination):
    if destination.exists() or destination.is_symlink():
        raise ValueError("The upstream source destination already exists.")
    if any(parent.is_symlink() for parent in destination.parents):
        raise ValueError("Refusing a symlink parent for source extraction.")
    verify(archive_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        with tarfile.open(archive_path, "r:xz") as archive:
            members = archive.getmembers()
            for entry in members:
                path = PurePosixPath(entry.name)
                if (path.is_absolute() or not path.parts or path.parts[0] != NAME or ".." in path.parts
                        or not (entry.isdir() or entry.isfile())):
                    raise ValueError(f"Unsupported source archive entry: {entry.name}")
            for entry in members:
                target = Path(temporary).joinpath(*PurePosixPath(entry.name).parts)
                if entry.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(entry) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(entry.mode & 0o777)
        tree = Path(temporary) / NAME
        for required in ("configure", "COPYING.LIB", "VERSION"):
            if not (tree / required).is_file():
                raise ValueError(f"Missing Wine source file: {required}")
        if destination.exists() or destination.is_symlink():
            raise ValueError("Source destination appeared during extraction.")
        tree.rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    archive = ROOT / "third_party" / f"{NAME}.tar.xz"
    try:
        if not archive.exists() and not archive.is_symlink():
            archive.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=archive.parent) as temporary:
                downloaded = Path(temporary) / archive.name
                with urlopen(URL, timeout=120) as response, downloaded.open("xb") as output:
                    shutil.copyfileobj(response, output)
                verify(downloaded)
                os.link(downloaded, archive)
        verify(archive)
        if not args.verify_only:
            extract(archive, ROOT / "third_party" / NAME)
        print(f"Verified upstream Wine {VERSION}: SHA-256 {SHA256}")
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
