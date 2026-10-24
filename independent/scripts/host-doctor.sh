#!/usr/bin/env bash
# Read-only check of the native macOS build/test prerequisites.
set -euo pipefail

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this script in a macOS host Terminal.' >&2
  exit 2
fi

missing=0
check_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    printf 'OK: %s\n' "$1"
  else
    printf 'MISSING: %s\n' "$1"
    missing=1
  fi
}

printf 'Native macOS prerequisites for the pinned MoltenVK CMake build:\n'
check_tool git
check_tool xcrun
if xcrun --find clang >/dev/null 2>&1 && xcrun --sdk macosx --show-sdk-path >/dev/null 2>&1; then
  printf 'OK: Apple Clang and macOS SDK\n'
else
  printf 'MISSING: Apple Command Line Tools/macOS SDK (install with xcode-select --install)\n'
  missing=1
fi
cmake_command="$(command -v cmake || true)"
if [[ -z "$cmake_command" && -x /Applications/CMake.app/Contents/bin/cmake ]]; then
  cmake_command=/Applications/CMake.app/Contents/bin/cmake
fi
if [[ -n "$cmake_command" ]]; then
  cmake_version="$("$cmake_command" --version | awk 'NR == 1 {print $3}')"
  if awk -v version="$cmake_version" 'BEGIN {split(version,v,"."); exit !(v[1] > 3 || (v[1] == 3 && v[2] >= 21))}'; then
    printf 'OK: CMake %s\n' "$cmake_version"
  else
    printf 'MISSING: CMake >= 3.21 (found %s)\n' "$cmake_version"
    missing=1
  fi
else
  printf 'MISSING: native macOS CMake >= 3.21\n'
  missing=1
fi

printf '\nRuntime execution:\n'
if /usr/bin/arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
  printf 'OK: x86_64 execution (Rosetta on Apple Silicon)\n'
else
  printf 'MISSING: x86_64 execution; Rosetta is required for the x86_64 Wine runtime\n'
  missing=1
fi

printf '\nFor the Wine milestone, run: bash independent/scripts/wine-host-doctor.sh\n'

printf '\nOptional Xcode build tools:\n'
if xcrun --find metal >/dev/null 2>&1; then
  printf 'Found: Metal compiler\n'
else
  printf 'Metal compiler not found. Full Xcode/Metal tools are needed for targets that compile Metal shaders.\n'
fi
if xcodebuild -version >/dev/null 2>&1; then
  printf 'Found: full Xcode (needed if we choose a SwiftUI app target)\n'
else
  printf 'Full Xcode not selected. It is optional for the pinned fork\047s documented CMake route.\n'
fi

printf '\nNo tools, applications, or game bottles were modified. See independent/docs/DEVELOPMENT.md.\n'
exit "$missing"
