#!/usr/bin/env bash
# Build every current runtime component on the macOS host.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Build the runner on the macOS host.' >&2
  exit 2
fi
if [[ "$#" != 0 ]]; then
  echo 'Usage: bash independent/scripts/build-all.sh' >&2
  exit 2
fi
python3 "$project_root/independent/scripts/setup-host-dev.py"
bash "$project_root/independent/scripts/host-doctor.sh"
# Acquire missing pinned inputs on a fresh checkout; retain existing trees.
if [[ ! -x "$project_root/.cache/host-tools/llvm-mingw-20261020-ucrt-macos-universal/bin/x86_64-w64-mingw32-clang" ]]; then
  python3 "$project_root/independent/scripts/host-tools.py"
fi
if [[ ! -f "$project_root/third_party/MoltenVK-DOOM2016-628683c1822614acf97b185f66817a875ba094a4/CMakeLists.txt" ]]; then
  python3 "$project_root/independent/scripts/moltenvk-source.py"
fi
if [[ ! -f "$project_root/third_party/wine-11.20/configure" ]]; then
  python3 "$project_root/independent/scripts/upstream-wine-source.py"
fi
bash "$project_root/independent/scripts/build-moltenvk.sh"
bash "$project_root/independent/scripts/build-wine.sh"
bash "$project_root/independent/scripts/build-steam-wrapper.sh"
printf 'All runtime components built on macOS.\n'
