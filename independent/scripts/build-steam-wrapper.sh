#!/usr/bin/env bash
# Cross-compile the Windows wrapper on the macOS host.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Build the Steam wrapper on the macOS host.' >&2
  exit 2
fi
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
compiler="$doom_pe_toolchain/bin/x86_64-w64-mingw32-clang"
output_dir="$project_root/build/steam-ui"
[[ ! -L "$output_dir" ]] || { echo 'Wrapper output must not be a symlink.' >&2; exit 1; }
mkdir -p "$output_dir"
"$compiler" -std=c11 -O2 -Wall -Wextra -Werror -static -municode -mwindows \
  "$project_root/independent/tools/steamwebhelper-wrapper.c" -o "$output_dir/steamwebhelper.exe"
file "$output_dir/steamwebhelper.exe"
shasum -a 256 "$output_dir/steamwebhelper.exe"
