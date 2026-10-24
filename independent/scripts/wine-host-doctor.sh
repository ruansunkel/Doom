#!/usr/bin/env bash
# Read-only prerequisite checks; compile probes use disposable temporary files.
set -o pipefail

if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this script in a macOS host Terminal.' >&2
  exit 2
fi

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
missing=0
native_ready=1
check_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    printf 'OK: %s\n' "$1"
  else
    printf 'MISSING: %s\n' "$1"
    missing=1
    return 1
  fi
}
version_at_least() {
  awk -v found="$1" -v minimum="$2" 'BEGIN {
    split(found, f, "."); split(minimum, m, ".")
    for (i = 1; i <= 3; i++) {
      if (f[i] + 0 > m[i] + 0) exit 0
      if (f[i] + 0 < m[i] + 0) exit 1
    }
    exit 0
  }'
}
check_version() {
  local tool="$1" minimum="$2" output version
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'MISSING: %s >= %s\n' "$tool" "$minimum"
    missing=1
    return
  fi
  output="$("$tool" --version 2>/dev/null)"
  version="$(printf '%s\n' "$output" | awk 'NR == 1 {
    for (i = 1; i <= NF; i++) if ($i ~ /^[0-9]+\.[0-9]+/) {print $i; break}
  }')"
  if [[ -n "$version" ]] && version_at_least "$version" "$minimum"; then
    printf 'OK: %s %s\n' "$tool" "$version"
  else
    printf 'MISSING: %s >= %s (found %s)\n' "$tool" "$minimum" "${version:-unknown version}"
    missing=1
  fi
}

printf 'Experimental native macOS Wine build prerequisites:\n'
check_tool make
check_tool pkg-config
check_version bison 3.0
check_version flex 2.5.33
check_tool file || native_ready=0
check_tool xcrun || native_ready=0
if [[ "$native_ready" == 1 ]] && xcrun --find clang >/dev/null 2>&1 &&
    xcrun --sdk macosx --show-sdk-path >/dev/null 2>&1; then
  printf 'OK: Apple Clang and macOS SDK\n'
else
  printf 'MISSING: Apple Clang/macOS SDK for the native x86_64 compile probes\n'
  native_ready=0
  missing=1
fi

if /usr/bin/arch -x86_64 /usr/bin/true >/dev/null 2>&1; then
  printf 'OK: x86_64 execution (Rosetta on Apple Silicon)\n'
else
  printf 'MISSING: x86_64 execution; the runtime needs Rosetta on Apple Silicon\n'
  missing=1
fi

probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/doom-wine-doctor.XXXXXX")" || exit 1
trap 'rm -rf -- "$probe_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
cat > "$probe_dir/basic.c" <<'C'
int main(void) { return 0; }
C

printf '\nNative x86_64 compile/link probe:\n'
if [[ "$native_ready" == 1 ]]; then
  if xcrun --sdk macosx clang -arch x86_64 "$probe_dir/basic.c" -o "$probe_dir/native" >"$probe_dir/native.log" 2>&1 &&
      [[ "$(file -b "$probe_dir/native")" == *Mach-O*x86_64* ]]; then
    printf 'OK: linked an x86_64 Mach-O executable\n'
  else
    printf 'MISSING: working Apple Clang/macOS SDK x86_64 linker\n'
    cat "$probe_dir/native.log"
    native_ready=0
    missing=1
  fi
else
  printf 'MISSING: cannot run native link probe until tools above are available\n'
fi

printf '\nWindows PE compile/link probes (never executed):\n'
for pe_arch in i686 x86_64; do
  pe_ok=0
  for compiler in "$pe_arch-w64-mingw32-gcc" "$pe_arch-w64-mingw32-clang"; do
    if ! command -v "$compiler" >/dev/null 2>&1; then
      continue
    fi
    if "$compiler" "$probe_dir/basic.c" -o "$probe_dir/$pe_arch.exe" >"$probe_dir/$pe_arch.log" 2>&1 &&
        command -v file >/dev/null 2>&1; then
      description="$(file -b "$probe_dir/$pe_arch.exe")"
      case "$pe_arch:$description" in
        i686:*'PE32 executable'*80386*|x86_64:*'PE32+ executable'*x86-64*)
          printf 'OK: %s linked %s PE executable\n' "$compiler" "$pe_arch"
          pe_ok=1
          break
          ;;
      esac
    fi
    printf 'Probe failed: %s\n' "$compiler"
    cat "$probe_dir/$pe_arch.log"
  done
  if [[ "$pe_ok" != 1 ]]; then
    printf 'MISSING: working %s-w64-mingw32-gcc or %s-w64-mingw32-clang with PE headers/libraries\n' "$pe_arch" "$pe_arch"
    missing=1
  fi
done

cat > "$probe_dir/freetype2.c" <<'C'
#include <ft2build.h>
#include FT_FREETYPE_H
int main(void) { FT_Library library; return FT_Init_FreeType(&library); }
C
cat > "$probe_dir/gnutls.c" <<'C'
#include <gnutls/gnutls.h>
int main(void) { return gnutls_global_init(); }
C
printf '\nNative x86_64 libraries (arm64-only libraries cannot satisfy these checks):\n'
for package in freetype2 gnutls; do
  if [[ "$native_ready" != 1 ]] || ! command -v pkg-config >/dev/null 2>&1; then
    printf 'MISSING: cannot probe %s until Apple Clang/SDK and pkg-config are available\n' "$package"
    missing=1
    continue
  fi
  if ! pkg-config --exists "$package"; then
    printf 'MISSING: pkg-config package %s (x86_64 headers and libraries)\n' "$package"
    missing=1
    continue
  fi
  read -r -a package_cflags <<< "$(pkg-config --cflags "$package")"
  read -r -a package_libs <<< "$(pkg-config --libs "$package")"
  if xcrun --sdk macosx clang -arch x86_64 "${package_cflags[@]}" "$probe_dir/$package.c" \
      "${package_libs[@]}" -o "$probe_dir/$package" >"$probe_dir/$package.log" 2>&1 &&
      [[ "$(file -b "$probe_dir/$package")" == *Mach-O*x86_64* ]]; then
    printf 'OK: %s headers and libraries link as x86_64\n' "$package"
  else
    printf 'MISSING: usable x86_64 %s headers/libraries; check pkg-config paths and library architecture\n' "$package"
    cat "$probe_dir/$package.log"
    missing=1
  fi
done

printf '\nProject MoltenVK library:\n'
library="$project_root/build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib"
if [[ ! -f "$library" ]]; then
  printf 'MISSING: %s (run independent/scripts/build-moltenvk.sh first)\n' "$library"
  missing=1
elif ! command -v lipo >/dev/null 2>&1; then
  printf 'MISSING: lipo to verify the built MoltenVK architectures\n'
  missing=1
else
  for library_arch in x86_64 arm64; do
    if lipo "$library" -verify_arch "$library_arch"; then
      printf 'OK: MoltenVK %s\n' "$library_arch"
    else
      printf 'MISSING: MoltenVK %s slice\n' "$library_arch"
      missing=1
    fi
  done
fi

printf '\nNo tools, runtimes, applications, or game bottles were installed or modified.\n'
printf 'This checks the experimental build prerequisites; it does not establish that Wine or DOOM works.\n'
exit "$missing"
