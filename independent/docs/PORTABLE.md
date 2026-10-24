# Portable DOOM runner for macOS

This folder contains Wine 11.20, patched MoltenVK, the Steam UI wrapper,
Python, TLS certificates, and the native libraries needed by this build.
MacPorts, Homebrew, Python installations, Xcode, and compilers are not required
on the destination Mac. The default package targets Apple Silicon Macs.
The current build's native dependencies require
**macOS 27.0 or newer**, plus Rosetta on Apple Silicon. Each package records
its measured minimum macOS version in `package-manifest.json`; its launcher
checks that version before starting.
Gameplay has been confirmed only on M1 Max with macOS 27.0.1; this package
still needs validation on a separate clean physical Mac. The build can be
performed in a macOS VM with the build prerequisites; that VM configuration
has not been tested. GPU/gameplay validation belongs on a suitable physical Mac.

Copy the **entire folder** to a writable local directory before setup. Keep its
internal layout intact. Start Terminal in that folder and run:

```bash
./doom-runner config
./doom-runner setup
./doom-runner steam
```

Sign in to your own Steam account in Steam's window. Keep Steam running and,
in another terminal in this folder, run:

```bash
./doom-runner install
# Confirm DOOM's installation in Steam and wait for its download to finish.
./doom-runner play
# Optional windowed mode:
./doom-runner windowed
```

An internet connection is needed for setup, Steam sign-in, and downloading your
owned copy of DOOM (2016). Setup downloads the official Windows Steam and
Microsoft Visual C++ installers; neither those installers nor game files are
included. This package uses the patched MoltenVK backend.

The folder becomes personal after setup: `build/prefixes/doom-upstream/`
contains Steam, credentials, game files, settings, and saves. `.cache/` contains
downloaded installers and receipts. Share only a freshly generated package,
before running setup. Move the folder before setup; moving an initialized Wine
prefix between Macs or directories has not been validated.

`package-manifest.json` records the build dependencies and packaged binary
hashes. `licenses/` contains supplied notices and the pinned Wine/MoltenVK
source archives. Binaries are signed locally with an ad hoc signature; the
package is not Developer ID signed or notarized. Do not disable macOS security
features. Public distribution needs its own signing and notarization process.

To build a new package from the source checkout on the macOS build machine:

```bash
bash independent/scripts/build-all.sh
bash independent/scripts/build-wine.sh --portable
python3 independent/scripts/package-runner.py
python3 independent/scripts/verify-portable.py dist/doom-runner-macos
```

The package appears in `dist/doom-runner-macos/`. The packager refuses to
overwrite an existing output; use `--output dist/another-name` for a new one.
It copies only runtime components, and recursively relocates native libraries.
The portable Wine build is separate from the development runtime. The Python
default is MacPorts Python 3.14; `--python /absolute/path/to/python3` selects
another installed Python whose runtime can be collected.

The verifier copies a fresh package to a temporary path containing spaces and
blocks reads from the source checkout, `/opt/local`, `/opt/homebrew`, and
`/usr/local`. It checks bundled Python and HTTPS, Wine startup, 32/64-bit
Windows APIs, Windows HTTPS, and Vulkan device creation. It needs host GPU and
network access; use `--skip-gpu` in a VM without Metal support. It creates and
removes its own temporary prefix and never launches Steam or DOOM. This is an
isolation smoke test on the build Mac, not a replacement for a separate clean
Mac test of setup and gameplay.

Add `--setup` to the verifier to also download and install Steam, its first
client update, and Visual C++ in that disposable prefix. This can download
hundreds of megabytes. It does not sign in or install DOOM.

## Validation recorded on 24 October 2026

The package passed dependency resolution and ad hoc signature checks for
145 Mach-O files. The development checks passed 84 tests and 22 subtests.
On the M1 Max/macOS 27.0.1 build Mac, the relocated package passed with reads
from the checkout and package-manager directories blocked:

- Bundled Python imports and certificate-verified HTTPS.
- Wine startup and 32-bit/64-bit Windows API probes.
- Windows WinHTTP HTTPS and Vulkan device creation with both DOOM features.
- Fresh Visual C++ and Windows Steam installation, Steam's first client update,
  and Steam UI wrapper installation in a disposable prefix.

The distributed folder remains fresh, without a prefix, installers, credentials,
or game files. Steam sign-in, window presentation, and DOOM gameplay using this
portable package still need testing on a separate clean physical Mac.
