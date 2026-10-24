#!/usr/bin/env python3
"""Test a relocated package while denying access to the build tree and MacPorts."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--skip-gpu", action="store_true", help="for a build VM without a usable Metal GPU")
    parser.add_argument("--setup", action="store_true", help="also download and install Steam and Visual C++ in the disposable prefix")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Run on the macOS host with permission to access its GPU and network.")
    source = args.package.resolve()
    if not (source / "doom-runner").is_file() or (source / "build/prefixes").exists():
        parser.error("Provide a fresh package, before setup creates personal prefix data.")
    subprocess.run(["bash", str(ROOT / "independent/scripts/smoke-wine.sh"), "--compile-only"], check=True)
    with tempfile.TemporaryDirectory(prefix="doom-portable-test-", dir="/private/tmp") as temporary:
        temporary = Path(temporary)
        package = temporary / "Relocated runner with spaces"
        shutil.copytree(source, package, symlinks=True)
        probes = temporary / "probes"
        probes.mkdir()
        names = ["wine-basic-i386.exe", "wine-basic-x86_64.exe", "wine-https-x86_64.exe"]
        if not args.skip_gpu:
            names.append("wine-vulkan-x86_64.exe")
        for name in names:
            shutil.copy2(ROOT / "build/smoke-upstream" / name, probes / name)
        profile = temporary / "clean-host.sb"
        blocked = [ROOT, Path("/opt/local"), Path("/opt/homebrew"), Path("/usr/local")]
        profile.write_text('(version 1)\n(allow default)\n' + ''.join(
            f'(deny file-read* (subpath {json.dumps(str(path))}))\n' for path in blocked))
        environment = {key: value for key, value in os.environ.items()
                       if key in {"HOME", "USER", "LOGNAME", "TMPDIR", "SHELL", "LANG"}}
        environment.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", WINEDEBUG="-all",
                           WINEDLLOVERRIDES="winemenubuilder.exe=d;mscoree,mshtml=")
        prefix = package / "build/prefixes/portable-smoke"
        runner = ["/bin/bash", str(package / "independent/scripts/run-wine.sh"), "--prefix", str(prefix), "--"]

        def check(command, timeout=180):
            print("Checking:", *command, flush=True)
            subprocess.run(["/usr/bin/sandbox-exec", "-f", str(profile), *map(str, command)],
                           env=environment, cwd=temporary, check=True, timeout=timeout)

        try:
            check([str(package / "bin/python3"), "-c", '''
import bz2, ctypes, lzma, pathlib, sqlite3, ssl, sys, urllib.request
assert pathlib.Path(sys.prefix).is_relative_to(pathlib.Path(sys.argv[1]))
request = urllib.request.Request("https://cdn.fastly.steamstatic.com/client/installer/SteamSetup.exe", method="HEAD")
with urllib.request.urlopen(request, timeout=30) as response:
    assert response.status == 200
print("PASS: bundled Python, native extension imports, and verified HTTPS.")
''', str(package)])
            check([str(package / "doom-runner"), "config"])
            check([*runner, "--version"])
            check([*runner, "wineboot", "--init"])
            for name in names:
                check([*runner, str(probes / name)])
            if args.setup:
                check([str(package / "bin/python3"), str(package / "independent/scripts/setup-game.py"),
                       "--prefix", str(prefix)], timeout=1200)
        finally:
            # Only stop this disposable prefix, never the user's Steam or game.
            stop_environment = dict(environment, WINEPREFIX=str(prefix))
            server = package / "artifacts/wine-upstream/bin/wineserver"
            # Setup can already have stopped this server after the client update.
            stopped = subprocess.run([str(server), "-k"], env=stop_environment, timeout=30)
            if stopped.returncode not in (0, 1):
                stopped.check_returncode()
            subprocess.run([str(server), "-w"], env=stop_environment, timeout=30, check=True)
        print("PASS: relocated package runs without the checkout, MacPorts, Homebrew, or host Python.")
        if args.skip_gpu:
            print("GPU/presentation/gameplay remain untested by this run.")
        else:
            print("Vulkan device creation passed. Steam UI, presentation, and gameplay need a clean physical Mac test.")


if __name__ == "__main__":
    main()
