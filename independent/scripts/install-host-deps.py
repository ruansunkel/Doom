#!/usr/bin/env python3
"""Install the fixed native Wine dependency set through MacPorts."""
import argparse
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import sys
import tempfile

PORT = "/opt/local/bin/port"
COMMANDS = (
    [PORT, "-N", "install", "pkgconfig", "bison"],
    [PORT, "-N", "install", "freetype", "+universal", "gnutls", "+universal"],
)
PORTGROUP = Path("/opt/local/var/macports/sources/rsync.macports.org/macports/release/tarballs/ports/"
                 "_resources/port1.0/group/muniversal-1.1.tcl")
LIBFFI_PORTGROUP = PORTGROUP.with_name("muniversal-1.0.tcl")
GMP_REINSTALL = (
    [PORT, "-N", "uninstall", "gmp"],
    [PORT, "-N", "clean", "gmp"],
    [PORT, "-N", "-s", "install", "gmp", "+universal"],
    [PORT, "-N", "clean", "nettle"],
)
HEADER_MERGE_LINES = (
    r'                    if { ! [catch {system "/usr/bin/lipo -create \"${dir1}/${fl}\" \"${dir2}/${fl}\" -output \"${dir}/${fl}\""}] } {',
    r'                    } elseif { ! [catch {system "/usr/bin/libtool \"${dir1}/${fl}\" \"${dir2}/${fl}\" -o \"${dir}/${fl}\""}] } {',
)


def patch_header_merge(text):
    """Keep reviewed muniversal header inputs out of both binary merge tools."""
    guarded = tuple(line.replace('{ ! [catch', '{ ![string match "*.h" $fl] && ! [catch', 1)
                    for line in HEADER_MERGE_LINES)
    # The reviewed 1.0 and 1.1 implementations differ only in indentation here.
    lines = text.splitlines(keepends=True)
    bodies = [line.strip() for line in lines]
    counts = [(bodies.count(before.strip()), bodies.count(after.strip()))
              for before, after in zip(HEADER_MERGE_LINES, guarded)]
    if counts == [(0, 1), (0, 1)]:
        return text
    if counts != [(1, 0), (1, 0)]:
        raise ValueError("Unrecognized muniversal header merge source; refusing to patch.")
    replacements = {before.strip(): after.strip()
                    for before, after in zip(HEADER_MERGE_LINES, guarded)}
    return "".join(line.replace(line.strip(), replacements[line.strip()], 1)
                   if line.strip() in replacements else line for line in lines)


def repair_header_merge(path=PORTGROUP):
    """Back up the known source once and atomically replace it, preserving mode."""
    backup = path.with_name(path.name + ".doom-runner-original")
    for candidate in (path, backup):
        if any(parent.is_symlink() for parent in (candidate, *candidate.parents)):
            raise ValueError("Refusing symlinks in the MacPorts PortGroup or backup path.")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("The MacPorts PortGroup must be a regular file.")
    original = path.read_bytes()
    patched = patch_header_merge(original.decode("utf-8")).encode("utf-8")
    if patched == original:
        print("MacPorts header merge workaround is already applied.", flush=True)
        return
    if backup.exists():
        if not backup.is_file() or backup.read_bytes() != original:
            raise ValueError("Existing MacPorts PortGroup backup differs; refusing replacement.")
    else:
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(original)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".doom-muniversal-", delete=False) as output:
            temporary = Path(output.name)
            output.write(patched)
            output.flush()
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
            if os.geteuid() == 0:
                os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"Applied MacPorts header merge workaround; original saved at {backup}", flush=True)


def reset_build_signals():
    """Restore signals inherited through Authorization Services before builds."""
    # Authorization Services / osascript can inherit a blocked signal mask.
    # Passing it to configure makes alarm-based probes sleep indefinitely.
    signal.pthread_sigmask(signal.SIG_SETMASK, set())
    for signum in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, signal.SIG_DFL)


def check_headers(include=Path("/opt/local/include"), *, repair_gmp=False, repair_libffi=False):
    """Identify the observed archive-as-header failure without guessing from logs."""
    for names, repair, option in (
        (("gmp.h",), repair_gmp, "--repair-gmp"),
        (("ffi.h", "ffitarget.h"), repair_libffi, "--repair-libffi"),
    ):
        if repair:
            continue
        for name in names:
            path = include / name
            if path.is_file():
                with path.open("rb") as source:
                    damaged = source.read(8) == b"!<arch>\n"
                if damaged:
                    raise ValueError(
                        f"{path} is an ar archive instead of a C header. Run: "
                        f"sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install {option}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="install; requires macOS administrator privileges")
    parser.add_argument("--repair-gmp", action="store_true",
                        help="plan a targeted MacPorts header merge fix and source reinstall of GMP; --install applies it")
    parser.add_argument("--repair-libffi", action="store_true",
                        help="repair muniversal 1.0 headers, reinstall libffi, and reconfigure failed Python")
    args = parser.parse_args()
    commands = []
    if args.repair_gmp:
        commands.extend(GMP_REINSTALL)
    if args.repair_libffi:
        commands.extend(([PORT, "-N", "uninstall", "libffi"],
                         [PORT, "-N", "-s", "install", "libffi", "+universal"],
                         [PORT, "-N", "clean", "python314"]))
    commands.extend(COMMANDS)
    for path in (PORTGROUP, LIBFFI_PORTGROUP):
        print(f"Guard *.h from binary merging in {path}; keep a private original backup.", flush=True)
    if args.repair_gmp:
        print("Reinstall GMP from source; non-forced uninstall refuses installed dependents.", flush=True)
        print("Clean GMP and the failed Nettle work directory before retrying GnuTLS.", flush=True)
    if args.repair_libffi:
        print("Reinstall libffi without force and reconfigure the failed Python build.", flush=True)
    for command in commands:
        print(" ".join(command), flush=True)
    if not args.install:
        print("Plan only. Pass --install on macOS with administrator privileges.")
        return 0
    if platform.system() != "Darwin" or os.geteuid() != 0:
        parser.error("Run --install on the Mac host with administrator privileges.")
    if not Path(PORT).is_file():
        parser.error("Install the official MacPorts package first.")

    reset_build_signals()
    try:
        check_headers(repair_gmp=args.repair_gmp, repair_libffi=args.repair_libffi)
        # Validate both known sources before changing either. An upstream change
        # must be reviewed rather than patched using a guessed source pattern.
        for path in (PORTGROUP, LIBFFI_PORTGROUP):
            patch_header_merge(path.read_text())
        for path in (PORTGROUP, LIBFFI_PORTGROUP):
            repair_header_merge(path)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    environment = os.environ.copy()
    environment["PATH"] = "/opt/local/bin:/opt/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin"
    for command in commands:
        try:
            subprocess.run(command, env=environment, check=True)
        except subprocess.CalledProcessError as error:
            print(f"MacPorts command failed (status {error.returncode}): {' '.join(command)}", file=sys.stderr)
            print("Inspect the config.log and main.log paths printed by MacPorts above.", file=sys.stderr)
            if "gnutls" in command:
                print("If Nettle failed, check: /usr/bin/file /opt/local/include/gmp.h\n"
                      "If it reports an ar archive, run:\n"
                      "  sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install --repair-gmp\n"
                      "Otherwise, inspect the configure error before selecting a repair.", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
