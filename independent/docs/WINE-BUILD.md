# Independent Wine runtime: source and host prerequisites

Run commands in this guide from the repository root. Scripts, tests, and tools
live under `independent/`; generated builds, runtime artifacts, source archives,
and prefixes retain their root paths so the working native installation remains
usable after the folder separation.

The patched MoltenVK library has compiled on the Mac host. The resulting
library contains x86_64 and arm64 slices. The source-built x86_64 macOS Wine
runtime has also completed. Upstream `wine-11.20` passes Windows API, Vulkan
device-creation, and WinHTTP HTTPS probes. The game launcher uses that runtime: it
connects to Steam's servers, loads the login QR code, and has completed sign-in
through Library-ready/Success. After installing its Visual C++ prerequisite,
the user confirmed DOOM's menu and a short gameplay section on 24 October 2026.

## Source baseline

The runtime uses WineHQ's upstream Wine **11.20**, released on 16 October 2026.
The [official release announcement](https://list.winehq.org/hyperkitty/list/wine-announce%40list.winehq.org/thread/BXK6IO4YFZW4O5CABDN5SOOFY3ZYTJP3/)
and [source archive](https://dl.winehq.org/wine/source/11.x/wine-11.20.tar.xz)
identify the pinned release. Its measured SHA-256 is:

```text
eac8ca448f9c0087f963026b4dc276d1e2b7fbb64056edc093e59bbb7e56fe28
```

This is a recorded checksum, not verification of the publisher's OpenPGP
signature. Fetch and extract the source from a fresh checkout:

```bash
python3 independent/scripts/upstream-wine-source.py
```

Sources go into `third_party/wine-11.20/`; the archive is cached beside them.
On this Mac extraction has already completed: use `--verify-only` to check
the cached archive without replacing the source tree. The fetcher verifies
the digest and rejects unsafe archive entries and existing destinations.

## Check the Mac before building

Run in a macOS Terminal from this repository:

```bash
bash independent/scripts/wine-host-doctor.sh
```

The doctor checks tools and compiles disposable probes. It does not install
dependencies, build Wine, or create a Wine prefix. A nonzero
exit means prerequisites are missing; use the reported results to determine
the host setup rather than installing a speculative dependency list.

It checks:

- Apple Clang, the macOS SDK, x86_64 compilation, and Rosetta execution.
- Make, pkg-config, Bison >= 3.0, and Flex >= 2.5.33.
- Working i686 and x86_64 MinGW GCC or llvm-mingw Clang PE linkers.
- FreeType and GnuTLS headers/libraries that link as **x86_64**.
- Both architectures in the source-built patched MoltenVK library.

Apple Silicon package managers may provide arm64-only libraries. Their presence
alone does not satisfy an x86_64 Wine runtime; the link probes check this.
The supplied Wine `configure` script is already generated, so autoconf,
automake, and libtoolize are not prerequisites for this initial route.

## Native host tools

MacPorts **2.12.7** is now installed at `/opt/local`. Its official macOS 27
installer was checked with `pkgutil` and Gatekeeper: Apple trusted its developer
signature and notarization before it was installed. The installer may add its
normal PATH settings to the host shell profile.

The native dependencies use MacPorts. The reviewed helper installs the fixed
package set and restores normal signal handling before launching MacPorts:

```bash
python3 independent/scripts/install-host-deps.py
sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install
```

On a fresh Mac, run this helper before `sudo port install python314` as well.
Its normal `--install` path now protects both reviewed muniversal 1.0 and 1.1
header-merging implementations before installing dependencies. It validates
both source patterns before editing and retains original backups. Unknown
upstream implementations require review; the helper refuses guessed edits.

Without `--install` it only prints the plan. It installs `pkgconfig`, `bison`,
`freetype +universal`, and `gnutls +universal`. If launched through macOS
Authorization Services, the administrator shell can pass blocked SIGALRM and
SIGTERM to its children. This caused GNU timer configure probes to hang during
the first attempt. The helper clears that inherited mask and resets the signal
handlers before starting the package manager; an isolated alarm regression test
checks that behavior. The stalled attempt was stopped and resumed; its installed
dependencies were retained.

The universal libraries include x86_64 slices for Wine's Unix side. Their
supporting dependencies may build from source; allow installation to finish.
Project installation diagnostics are cached in `.cache/host-tools/` and
MacPorts keeps its own logs under `/opt/local/var/macports/logs`.

The host dependency installation completed, including universal GnuTLS 3.8.13.
The final MacPorts scan reported no broken files or ports, and both FreeType
and GnuTLS passed the doctor's x86_64 link probes.

On this macOS 27 toolchain, Apple's `libtool` accepts different C headers as
archive inputs and returns success. MacPorts' `muniversal` merge fallback then
installed a 96-byte archive as `gmp.h`, causing Nettle's `GMP_NUMB_BITS` check
to fail. The targeted repair keeps `*.h` inputs out of both binary merge tools
and uses the existing text merge. It saves `muniversal-1.1.tcl.doom-runner-original`
beside the original PortGroup. A Tcl regression test verifies the short-circuit
behavior; archive/library inputs retain their normal merge path.

If Nettle fails during configure, the summary and attempted package downloads
do not establish the cause. Inspect its reported `config.log`, and check:

```bash
/usr/bin/file /opt/local/include/gmp.h
```

For the observed damaged-header case (an **ar archive**, rather than C text):

```bash
python3 independent/scripts/install-host-deps.py --repair-gmp
sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install --repair-gmp
```

The repair removes the damaged GMP image without force (MacPorts refuses if
there are installed dependents), cleans GMP, reinstalls it from source using the
corrected merge, cleans Nettle's failed work directory, and resumes dependency
installation. The normal installer detects existing archived headers and points
to an explicit repair rather than uninstalling packages automatically. MacPorts
failures now print the failed command and diagnostic guidance without a Python
traceback. A forced same-version upgrade reused
the bad image on this host, so the repair uses a clean reinstall. MacPorts source
updates can replace the local PortGroup workaround; the helper refuses unknown
source patterns rather than modifying them blindly.

The same issue was found in the older `muniversal-1.0.tcl` used by libffi:
`ffi.h` and `ffitarget.h` were archives, which broke Python's ctypes build.
The corresponding targeted repair is:

```bash
sudo /usr/bin/python3 independent/scripts/install-host-deps.py --install --repair-libffi
```

This preserves a separate PortGroup 1.0 backup, reinstalls libffi without force,
and cleans only the failed Python 3.14 build directory so its configure checks
run again with valid headers. A recursive scan of installed headers identified
these libffi files as the remaining damaged headers after GMP was repaired.

Windows PE compilation uses the official **LLVM-MinGW 20261020** macOS universal
toolchain (LLVM 23.1.4), avoiding a GCC/compiler bootstrap. The release asset is
`llvm-mingw-20261020-ucrt-macos-universal.tar.xz`; its SHA-256, published in
the GitHub release asset manifest, is:

```text
e9c13e4ede38e715003ffc674d4d00a1088df8235439d1f0c16188ff0704c17e
```

On a fresh checkout, fetch and extract that compiler into the project cache:

```bash
python3 independent/scripts/host-tools.py
```

It refuses an existing extracted toolchain. On this Mac it is already installed,
so use `python3 independent/scripts/host-tools.py --verify-only` to verify the cached archive
without changing the current tools. The fetcher verifies the digest, rejects
unsafe archive paths and links, and does not execute downloaded programs.

`independent/scripts/host-env.sh` selects the cached compiler, MacPorts tools and pkg-config
metadata, and `CMake.app`. The build and Wine doctor load these overrides in
their own process. You can source that file in a host Bash or zsh shell when
using the tools manually.

The host probes have already linked both 32-bit and 64-bit Windows executables
with the new toolchain. The full doctor also checks the native library linkage:

```bash
bash independent/scripts/wine-host-doctor.sh
```

## What the source audit establishes

These are observations from this archive's `configure.ac`, generated
`configure`, and native driver makefiles:

- `--enable-archs=i386,x86_64` selects the two PE architectures for modern
  WoW64. Both cross-compilers must pass Wine's capability checks.
- The Unix side must compile as x86_64 on this Apple Silicon Mac. Set the
  compiler architecture explicitly; changing only the configure triplet does
  not prove that the compiler emits x86_64 binaries.
- The macOS graphics and CoreAudio backends use Apple frameworks. The native
  macOS driver is the intended route, with X11/Wayland disabled.
- FreeType provides fonts and GnuTLS provides encryption support. These need
  matching native architectures and eventual runtime packaging.
- Vulkan discovery tries `libvulkan` before `libMoltenVK`. Integration must
  select our patched library explicitly and verify the actual loaded path.
  An unrelated installed Vulkan loader must not silently select a different
  MoltenVK build.

The [maintained macOS Wine packaging recipe](https://github.com/Gcenx/macOS_Wine_builds)
also uses an x86_64 Unix runtime with `--enable-archs=i386,x86_64` and llvm-mingw.
Its broader dependency list is a reference; our native build and smoke probes
verify the narrower configuration below.

## Build and test commands

After the dependency installation and doctor pass:

```bash
bash independent/scripts/build-wine.sh
bash independent/scripts/smoke-wine.sh
```

The build helper explicitly uses Apple Clang with `-arch x86_64` for the native
side and LLVM-MinGW for both PE architectures. It configures modern WoW64 with
`--enable-archs=i386,x86_64`, native macOS graphics/audio, FreeType, GnuTLS, and
Vulkan. CUPS, X11/Wayland and optional media backends are disabled. Add media
backends only if application testing demonstrates a need.

Build products go in `build/wine-upstream-x86_64/`, and `make install` targets
`artifacts/wine-upstream/`. `--configure-only` stops before compilation.
The configuration pins the absolute source-built MoltenVK path in
`SONAME_LIBVULKAN`; changing that location requires rebuilding the runtime.

For distribution, `bash independent/scripts/build-wine.sh --portable` builds
separately into `build/wine-portable-x86_64/` and `artifacts/wine-portable/`.
Its Vulkan path is `@loader_path/../../../native/libMoltenVK.dylib`, resolved
relative to Wine's native bridge. `package-runner.py` copies that runtime,
bundles Python and native library dependencies, relocates Mach-O load commands,
and signs the resulting files locally. See [portable packaging](PORTABLE.md).

The smoke helper compiles small Windows test executables and, on a full run,
initializes only `build/prefixes/upstream-smoke`. It checks 32-bit/64-bit Windows
APIs, creates a Vulkan device enabling `depthBounds` and `shaderCullDistance`,
and makes a WinHTTP HTTPS HEAD request for Steam's public installer metadata.
It does not sign in, download the installer body, or launch a game. Logs go in
`build/smoke-upstream/`. `--compile-only` builds the probes without starting Wine.

The same Vulkan probe can run natively under Rosetta before Wine is available:

```bash
bash independent/scripts/probe-vulkan.sh
```

This passed on the M1 Max with the source-built MoltenVK: `depthBounds=1`,
`shaderCullDistance=1`, and successful graphics-device creation with both
features enabled. The output is recorded in `build/vulkan-native.log`. It does
not test presentation or gameplay. An optional absolute library path selects
a different Vulkan library for an isolated capability check.

For individual experiments:

```bash
bash independent/scripts/run-wine.sh --print-config
bash independent/scripts/run-wine.sh -- path/to/program.exe
bash independent/scripts/run-wine.sh --trace-libraries -- path/to/program.exe
```

This helper binds the runtime and wineserver to `artifacts/wine-upstream`,
clears inherited loader/library overrides, and restricts prefixes to the
workspace's `build/prefixes/` directory, including resolved symlink targets.
The graphics library is selected by Wine's compiled `SONAME_LIBVULKAN` path.

`--trace-libraries` enables dyld's native library-path diagnostics immediately
before starting Wine. The Vulkan smoke invocation records those paths so the
actual runtime and graphics library can be checked.

FreeType/GnuTLS currently remain external dependencies under `/opt/local/lib`;
the runner sets only that known fallback library directory. The installed
artifact is a development runtime, not yet a self-contained redistributable app.

For the optional future KosmicKrisp path and the M1 Max depth-bounds limitation,
see [the backend assessment](KOSMICKRISP.md).

## Validated runtime baseline

Validated on this M1 Max on 24 October 2026:

- The native Wine build installed into `artifacts/wine-upstream/` and reports
  `wine-11.20`. Its loader and wineserver are x86_64 Mach-O executables.
- Both i386 and x86_64 Windows API probes passed, including clock checks.
- The Windows Vulkan probe created a graphics device with `depthBounds=1`
  and `shaderCullDistance=1` enabled.
- The Windows WinHTTP HEAD probe returned HTTP 200 from Steam's public installer
  endpoint without downloading its body.
- The Vulkan dyld trace contains the project-built Wine and MoltenVK libraries.

Smoke outputs are in `build/smoke-upstream/`; the latest cleanup verification
log is `build/wine-upstream-cleanup-smoke.log`. These probes test API calls and
device creation; gameplay was checked separately below.

## Gameplay acceptance and remaining work

Windows Steam sign-in, DOOM's menu, and a short gameplay section are confirmed
on the M1 Max with upstream Wine 11.20 and the source-built patched MoltenVK.
The running game's library paths confirm the project-built Wine and MoltenVK.
This is a functional gameplay check; extended stability and performance have
not been measured. Standalone packaging and a macOS application launcher remain.

## Independent Steam/DOOM test prefix

For a fresh checkout or after removing the entire build directory, follow
[the first-time setup guide](../SETUP.md). `doom-runner.sh setup` now creates
the prefix, installs the application prerequisites and Steam, upgrades the
initial updater to x64, downloads the client, and applies the UI wrapper.
`doom-runner.sh install` opens Steam's DOOM installation dialog after sign-in.

Windows Steam and DOOM are installed in `build/prefixes/doom-upstream/`.
The user signed in through Steam's own window; its startup log reached
Library-ready/Success. The retired runtime's test prefixes have been removed.

DOOM's game directory and app manifest were copied into this prefix using
APFS clones. The cloned executable has a different inode from the original;
its storage blocks are initially shared through copy-on-write. Steam can reuse
these installed game files after sign-in. The new prefix's Documents,
Downloads, and media folders are local directories.

Experimental commands on the **Mac host**:

```bash
bash independent/scripts/doom-runner.sh config
bash independent/scripts/doom-runner.sh steam
# After Steam is signed in through this independent runner:
bash independent/scripts/doom-runner.sh windowed
# Or fullscreen:
bash independent/scripts/doom-runner.sh play
```

Steam's CEF 126 UI was black but interactive. Changing the Direct3D renderer,
CEF sandbox, compositing flags, and MSync did not resolve it. Basic 32-bit and
64-bit Wine windows rendered normally. A temporary DXVK test also presented a
bright green Direct3D window, which the user confirmed; its DLL changes were
then restored before the final Steam setup.

The working UI fix is a source-built `steamwebhelper.exe` wrapper which passes
`--disable-gpu --disable-gpu-compositing --single-process` directly to Valve's
preserved `steamwebhelper_real.exe`. This approach is documented by the
[steam-on-m1-wine project](https://github.com/notpop/steam-on-m1-wine/blob/main/docs/troubleshooting.md).
Our wrapper forwards Unicode paths, quoted arguments, environment, and child
exit status; it does not log command lines. A synthetic Windows child verified
those forwarding behaviors before installation. The installer preserves and
checksums Valve's original, supports `--restore`, and recognizes client updates.

`doom-runner.sh steam` builds the wrapper if absent, installs it idempotently,
sets Steam's working directory, and uses `-noverifyfiles -cef-disable-gpu
-no-cef-sandbox`. Steam updates can restore Valve's helper; relaunch through
this script to reapply the wrapper. For normal verification with the original
helper, quit independent Steam and run
`python3 independent/scripts/install-steam-wrapper.py --restore` first. No persistent
Steam update-inhibition configuration was added.

The user confirmed that the sign-in UI renders with the wrapper. Wine 11.20
retrieved the CM list, established a server connection, and displayed the login
QR code before sign-in completed.

### DOOM application prerequisites

The first independent game launch created a Vulkan device and swapchain, but
the user saw a black window. Wine reported that `CChromaEditorLibrary.dll`
could not load because `mfc140u.dll` was absent. A crash report was also
written during that launch.

Microsoft's official x64 Visual C++ v14 Redistributable was installed only in
`doom-upstream`, returning success and supplying `mfc140u.dll`. Installing the
runtime is an application prerequisite, separate from building Wine. Directly
launching the game executable does not run Steam's first-launch installers.
For a fresh independent prefix, use the current x64 download linked by
[Microsoft's supported runtime page](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist):

```bash
curl --fail --location --proto '=https' --tlsv1.2 \
  https://aka.ms/vc14/vc_redist.x64.exe -o .cache/host-tools/vc_redist.x64.exe
bash independent/scripts/run-wine.sh \
  --prefix build/prefixes/doom-upstream -- \
  "$PWD/.cache/host-tools/vc_redist.x64.exe" \
  /install /quiet /norestart /log 'C:\vc-redist-install.log'
```

The tested download on 2026-10-24 was version `14.51.36247.0`, measured SHA-256
`843068991daaa1f73ad9f6239bce4d0f6a07a51f18c37ea2a867e9beca71295c`.
This is a recorded checksum; the permalink can deliver newer versions.
After restarting, the user confirmed that DOOM reaches the menu and gameplay
works. The earlier crash report was not rewritten during the startup recheck.
The launcher checks for the required MFC DLL before launching the game.

DOOM is explicitly launched with `DOOMx64vk.exe`, `+r_renderAPI 1`, and
`+com_skipIntroVideo 1`. The Steam UI workaround does not change its renderer.

The launcher uses the independent runtime, graphics library, and prefix through
`run-wine.sh`. It remains a development helper with external MacPorts libraries,
not a standalone macOS application. Steam startup diagnostics are in
`build/steam-upstream-clean-launch.log`.
The gameplay-confirmed game's open-file inspection is recorded in
`build/doom-independent-loaded-libraries.json`: it loaded Wine libraries from
`artifacts/wine-upstream` and MoltenVK from `build/moltenvk-doom2016`.
Its restart log is `build/doom-upstream-vcredist-launch.log`.

## Steam startup

Steam's silent Run-key autostart was disabled in the game prefix so Wine startup
cannot launch a competing client before the wrapper is applied. The original
startup entry is backed up in `build/upstream-steam-autostart-backup.reg`.
