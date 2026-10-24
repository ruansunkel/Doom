#!/usr/bin/env python3
"""Install or restore the source-built CEF wrapper in the independent prefix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data, mode=0o755):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".doom-ui-", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def install(cef, wrapper, *, restore=False):
    """Preserve Valve's helper before replacement; accept only our tracked wrapper."""
    helper = cef / "steamwebhelper.exe"
    real = cef / "steamwebhelper_real.exe"
    metadata = cef / ".doom-runner-wrapper.json"
    for path in (helper, real, metadata, wrapper):
        if any(parent.is_symlink() for parent in (path, *path.parents)):
            raise ValueError("Refusing a symlink in the Steam helper or wrapper path.")
    current = helper.read_bytes()
    previous = json.loads(metadata.read_text()) if metadata.exists() else None
    if restore:
        if previous and digest(current) == previous["wrapper_sha256"]:
            original = real.read_bytes()
            if digest(original) != previous["original_sha256"]:
                raise ValueError("The preserved Valve helper does not match its recorded checksum.")
            atomic_write(helper, original)
            return "Restored Valve's helper; the original backup remains available."
        return "The current helper is not the tracked wrapper; left it unchanged."
    wrapped = wrapper.read_bytes()
    if not wrapped.startswith(b"MZ"):
        raise ValueError("The compiled wrapper is not a Windows executable.")
    unchanged = False
    if previous and digest(current) == previous["wrapper_sha256"]:
        original = real.read_bytes()
        if digest(original) != previous["original_sha256"]:
            raise ValueError("The preserved Valve helper does not match its recorded checksum.")
        unchanged = digest(current) == digest(wrapped)
    else:
        if real.exists() and not previous:
            raise ValueError("An unmanaged steamwebhelper_real.exe already exists; refusing replacement.")
        if not current.startswith(b"MZ") or len(current) < 1024 * 1024:
            raise ValueError("Unrecognized helper; refusing to preserve it as Valve's executable.")
        original = current
    # Preserve each original version when Steam updates the helper.
    archive = cef / ("steamwebhelper_original_" + digest(original) + ".exe")
    if archive.is_symlink():
        raise ValueError("Refusing a symlink as the original-helper backup.")
    if archive.exists():
        if archive.read_bytes() != original:
            raise ValueError("Existing original-helper backup differs.")
    else:
        atomic_write(archive, original)
    if unchanged:
        return "Steam UI wrapper already installed; Valve helper checksum verified."
    atomic_write(real, original)
    atomic_write(helper, wrapped)
    state = {"original_sha256": digest(original), "wrapper_sha256": digest(wrapped),
             "flags": ["--disable-gpu", "--disable-gpu-compositing", "--single-process"]}
    atomic_write(metadata, (json.dumps(state, indent=2) + "\n").encode(), mode=0o600)
    return "Installed Steam UI wrapper; Valve helper and checksum backup preserved."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true", help="restore the tracked Valve helper for normal verification/updates")
    parser.add_argument("--prefix", type=Path, default=os.environ.get("DOOM_PREFIX", ROOT / "build/prefixes/doom-upstream"))
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Install into the independent Steam prefix on the macOS host.")
    prefix = args.prefix.expanduser().resolve()
    try:
        prefix.relative_to(ROOT / "build/prefixes")
    except ValueError:
        parser.error("Prefixes must stay inside this workspace's build/prefixes directory.")
    cef = prefix / "drive_c/Program Files (x86)/Steam/bin/cef/cef.win64"
    wrapper = ROOT / "build/steam-ui/steamwebhelper.exe"
    try:
        print(install(cef, wrapper, restore=args.restore))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
