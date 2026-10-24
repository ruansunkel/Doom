# Independent DOOM runner

Build a Wine 11.20 and patched MoltenVK runner on macOS, install Windows Steam,
download DOOM (2016) through your own account, and play.

After installing the [native Mac prerequisites](independent/SETUP.md):

```bash
bash independent/scripts/build-all.sh
bash independent/scripts/doom-runner.sh setup
bash independent/scripts/doom-runner.sh steam
# Sign in in Steam, then use another terminal:
bash independent/scripts/doom-runner.sh install
# Confirm installation in Steam and wait for the download:
bash independent/scripts/doom-runner.sh play
```

The graphics patch is built into MoltenVK automatically. Setup installs Steam,
its first client update, the UI compatibility wrapper, and DOOM's Visual C++
prerequisite. Each user downloads their own game through Steam.

- [First-time setup, launch commands, and starting over](independent/SETUP.md)
- [Native development environment](independent/docs/DEVELOPMENT.md)
- [Wine builds and verification](independent/docs/WINE-BUILD.md)
- [KosmicKrisp SDK tests and current blockers](independent/docs/KOSMICKRISP.md)

Steam sign-in, the menu, and a short gameplay section were confirmed on M1 Max
with macOS 27.0.1. Other hardware/OS combinations remain unvalidated.

To build a portable folder for a Mac without development tools or MacPorts,
finish the build above, then run on the macOS build machine:

```bash
bash independent/scripts/build-wine.sh --portable
python3 independent/scripts/package-runner.py
python3 independent/scripts/verify-portable.py dist/doom-runner-macos
```

Copy the complete `dist/doom-runner-macos/` folder to a writable location on the
destination Mac. Run `./doom-runner setup`, `./doom-runner steam`,
`./doom-runner install`, and `./doom-runner play` there. Python, native runtime
libraries, and patched MoltenVK are bundled; Rosetta is required on Apple
Silicon. This build requires macOS 27 or newer.
[Portable setup, build details, and validation limits](independent/docs/PORTABLE.md).
Generate a fresh package for sharing; a folder used for Steam setup contains
personal account data. Packages are locally signed, without notarization.

Source lives under `independent/`. Run commands from the repository root in a
local macOS terminal. Generated files stay at `build/`, `artifacts/`,
`third_party/`, and `.cache/` to preserve embedded native paths. VS Code's
**Host: ...** tasks provide the same build and setup commands.

Share the source checkout without generated folders or personal Steam data.
