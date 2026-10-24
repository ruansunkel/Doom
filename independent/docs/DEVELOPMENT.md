# Developing the DOOM runner on macOS

All current builds and checks run directly on the Mac host. Open this repository
in a local VS Code window and use its integrated terminal. Run commands from
the repository root.

The source-built runner has passed Steam sign-in, the menu, and a short gameplay
check on the M1 Max. See [the setup guide](../SETUP.md) for game commands.

## Set up native development tools

```bash
python3 independent/scripts/setup-host-dev.py
```

The setup helper creates a native macOS `.venv`, installs the exact pytest and
Ruff versions in `requirements-dev.txt`, and prepares ShellCheck 0.11.0 under
`.cache/host-tools/`. Downloads use pinned publisher SHA-256 values for the
macOS arm64 and x86_64 ShellCheck packages. The installer preserves the license
and rejects unexpected archive entries and symlink destinations.

It uses native Python 3.10 or newer; this Mac has MacPorts Python 3.14 at
`/opt/local/bin/python3.14`. Use `--python /absolute/path/to/python3` to choose
another interpreter when creating the environment. An existing environment
from another operating system must be renamed first. The old generated
Python environment on this Mac was preserved in
`.cache/host-tools/previous-linux-venv/` and is no longer used.

VS Code's workspace settings select `.venv/bin/python`, Apple's native clangd,
and the cached native ShellCheck. If VS Code remembers an older Python
selection, use **Python: Select Interpreter** and select `.venv/bin/python`.
Recommended extensions cover C/C++, Python, Ruff, Bash, and ShellCheck.

## Check and build

```bash
bash independent/scripts/check.sh
bash independent/scripts/host-doctor.sh
bash independent/scripts/wine-host-doctor.sh
bash independent/scripts/build-all.sh
bash independent/scripts/smoke-wine.sh
```

`check.sh` runs shell syntax checks, ShellCheck, Ruff, Python syntax checks, and
the test suite using the native `.venv`. The two doctors check the native SDK,
Rosetta, CMake, PE cross-compilers, and matching x86_64 Wine dependencies.

`build-all.sh` builds MoltenVK, Wine, and the Steam UI wrapper in that order.
The Windows wrapper and probes are cross-compiled on macOS with LLVM-MinGW;
the build tools themselves run natively on the host. MoltenVK uses Apple's
C/C++ compiler shims explicitly so the PE toolchain cannot replace them.

The smoke command uses the separate `build/prefixes/upstream-smoke/` prefix.
It checks 32/64-bit Windows APIs, Vulkan device creation, and WinHTTP HTTPS.
The game installation remains in `build/prefixes/doom-upstream/`.

VS Code's **Run Task** menu provides the same commands as `Host: ...` tasks.
**Run Build Task** runs **Host: Build all**. Individual build tasks are also
available:

```bash
bash independent/scripts/build-moltenvk.sh
bash independent/scripts/build-wine.sh
bash independent/scripts/build-steam-wrapper.sh
```

## Native build prerequisites

The current Mac already has the required SDK, Rosetta, CMake, MacPorts native
libraries, and LLVM-MinGW toolchain. A fresh Mac needs:

| Component | Native tools |
| --- | --- |
| C/C++ and macOS frameworks | Apple Command Line Tools, Apple Clang, macOS SDK, Make |
| Graphics build | Native CMake 3.21+, Apple Metal frameworks |
| Wine Unix runtime | x86_64 Apple Clang output, Rosetta on Apple Silicon |
| Windows PE binaries | Pinned LLVM-MinGW 20261020, i686 and x86_64 targets |
| Fonts, TLS, parser generation | MacPorts FreeType/GnuTLS universal libraries, pkg-config, Bison, Flex |
| Development checks | Native Python 3.10+, pinned pytest/Ruff, ShellCheck |

Use `xcode-select --install` if Command Line Tools are missing. Native CMake is
available from [Kitware](https://cmake.org/download/); the helpers discover
`/Applications/CMake.app/Contents/bin/cmake`. Full Xcode is optional for the
current pinned MoltenVK route. A future target that compiles Metal shaders or
builds a SwiftUI app may require it.

The [Wine guide](WINE-BUILD.md) records dependency installation, the MacPorts
header repairs needed on this Mac, toolchain pins, and source checksums. The
host dependency installer prints its plan by default and requires its explicit
`--install` mode for system package changes.

## Sources and output paths

`build-all.sh` prepares the native development environment and acquires missing
pinned sources and the PE compiler automatically. To acquire those inputs
individually:

```bash
python3 independent/scripts/host-tools.py
python3 independent/scripts/moltenvk-source.py
python3 independent/scripts/upstream-wine-source.py
```

These are already present on this Mac. The fetchers refuse replacement of
existing source/tool trees. Use `--verify-only` to verify cached archives;
MoltenVK's fetcher also accepts `--archive PATH`.

The source baseline is Wine 11.20 and the DOOM-specific MoltenVK fork at commit
`628683c1822614acf97b185f66817a875ba094a4`. The graphics build produces x86_64
and arm64 slices. CMake may download dependencies during configuration; this
is not a fully offline build pipeline.

Scripts, tools, tests, and docs live under `independent/`. Generated data stays
at the repository root to preserve existing embedded native paths:

- `build/`: compilation outputs, smoke tests, logs, and game prefixes.
- `artifacts/`: installed Wine runtime.
- `third_party/`: pinned source archives and extracted source trees.
- `.cache/host-tools/`: cached native compilers and development tools.
- `.venv/`: native Python environment used by VS Code and `check.sh`.

The runner still uses external native FreeType/GnuTLS libraries under
`/opt/local/lib`; standalone application packaging remains.

The complete host workflow was validated on 24 October 2026: all three runtime
components built, 80 tests plus 22 subtests passed, and the rebuilt Wine runtime
passed the Windows API, Vulkan, and HTTPS probes. The build log is
`build/host-build-all.log`; runtime verification is in `build/host-build-smoke.log`.

## Fresh Steam installation

The [first-time setup guide](../SETUP.md) covers rebuilding with no previous
Steam prefix. `doom-runner.sh setup` installs official application prerequisites
and updates the initial Steam client. `steam` opens sign-in, `install` requests
DOOM's Steam installation dialog, and `play` selects Vulkan with the patched
source-built graphics library. A separate `DOOM_PREFIX` inside `build/prefixes/`
can be used to test a fresh installation without resetting the game prefix.

The fresh setup was also exercised from an empty test prefix: Visual C++ and
Steam installed, the obsolete 32-bit updater was upgraded using Valve's
hash-verified x64 package, the initial client update completed, and the CEF
wrapper was applied. A repeated setup skipped the initial client bootstrap.
The resulting client libraries match the gameplay-tested installation.
Logs are in `build/fresh-install-setup.log` and `build/fresh-install-repeat.log`;
the validation summary is `build/fresh-install-validation.json`. Signing in
and downloading DOOM remain interactive steps in Steam.
