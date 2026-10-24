#!/usr/bin/env bash
# Native capability check; no Wine prefix or global driver changes.
set -euo pipefail
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this probe on the macOS host.' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
architecture="${VULKAN_PROBE_ARCH:-x86_64}"
case "$architecture" in
  x86_64|arm64) ;;
  *) echo 'VULKAN_PROBE_ARCH must be x86_64 or arm64.' >&2; exit 2 ;;
esac
library="$project_root/build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib"
if [[ "$#" -gt 1 ]]; then
  echo 'Usage: bash independent/scripts/probe-vulkan.sh [/absolute/path/to/Vulkan/library]' >&2
  exit 2
fi
if [[ "$#" == 1 ]]; then library="$1"; fi
if [[ "$library" != /* || ! -f "$library" ]]; then
  echo 'Provide an existing Vulkan library by absolute path.' >&2
  exit 2
fi
headers="$project_root/build/moltenvk-doom2016/_deps/vulkan-headers-src/include"
if [[ ! -f "$headers/vulkan/vulkan.h" ]]; then
  cache="$project_root/build/moltenvk-doom2016/CMakeCache.txt"
  if [[ -f "$cache" ]]; then
    header_source="$(sed -n 's/^VULKAN_HEADERS_SOURCE_DIR:STATIC=//p' "$cache")"
    if [[ -n "$header_source" ]]; then headers="$header_source/include"; fi
  fi
fi
if [[ ! -f "$headers/vulkan/vulkan.h" ]]; then
  echo 'Build MoltenVK first to obtain the pinned Vulkan headers.' >&2
  exit 1
fi
output_dir="$project_root/build/smoke-upstream"
if [[ -L "$output_dir" ]]; then
  echo 'The smoke output directory must not be a symlink.' >&2
  exit 1
fi
mkdir -p "$output_dir"
# Default matches Wine under Rosetta; arm64 diagnoses native-only drivers.
xcrun --sdk macosx clang -arch "$architecture" -std=c11 -O2 -Wall -Wextra -Werror \
  -I "$headers" "$project_root/independent/tests/host/wine-vulkan.c" \
  -o "$output_dir/vulkan-native-$architecture"
file "$output_dir/vulkan-native-$architecture" "$library"
exec "$output_dir/vulkan-native-$architecture" "$library"
