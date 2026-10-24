#!/usr/bin/env bash
# Build only into this repository; do not patch installed applications.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Build MoltenVK on the macOS host.' >&2
  exit 2
fi
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
bash "$project_root/independent/scripts/host-doctor.sh"
cmake_command="$(command -v cmake || true)"
if [[ -z "$cmake_command" && -x /Applications/CMake.app/Contents/bin/cmake ]]; then
  cmake_command=/Applications/CMake.app/Contents/bin/cmake
fi
source_dir="$project_root/third_party/MoltenVK-DOOM2016-628683c1822614acf97b185f66817a875ba094a4"
build_dir="$project_root/build/moltenvk-doom2016"
if [[ ! -f "$source_dir/CMakeLists.txt" ]]; then
  echo 'First run: python3 independent/scripts/moltenvk-source.py' >&2
  exit 1
fi
"$cmake_command" -S "$source_dir" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=/usr/bin/cc \
  -DCMAKE_CXX_COMPILER=/usr/bin/c++ \
  '-DCMAKE_OSX_ARCHITECTURES=x86_64;arm64'
"$cmake_command" --build "$build_dir" --parallel "$(sysctl -n hw.ncpu)"
library="$build_dir/MoltenVK/libMoltenVK.dylib"
# Keep one architecture per invocation for compatibility with Xcode 27 lipo.
lipo "$library" -verify_arch x86_64
lipo "$library" -verify_arch arm64
printf 'Built universal library: %s\n' "$library"
shasum -a 256 "$library"
