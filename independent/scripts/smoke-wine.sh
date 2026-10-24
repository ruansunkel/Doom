#!/usr/bin/env bash
# Build and optionally run probes only in the independent Wine test prefix.
set -euo pipefail

usage() {
  echo 'Usage: bash independent/scripts/smoke-wine.sh [--compile-only]'
  echo 'Builds 32/64-bit Windows API probes and 64-bit Vulkan/HTTPS probes.'
  echo 'The default also initializes build/prefixes/upstream-smoke and runs the probes.'
}
compile_only=0
case "${1:-}" in
  --compile-only) compile_only=1 ;;
  --help|-h) usage; exit 0 ;;
  '') ;;
  *) usage >&2; exit 2 ;;
esac
if [[ "$#" -gt 1 ]]; then usage >&2; exit 2; fi
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run on the macOS host.' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
output_dir="$project_root/build/smoke-upstream"
prefix="$project_root/build/prefixes/upstream-smoke"
compiler32="$doom_pe_toolchain/bin/i686-w64-mingw32-clang"
compiler64="$doom_pe_toolchain/bin/x86_64-w64-mingw32-clang"
headers="$project_root/build/moltenvk-doom2016/_deps/vulkan-headers-src/include"
if [[ ! -f "$headers/vulkan/vulkan.h" ]]; then
  # CPM may keep the exact dependency outside _deps in its shared source cache.
  cache="$project_root/build/moltenvk-doom2016/CMakeCache.txt"
  if [[ -f "$cache" ]]; then
    header_source="$(sed -n 's/^VULKAN_HEADERS_SOURCE_DIR:STATIC=//p' "$cache")"
    if [[ -n "$header_source" ]]; then headers="$header_source/include"; fi
  fi
fi
if [[ ! -x "$compiler32" || ! -x "$compiler64" ]]; then
  echo 'The pinned llvm-mingw host toolchain is missing; check independent/scripts/host-env.sh.' >&2
  exit 1
fi
if [[ ! -f "$headers/vulkan/vulkan.h" ]]; then
  echo 'Vulkan headers from the MoltenVK build are missing; build MoltenVK first.' >&2
  exit 1
fi
if [[ -L "$output_dir" ]]; then
  echo 'The smoke output directory must not be a symlink.' >&2
  exit 1
fi
mkdir -p -- "$output_dir"
run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}
printf 'Compiler toolchain: %s\nVulkan headers: %s\n' "$doom_pe_toolchain" "$headers"
run "$compiler64" --version
run "$compiler32" -std=c11 -O2 -Wall -Wextra -Werror \
  "$project_root/independent/tests/host/wine-basic.c" -o "$output_dir/wine-basic-i386.exe"
run "$compiler64" -std=c11 -O2 -Wall -Wextra -Werror \
  "$project_root/independent/tests/host/wine-basic.c" -o "$output_dir/wine-basic-x86_64.exe"
run "$compiler64" -std=c11 -O2 -Wall -Wextra -Werror -I "$headers" \
  "$project_root/independent/tests/host/wine-vulkan.c" -o "$output_dir/wine-vulkan-x86_64.exe"
run "$compiler64" -std=c11 -O2 -Wall -Wextra -Werror \
  "$project_root/independent/tests/host/wine-https.c" -lwinhttp -o "$output_dir/wine-https-x86_64.exe"
executables=(wine-basic-i386.exe wine-basic-x86_64.exe wine-vulkan-x86_64.exe wine-https-x86_64.exe)
for executable in "${executables[@]}"; do
  run file "$output_dir/$executable"
  run shasum -a 256 "$output_dir/$executable"
done
if [[ "$compile_only" == 1 ]]; then
  echo 'Compile-only checks passed. No Wine process or test prefix was started.'
  exit 0
fi

runner="$project_root/independent/scripts/run-wine.sh"
run bash "$runner" --prefix "$prefix" --print-config | tee "$output_dir/runtime-config.log"
run bash "$runner" --prefix "$prefix" -- --version | tee "$output_dir/wine-version.log"
# Scoped to these test invocations; no persistent registry or bottle edits.
run env WINEDLLOVERRIDES='winemenubuilder.exe=d;mscoree,mshtml=' \
  bash "$runner" --prefix "$prefix" -- wineboot --init 2>&1 | tee "$output_dir/wineboot.log"
for executable in "${executables[@]}"; do
  if [[ "$executable" == wine-vulkan-x86_64.exe ]]; then
    run env WINEDLLOVERRIDES='winemenubuilder.exe=d;mscoree,mshtml=' \
      bash "$runner" --prefix "$prefix" --trace-libraries -- "$output_dir/$executable" \
      2>&1 | tee "$output_dir/$executable.log"
  else
    run env WINEDLLOVERRIDES='winemenubuilder.exe=d;mscoree,mshtml=' \
      bash "$runner" --prefix "$prefix" -- "$output_dir/$executable" \
      2>&1 | tee "$output_dir/$executable.log"
  fi
done
echo 'Smoke probes passed: Windows API basics, Vulkan device creation, and WinHTTP HTTPS.'
printf 'Logs are in %s. Steam, DOOM presentation, and gameplay remain untested by these probes.\n' "$output_dir"
