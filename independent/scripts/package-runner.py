#!/usr/bin/env python3
"""Package the portable Wine build and its runtime dependencies on macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MAGIC = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}
SYSTEM = ("/usr/lib/", "/System/Library/")


def run(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


def macho(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as source:
        header = source.read(8)
    if header[:4] not in MAGIC:
        return False
    if header[:4] in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"}:
        # Java class files share the fat Mach-O magic, but not its arch table.
        if len(header) < 8:
            return False
        count = struct.unpack(">I" if header[:4] == b"\xca\xfe\xba\xbe" else "<I", header[4:])[0]
        return 0 < count <= 32 and path.stat().st_size >= 8 + count * 20
    return True


def dependencies(path):
    return sorted({line.strip().split(" (compatibility version", 1)[0]
                   for line in run("otool", "-L", path).splitlines()
                   if " (compatibility version" in line})


def rpaths(path):
    lines = run("otool", "-l", path).splitlines()
    return sorted({lines[i + 2].strip().split("path ", 1)[1].rsplit(" (offset", 1)[0]
                   for i, line in enumerate(lines[:-2]) if line.strip() == "cmd LC_RPATH"})


def resolve_load(name, source):
    if name.startswith("@loader_path/"):
        path = source.parent / name.removeprefix("@loader_path/")
    elif name.startswith("@rpath/"):
        suffix = name.removeprefix("@rpath/")
        candidates = [source.parent / suffix]
        for entry in rpaths(source):
            if entry.startswith("@loader_path"):
                entry = str(source.parent) + entry[len("@loader_path"):]
            if entry.startswith("/"):
                candidates.append(Path(entry) / suffix)
        path = next((p for p in candidates if p.is_file()), None)
        if path is None:
            raise ValueError(f"Cannot resolve {name} from {source}")
    elif name.startswith("/"):
        path = Path(name)
    else:
        raise ValueError(f"Unsupported library reference {name} in {source}")
    if not path.is_file():
        raise ValueError(f"Missing dependency {path}")
    return path.resolve()


def relative_load(binary, library):
    return "@loader_path/" + os.path.relpath(library, binary.parent)


def minimum_macos(path):
    commands = run("otool", "-l", path)
    versions = re.findall(r"^\s+minos ([\d.]+)", commands, re.MULTILINE)
    versions += re.findall(r"cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([\d.]+)", commands)
    return max((tuple(map(int, version.split("."))) for version in versions), default=(0, 0))


class Libraries:
    def __init__(self, root):
        self.root = root
        self.native = root / "artifacts/wine-upstream/native"
        self.native.mkdir(parents=True)
        self.mapping = {}
        self.pending = []
        self.names = {}

    def track(self, source, target):
        source = source.resolve()
        if source not in self.mapping:
            self.mapping[source] = target
            self.pending.append(source)
        return self.mapping[source]

    def collect(self, source):
        source = source.resolve()
        if source in self.mapping:
            return self.mapping[source]
        target = self.native / source.name
        if target.name in self.names and self.names[target.name] != source:
            raise ValueError(f"Dependency filename collision: {source}")
        self.names[target.name] = source
        shutil.copy2(source, target)
        return self.track(source, target)

    def alias(self, source, name):
        target = self.collect(source)
        alias = self.native / name
        if alias != target:
            alias.symlink_to(target.name)

    def relocate(self):
        index = 0
        while index < len(self.pending):
            source = self.pending[index]
            index += 1
            target = self.mapping[source]
            target.chmod(target.stat().st_mode | 0o200)
            ids = {line.strip() for line in run("otool", "-D", source).splitlines()[1:]
                   if not line.endswith(":")}
            changes = []
            for name in dependencies(source):
                if name in ids or name.startswith(SYSTEM):
                    continue
                resolved = resolve_load(name, source)
                dependency = self.mapping.get(resolved) or self.collect(resolved)
                changes += ["-change", name, relative_load(target, dependency)]
            if ids:
                changes += ["-id", "@rpath/" + target.name]
            for entry in rpaths(source):
                if entry.startswith("/") and not entry.startswith(SYSTEM):
                    changes += ["-delete_rpath", entry]
            if changes:
                run("install_name_tool", *changes, target)
            run("codesign", "--force", "--sign", "-", target)


def check_package(root):
    """Reject unresolved load commands and external symlinks before publishing."""
    binaries = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError(f"External package symlink: {path}")
        elif macho(path):
            binaries += 1
            ids = {line.strip() for line in run("otool", "-D", path).splitlines()[1:]}
            for name in dependencies(path):
                if name in ids or name.startswith(SYSTEM):
                    continue
                if not name.startswith("@loader_path/"):
                    raise ValueError(f"Nonportable load command {name} in {path}")
                resolved = resolve_load(name, path)
                if not resolved.is_relative_to(root.resolve()):
                    raise ValueError(f"Dependency escapes package: {path}: {name}")
            for entry in rpaths(path):
                if entry.startswith("/") and not entry.startswith(SYSTEM):
                    raise ValueError(f"Nonportable rpath {entry} in {path}")
            run("codesign", "--verify", path)
    return binaries


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)


def package(destination, python):
    wine = ROOT / "artifacts/wine-portable"
    config = ROOT / "build/wine-portable-x86_64/include/config.h"
    expected = '#define SONAME_LIBVULKAN "@loader_path/../../../native/libMoltenVK.dylib"'
    if not config.is_file() or expected not in config.read_text() or not (wine / "bin/wine").is_file():
        raise ValueError("First build: bash independent/scripts/build-wine.sh --portable")
    bridge = wine / "lib/wine/x86_64-unix/win32u.so"
    if b"@loader_path/../../../native/libMoltenVK.dylib\0" not in bridge.read_bytes():
        raise ValueError("Installed Wine bridge is not portable; rebuild Wine with --portable.")
    python_info = json.loads(run(python, "-c", "import json,sys,sysconfig; print(json.dumps("
                                "[sys.executable,sysconfig.get_path('stdlib'),"
                                "sysconfig.get_config_var('VERSION'),"
                                "sysconfig.get_config_var('PYTHONFRAMEWORK')]))"))
    python_exe, stdlib, version, framework = python_info
    if framework:
        # Framework bin/python is a launcher that respawns the app executable.
        # Bundle the actual interpreter so it cannot respawn a builder path.
        python_exe = Path(stdlib).parent.parent / "Resources/Python.app/Contents/MacOS/Python"
    if tuple(map(int, version.split("."))) < (3, 9):
        raise ValueError("Packaging requires Python 3.9 or newer.")
    # Never copy a development prefix, game files, installers or login state.
    shutil.copytree(wine, destination / "artifacts/wine-upstream", symlinks=True)
    libraries = Libraries(destination)
    for source in wine.rglob("*"):
        if macho(source):
            libraries.track(source, destination / "artifacts/wine-upstream" / source.relative_to(wine))
    for name in ("libfreetype.6.dylib", "libgnutls.30.dylib"):
        libraries.alias(Path("/opt/local/lib") / name, name)
    libraries.alias(ROOT / "build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib", "libMoltenVK.dylib")
    python_target = destination / "python/bin/python3"
    python_target.parent.mkdir(parents=True)
    shutil.copy2(python_exe, python_target)
    libraries.track(Path(python_exe), python_target)
    stdlib = Path(stdlib)
    stdlib_target = destination / "python/lib" / ("python" + version)
    shutil.copytree(stdlib, stdlib_target, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "site-packages", "test", "tests", "idlelib", "ensurepip", "config-*"))
    for source in stdlib.rglob("*"):
        target = stdlib_target / source.relative_to(stdlib)
        if target.is_file() and macho(source):
            libraries.track(source, target)
    libraries.relocate()
    minimum = max(minimum_macos(source) for source in libraries.mapping)
    minimum = (minimum + (0, 0, 0))[:3]
    minimum_string = ".".join(map(str, minimum))
    minimum_number = minimum[0] * 10000 + minimum[1] * 100 + minimum[2]
    scripts = destination / "independent/scripts"
    scripts.mkdir(parents=True)
    for name in ("doom-runner.sh", "run-wine.sh", "setup-game.py", "steam-bootstrap.py", "install-steam-wrapper.py"):
        shutil.copy2(ROOT / "independent/scripts" / name, scripts / name)
    wrapper = destination / "build/steam-ui/steamwebhelper.exe"
    wrapper.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "build/steam-ui/steamwebhelper.exe", wrapper)
    certificates = destination / "certificates.pem"
    shutil.copy2("/opt/local/share/curl/curl-ca-bundle.crt", certificates)
    executable(destination / "bin/python3", '''#!/bin/bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
unset PYTHONPATH PYTHONSTARTUP PYTHONUSERBASE DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
export PYTHONHOME="$root/python" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export SSL_CERT_FILE="$root/certificates.pem"
exec "$root/python/bin/python3" -s "$@"
''')
    launcher = '''#!/bin/bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
IFS=. read -r os_major os_minor os_patch <<< "$(/usr/bin/sw_vers -productVersion)"
if (( os_major * 10000 + ${os_minor:-0} * 100 + ${os_patch:-0} < REQUIRED_MACOS_NUMBER )); then
  echo 'This build requires macOS REQUIRED_MACOS_STRING or newer.' >&2
  exit 1
fi
export PATH="$root/bin:/usr/bin:/bin:/usr/sbin:/sbin"
exec /bin/bash "$root/independent/scripts/doom-runner.sh" "$@"
'''
    executable(destination / "doom-runner", launcher.replace("REQUIRED_MACOS_NUMBER", str(minimum_number))
               .replace("REQUIRED_MACOS_STRING", minimum_string))
    licenses = destination / "licenses"
    licenses.mkdir()
    shutil.copytree("/opt/local/share/doc", licenses / "native-dependencies", symlinks=False)
    shutil.copy2(stdlib / "LICENSE.txt", licenses / "PYTHON-LICENSE.txt")
    shutil.copy2(ROOT / "third_party/wine-11.20/COPYING.LIB", licenses / "WINE-COPYING.LIB")
    shutil.copy2(ROOT / "third_party/MoltenVK-DOOM2016-628683c1822614acf97b185f66817a875ba094a4/LICENSE",
                 licenses / "MOLTENVK-LICENSE")
    sources = licenses / "sources"
    sources.mkdir()
    for archive in ("wine-11.20.tar.xz", "moltenvk-doom2016.tar.gz"):
        shutil.copy2(ROOT / "third_party" / archive, sources / archive)
    shutil.copytree(ROOT / "independent", sources / "runner/independent",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "README.md", sources / "runner/README.md")
    # Preserve cached native dependency sources when available on the builder.
    distfiles = Path("/opt/local/var/macports/distfiles")
    if distfiles.is_dir():
        shutil.copytree(distfiles, sources / "macports", symlinks=False)
    shutil.copy2(ROOT / "independent/docs/PORTABLE.md", destination / "README.md")
    manifest = {
        "wine": "11.20", "graphics": "patched MoltenVK", "python": version, "minimum_macos": minimum_string,
        "native_dependencies": [{"source": str(source), "file": str(target.relative_to(destination)),
                                 "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
                                for source, target in sorted(libraries.mapping.items())],
        "macports": run("/opt/local/bin/port", "-q", "installed"),
    }
    (destination / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    count = check_package(destination)
    print(f"Verified {count} bundled Mach-O files: dependencies resolve inside the package or macOS.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/doom-runner-macos")
    parser.add_argument("--python", type=Path, default=Path("/opt/local/bin/python3.14"))
    args = parser.parse_args()
    try:
        if platform.system() != "Darwin":
            raise ValueError("Package on the macOS build host.")
        destination = args.output.absolute()
        if destination.exists() or destination.is_symlink():
            raise ValueError("Output already exists; choose a new --output directory.")
        if any(p.is_symlink() for p in destination.parents):
            raise ValueError("Package output parents must not be symlinks.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".package-", dir=destination.parent) as temporary:
            staging = Path(temporary) / destination.name
            staging.mkdir()
            package(staging, args.python)
            staging.rename(destination)
        print(f"Portable runner: {destination}")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
