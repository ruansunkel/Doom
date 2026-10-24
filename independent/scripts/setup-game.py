#!/usr/bin/env python3
"""Install Windows Steam and DOOM prerequisites into an isolated Wine prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
INSTALLERS = {
    "SteamSetup.exe": "https://cdn.fastly.steamstatic.com/client/installer/SteamSetup.exe",
    "vc_redist.x64.exe": "https://aka.ms/vc14/vc_redist.x64.exe",
}
STEAM_FLAGS = ["-cef-disable-gpu", "-no-cef-sandbox"]


def prefix_path(value):
    path = Path(value).expanduser().resolve()
    allowed = ROOT / "build/prefixes"
    try:
        relative = path.relative_to(allowed)
    except ValueError:
        raise ValueError("Prefixes must stay inside this workspace's build/prefixes directory.") from None
    if not relative.parts or (path.exists() and not path.is_dir()):
        raise ValueError("Choose a prefix directory below build/prefixes/.")
    return path


def digest(path):
    hashed = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


def check_installer(path):
    if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file():
        raise ValueError("Installer must be a regular file with no symlink parents.")
    size = path.stat().st_size
    with path.open("rb") as source:
        header = source.read(64)
        if size < 1024 or header[:2] != b"MZ":
            raise ValueError("Download is not a Windows installer.")
        offset = struct.unpack_from("<I", header, 60)[0]
        if not 64 <= offset <= size - 4:
            raise ValueError("Invalid Windows installer header.")
        source.seek(offset)
        if source.read(4) != b"PE\0\0":
            raise ValueError("Invalid Windows installer signature.")


def installer(name):
    """Cache official HTTPS downloads and record measured hashes, not publisher pins."""
    cache = ROOT / ".cache/host-tools"
    if any(parent.is_symlink() for parent in (cache, *cache.parents)):
        raise ValueError("Refusing symlinks in the installer cache.")
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / name
    receipt = cache / (name + ".download.json")
    if receipt.is_symlink():
        raise ValueError("Refusing a symlink as the installer receipt.")
    if not path.exists() and not path.is_symlink():
        print(f"Downloading {name} from its official source...", flush=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            downloaded = Path(temporary) / name
            with urlopen(INSTALLERS[name], timeout=120) as response, downloaded.open("xb") as output:
                if not response.geturl().startswith("https://"):
                    raise ValueError("Installer download redirected away from HTTPS.")
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            check_installer(downloaded)
            os.link(downloaded, path)
    check_installer(path)
    measured = digest(path)
    if receipt.exists():
        saved = json.loads(receipt.read_text())
        if saved.get("sha256") != measured or saved.get("url") != INSTALLERS[name]:
            raise ValueError("Cached installer differs from its download receipt; inspect the cache before retrying.")
    else:
        with receipt.open("x") as output:
            json.dump({"url": INSTALLERS[name], "sha256": measured}, output, indent=2)
            output.write("\n")
    return path


def client_files(steam):
    cef = steam / "bin/cef/cef.win64"
    helper = cef / "steamwebhelper.exe"
    metadata = cef / ".doom-runner-wrapper.json"
    original = cef / "steamwebhelper_real.exe"
    if metadata.is_file() and not metadata.is_symlink() and helper.is_file() and original.is_file():
        state = json.loads(metadata.read_text())
        if (not helper.is_symlink() and not original.is_symlink()
                and digest(helper) == state.get("wrapper_sha256")
                and digest(original) == state.get("original_sha256")):
            helper = original
    return [steam / "steamui.dll", steam / "steamclient.dll",
            helper, cef / "libcef.dll"]


def client_ready(steam):
    return all(path.is_file() and path.stat().st_size > 1024 * 1024 for path in client_files(steam))


def game_ready(prefix):
    steamapps = prefix / "drive_c/Program Files (x86)/Steam/steamapps"
    if not (steamapps / "common/DOOM/DOOMx64vk.exe").is_file():
        return False
    try:
        manifest = (steamapps / "appmanifest_379720.acf").read_text()
    except FileNotFoundError:
        return False
    state = re.search(r'"StateFlags"\s+"(\d+)"', manifest)
    return bool(state and int(state.group(1)) == 4)


def stop_prefix(prefix):
    """Only used for the setup-owned initial Steam update, before sign-in."""
    environment = dict(os.environ, WINEPREFIX=str(prefix))
    for name in ("WINESERVERSOCKET", "WINESERVER", "WINELOADER"):
        environment.pop(name, None)
    server = ROOT / "artifacts/wine-upstream/bin/wineserver"
    subprocess.run([str(server), "-k"], env=environment, check=True, timeout=30)
    subprocess.run([str(server), "-w"], env=environment, check=True, timeout=30)


def disable_autostart(prefix, wine, log):
    command = ["bash", str(ROOT / "independent/scripts/run-wine.sh"), "--prefix", str(prefix), "--",
               "reg", "delete", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run", "/v", "Steam", "/f"]
    result = subprocess.run(command, env=wine, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode not in (0, 1):
        raise ValueError("Could not disable Steam's prefix autostart; see the prefix setup log.")


def bootstrap_client(prefix, steam, wine, log, timeout):
    print("Steam is downloading its first client update; this can take several minutes...", flush=True)
    # File verification is required to download the initial client. The normal
    # launcher uses -noverifyfiles only after the complete UI has been wrapped.
    command = ["bash", str(ROOT / "independent/scripts/run-wine.sh"), "--prefix", str(prefix),
               "--", r"C:\Program Files (x86)\Steam\Steam.exe", *STEAM_FLAGS, "-silent"]
    process = subprocess.Popen(command, cwd=steam, env=wine, stdout=log, stderr=subprocess.STDOUT)
    stable = None
    deadline = time.monotonic() + timeout
    next_notice = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if client_ready(steam) and (steam / "package/steam_client_win64.installed").is_file():
                snapshot = [(p.stat().st_size, p.stat().st_mtime_ns) for p in client_files(steam)]
                if snapshot == stable:
                    disable_autostart(prefix, wine, log)
                    return
                stable = snapshot
            elif process.poll() not in (None, 0):
                raise ValueError("Steam's initial update exited with an error; see the prefix setup log and retry setup.")
            if time.monotonic() >= next_notice:
                print("Still waiting for Steam's initial client update...", flush=True)
                next_notice = time.monotonic() + 20
            time.sleep(3)
        raise ValueError("Steam's initial update timed out; check the prefix setup log and rerun setup.")
    finally:
        stop_prefix(prefix)
        process.wait(timeout=30)


def setup(prefix, *, prerequisites_only=False, timeout=600):
    runtime = ROOT / "artifacts/wine-upstream/bin/wine"
    graphics = ROOT / "build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib"
    if (ROOT / "package-manifest.json").is_file() or (ROOT / "artifacts/wine-upstream/native").is_dir():
        graphics = ROOT / "artifacts/wine-upstream/native/libMoltenVK.dylib"
    if not runtime.is_file() or not graphics.is_file():
        raise ValueError("Build the runtime first: bash independent/scripts/build-all.sh")
    steam = prefix / "drive_c/Program Files (x86)/Steam"
    needs_runtime = not (prefix / "drive_c/windows/system32/mfc140u.dll").is_file()
    needs_steam = not (steam / "Steam.exe").is_file()
    # Download before initializing Wine, so network waits do not trigger autostarts.
    redist = installer("vc_redist.x64.exe") if needs_runtime else None
    steam_installer = installer("SteamSetup.exe") if needs_steam and not prerequisites_only else None
    prefix.mkdir(parents=True, exist_ok=True)
    log_path = prefix / ".doom-runner-setup.log"
    wine = dict(os.environ, WINEDEBUG="-all", WINEDLLOVERRIDES="winemenubuilder.exe=d;mscoree,mshtml=")
    runner = ["bash", str(ROOT / "independent/scripts/run-wine.sh"), "--prefix", str(prefix), "--"]
    with log_path.open("a") as log:
        def run(*arguments, accepted=(0,)):
            result = subprocess.run([*runner, *map(str, arguments)], env=wine, stdout=log, stderr=subprocess.STDOUT)
            if result.returncode not in accepted:
                raise ValueError(f"Wine setup command failed (status {result.returncode}); see {log_path}")

        if not (prefix / "system.reg").is_file():
            print("Creating an isolated Windows prefix...", flush=True)
            run("wineboot", "--init")
            run("reg", "add", r"HKCU\Software\Wine", "/v", "Version", "/t", "REG_SZ", "/d", "win10", "/f")
        if redist:
            print("Installing DOOM's x64 Visual C++ prerequisite...", flush=True)
            run(redist, "/install", "/quiet", "/norestart", "/log", r"C:\doom-vc-redist.log", accepted=(0, 194))
            if not (prefix / "drive_c/windows/system32/mfc140u.dll").is_file():
                raise ValueError("Visual C++ installation did not supply mfc140u.dll; see the prefix setup log.")
        if prerequisites_only:
            print("DOOM's application prerequisite is ready.", flush=True)
            return
        if steam_installer:
            print("Installing Windows Steam...", flush=True)
            run(steam_installer, "/S")
        if not (steam / "Steam.exe").is_file():
            raise ValueError("Steam installation did not create Steam.exe; see the prefix setup log.")
        # Wine startup must not bypass the wrapper-managed launch command.
        disable_autostart(prefix, wine, log)
        if not client_ready(steam):
            stop_prefix(prefix)
            subprocess.run([sys.executable, str(ROOT / "independent/scripts/steam-bootstrap.py"),
                            "--prefix", str(prefix)], check=True)
            bootstrap_client(prefix, steam, wine, log, timeout)
        if not (ROOT / "build/steam-ui/steamwebhelper.exe").is_file():
            subprocess.run(["bash", str(ROOT / "independent/scripts/build-steam-wrapper.sh")], check=True)
        subprocess.run([sys.executable, str(ROOT / "independent/scripts/install-steam-wrapper.py"),
                        "--prefix", str(prefix)], check=True)
    print("Steam setup is ready. Launch Steam, sign in there, and install DOOM (2016).", flush=True)
    print(f"Setup log: {log_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=os.environ.get("DOOM_PREFIX", ROOT / "build/prefixes/doom-upstream"))
    parser.add_argument("--prerequisites-only", action="store_true")
    parser.add_argument("--print-prefix", action="store_true")
    parser.add_argument("--check-game", action="store_true", help="check Steam's fully installed DOOM state")
    parser.add_argument("--timeout", type=int, default=600, help="seconds allowed for Steam's first client update")
    args = parser.parse_args()
    try:
        prefix = prefix_path(args.prefix)
        if args.print_prefix:
            print(prefix)
            return
        if args.check_game:
            if not game_ready(prefix):
                raise ValueError("DOOM is not fully installed. Run doom-runner.sh install and wait for Steam to finish downloading.")
            return
        if platform.system() != "Darwin":
            raise ValueError("Run game setup on the macOS host.")
        if args.timeout <= 0:
            raise ValueError("--timeout must be positive.")
        setup(prefix, prerequisites_only=args.prerequisites_only, timeout=args.timeout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
