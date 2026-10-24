# Build, install Steam, download DOOM, and play

Run all commands from the repository root on the macOS host. Each user builds
the runner locally, signs in with their own Steam account, and downloads their
own copy of DOOM (2016), app **379720**.

Validated on Apple M1 Max with macOS 27.0.1 on 24 October 2026. Other Mac/OS
combinations have not been validated. This is a source-build workflow with
external native dependencies. To produce a portable runtime for a destination
Mac without those dependencies, follow the [portable packaging guide](docs/PORTABLE.md).

## Prepare the Mac

Install Apple Command Line Tools, Rosetta on Apple Silicon, native CMake 3.21+,
and MacPorts. The [host development guide](docs/DEVELOPMENT.md) describes those
requirements. The native Wine libraries need x86_64 slices, even on Apple Silicon.
With MacPorts installed:

```bash
/usr/bin/python3 independent/scripts/install-host-deps.py
sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install
sudo /opt/local/bin/port install python314
```

The dependency helper prints its plan without `--install`. The detailed
[Wine guide](docs/WINE-BUILD.md) records the dependency set and header repairs
observed on this Mac. Install CMake and the SDK before running the build.

Run the helper **before installing Python or the universal libraries**. It
guards the reviewed MacPorts header-merging code against an observed macOS
toolchain bug that can turn `gmp.h` or libffi headers into binary archives.
If you previously attempted installation and Nettle fails to configure, check:

```bash
/usr/bin/file /opt/local/include/gmp.h
```

If it reports an **ar archive**, use the targeted repair, then retry installing
Python if needed:

```bash
sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install --repair-gmp
```

This rebuilds GMP from source and cleans Nettle's failed work directory before
retrying GnuTLS. It refuses to uninstall GMP if installed packages depend on
it. If `gmp.h` is normal C text, inspect the Nettle `config.log` error before
choosing a repair; missing binary downloads alone do not identify the cause.

## Build the runner

```bash
bash independent/scripts/build-all.sh
```

This prepares native Python development tools, fetches missing pinned Wine and
MoltenVK sources and LLVM-MinGW, then builds the patched graphics library,
Wine 11.20, and the Steam UI wrapper. Existing source trees are retained.

The Vulkan patch is included in the MoltenVK source build. No separate patch
to DOOM's executable is required after downloading the game.

Optional checks:

```bash
bash independent/scripts/check.sh
bash independent/scripts/smoke-wine.sh
```

## Install and launch Windows Steam

```bash
bash independent/scripts/doom-runner.sh setup
bash independent/scripts/doom-runner.sh steam
```

Setup creates `build/prefixes/doom-upstream/`, installs the official x64 Visual
C++ runtime needed by DOOM and the Windows Steam installer, downloads Steam's
first client update, and applies the source-built CEF wrapper. It also upgrades
the installer's old 32-bit updater to Valve's current 64-bit updater, checking
the package SHA-256 against Valve's HTTPS manifest before replacement.

The first update can take several minutes. Setup stops only the selected
prefix while preparing its initial client, before sign-in. Subsequent complete
installations are retained. `steam` also invokes setup automatically if the
client is missing.

Sign in in Steam's window. Credentials are entered directly into Steam.
Installers are downloaded from [Valve](https://store.steampowered.com/about/)
and [Microsoft](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist),
not included in the repository. Mutable installer download receipts record
measured hashes; those receipts are not publisher signature verification.

## Download DOOM through Steam

With Steam open and signed in, use another terminal:

```bash
bash independent/scripts/doom-runner.sh install
```

This opens Steam's DOOM install dialog. Confirm the installation in Steam and
wait for the download to finish. The account must own DOOM (2016); the runner
does not supply game files or bypass Steam ownership checks.

## Play

Keep Windows Steam running and signed in, then run:

```bash
bash independent/scripts/doom-runner.sh play
# Or windowed:
bash independent/scripts/doom-runner.sh windowed
```

The launcher uses `DOOMx64vk.exe` and the project-built patched MoltenVK.
It installs the Visual C++ prerequisite if it is missing. Steam's default Play
entry may select OpenGL, so use this launcher for the tested Vulkan route.

The menu and a short gameplay section were confirmed with this runtime.
Extended stability and performance have not been measured.

## Start over

Quit DOOM and Windows Steam before clearing their installation. Deleting the
entire `build/` directory intentionally removes the Steam prefix, game files,
login state, settings, local saves, compilation outputs, and the graphics library.
Deleting `artifacts/wine-upstream/` also removes the installed runtime.

After backing up any local saves you want to keep, repeat the build, setup,
Steam, install, and play commands above. The commands now create a fresh
installation; no earlier local Steam prefix is required. Installed native host
dependencies and cached source/compiler downloads can be reused.

For an isolated trial, set the same `DOOM_PREFIX` for each runner command to a
new directory under `build/prefixes/`. For example:

```bash
DOOM_PREFIX="$PWD/build/prefixes/new-install" bash independent/scripts/doom-runner.sh setup
DOOM_PREFIX="$PWD/build/prefixes/new-install" bash independent/scripts/doom-runner.sh steam
```

Setup logs are stored inside the selected prefix as `.doom-runner-setup.log`.
To allow a slower initial update, call `setup-game.py --timeout 1200` with the
same `--prefix`. Retrying setup preserves installed files.

Share the project source, rather than your generated `build/`, `artifacts/`,
`.cache/`, or `.venv/` folders. Those can contain personal Steam data and local
binaries. See also the [KosmicKrisp assessment](docs/KOSMICKRISP.md).
