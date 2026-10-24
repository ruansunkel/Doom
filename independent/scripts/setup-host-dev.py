#!/usr/bin/env python3
"""Prepare native macOS Python development tools and pinned ShellCheck."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
VERSION = "0.11.0"
SHELLCHECK_HASHES = {
    "arm64": ("aarch64", "56affdd8de5527894dca6dc3d7e0a99a873b0f004d7aabc30ae407d3f48b0a79"),
    "x86_64": ("x86_64", "3c89db4edcab7cf1c27bff178882e0f6f27f7afdf54e859fa041fca10febe4c6"),
}


def regular_path(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError(f"Refusing a symlink in the setup path: {path}")


def verify(path, expected):
    regular_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("ShellCheck archive SHA-256 mismatch.")


def extract_shellcheck(archive_path, destination, expected):
    """Accept only the three regular files in the pinned upstream package."""
    regular_path(destination)
    if destination.exists():
        raise ValueError("ShellCheck destination already exists.")
    verify(archive_path, expected)
    destination.parent.mkdir(parents=True, exist_ok=True)
    package = f"shellcheck-v{VERSION}"
    names = {f"{package}/{name}" for name in ("shellcheck", "LICENSE.txt", "README.txt")}
    with tarfile.open(archive_path, "r:xz") as archive:
        members = archive.getmembers()
        if (len(members) != len(names) or {item.name for item in members} != names
                or any(not item.isfile() for item in members)):
            raise ValueError("Unsafe or unexpected ShellCheck archive contents.")
        with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
            staged = Path(temporary) / package
            staged.mkdir()
            for member in members:
                output = staged / Path(member.name).name
                with archive.extractfile(member) as source, output.open("xb") as target:
                    shutil.copyfileobj(source, target)
                output.chmod(0o755 if output.name == "shellcheck" else 0o644)
            staged.rename(destination)


def ensure_shellcheck():
    architecture, expected = SHELLCHECK_HASHES[platform.machine()]
    cache = ROOT / ".cache/host-tools"
    destination = cache / f"shellcheck-v{VERSION}"
    regular_path(destination)
    if (destination / "shellcheck").is_file():
        subprocess.run([str(destination / "shellcheck"), "--version"], check=True)
        return
    filename = f"shellcheck-v{VERSION}.darwin.{architecture}.tar.xz"
    archive = cache / filename
    regular_path(archive)
    if not archive.exists():
        cache.mkdir(parents=True, exist_ok=True)
        url = f"https://github.com/koalaman/shellcheck/releases/download/v{VERSION}/{filename}"
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            downloaded = Path(temporary) / filename
            with urlopen(url, timeout=120) as response, downloaded.open("xb") as target:
                shutil.copyfileobj(response, target)
            verify(downloaded, expected)
            os.link(downloaded, archive)
    extract_shellcheck(archive, destination, expected)


def native_python(path):
    try:
        result = subprocess.run(
            [str(path), "-c", 'import sys; assert sys.platform == "darwin" and sys.version_info >= (3, 10)'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return result.returncode == 0
    except OSError:
        return False


def choose_python(requested):
    if requested:
        if native_python(requested):
            return requested
        raise ValueError("--python must select a native macOS Python 3.10 or newer.")
    for candidate in ("/opt/local/bin/python3.14", "python3.14", "python3.13", "python3.12",
                      "python3.11", "python3.10", sys.executable):
        executable = shutil.which(candidate)
        if executable and native_python(executable):
            return executable
    raise ValueError("Install native Python 3.10+ (for example: sudo port install python314), then rerun setup.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", help="native Python 3.10+ executable used to create .venv")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run development setup on the macOS host.")
    if platform.machine() not in SHELLCHECK_HASHES:
        parser.error("Unsupported macOS architecture.")
    try:
        environment = ROOT / ".venv"
        regular_path(environment)
        if environment.exists():
            if not (environment / "pyvenv.cfg").is_file() or not native_python(environment / "bin/python"):
                raise ValueError("The existing .venv is not a native macOS Python 3.10+ environment; rename it before setup.")
        else:
            subprocess.run([choose_python(args.python), "-m", "venv", str(environment)], check=True)
        subprocess.run([str(environment / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
                        "--requirement", str(ROOT / "requirements-dev.txt")], check=True)
        ensure_shellcheck()
        print("Host development tools ready. Run: bash independent/scripts/check.sh", flush=True)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
