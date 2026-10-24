#!/usr/bin/env python3
"""Fetch and verify the pinned DOOM MoltenVK source; never install a runtime."""
import argparse
import hashlib
import io
import posixpath
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from urllib.request import urlopen

COMMIT = "628683c1822614acf97b185f66817a875ba094a4"
SHA256 = "3e173609ab186de8435000c0b5c8262b25c08f7f95d2c158a71ba425fff160fb"
URL = f"https://codeload.github.com/quanticdynamics/MoltenVK-DOOM2016/tar.gz/{COMMIT}"
ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = f"MoltenVK-DOOM2016-{COMMIT}"


def verify(data):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Source archive SHA-256 mismatch; refusing extraction")


def extract(data, destination):
    """Extract files and internal symlinks under the expected archive root."""
    verify(data)
    if destination.exists():
        raise ValueError(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != ARCHIVE_ROOT or ".." in parts
                    or not (member.isfile() or member.isdir() or member.issym())):
                raise ValueError(f"Unsupported archive entry: {member.name}")
            if member.issym():
                link = posixpath.normpath(posixpath.join(
                    posixpath.dirname(member.name), member.linkname))
                if not link.startswith(ARCHIVE_ROOT + "/"):
                    raise ValueError(f"Escaping symlink: {member.name}")
        with tempfile.TemporaryDirectory(dir=destination.parent) as staging:
            # Links come last so writes cannot traverse an archive symlink.
            for member in sorted(members, key=lambda entry: entry.issym()):
                target = Path(staging).joinpath(*PurePosixPath(member.name).parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.issym():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(member.linkname)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source:
                        target.write_bytes(source.read())
                    target.chmod(member.mode & 0o777)
            (Path(staging) / ARCHIVE_ROOT).rename(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a local archive (no network)")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.archive:
        data = args.archive.read_bytes()
    else:
        with urlopen(URL, timeout=120) as response:
            data = response.read()
    verify(data)
    print(f"Verified {COMMIT}: SHA-256 {SHA256}")
    if not args.verify_only:
        destination = ROOT / "third_party" / ARCHIVE_ROOT
        extract(data, destination)
        print(f"Source ready: {destination}")


if __name__ == "__main__":
    main()
