#!/usr/bin/env bash
# Build the pinned upstream Wine runtime.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Build Wine on the macOS host.' >&2
  exit 2
fi
configure_only=0
portable=0
for argument in "$@"; do
  case "$argument" in
    --configure-only) configure_only=1 ;;
    --portable) portable=1 ;;
    *) echo 'Usage: bash independent/scripts/build-wine.sh [--configure-only] [--portable]' >&2; exit 2 ;;
  esac
done
# shellcheck source=independent/scripts/host-env.sh
source "$project_root/independent/scripts/host-env.sh"
bash "$project_root/independent/scripts/wine-host-doctor.sh"

source_dir="$project_root/third_party/wine-11.20"
build_dir="$project_root/build/wine-upstream-x86_64"
install_dir="$project_root/artifacts/wine-upstream"
if [[ "$portable" == 1 ]]; then
  build_dir="$project_root/build/wine-portable-x86_64"
  install_dir="$project_root/artifacts/wine-portable"
fi
moltenvk_dir="$project_root/build/moltenvk-doom2016/MoltenVK"
if [[ ! -f "$source_dir/configure" || ! -f "$source_dir/COPYING.LIB" ]]; then
  echo 'First fetch the pinned Wine sources with python3 independent/scripts/upstream-wine-source.py.' >&2
  exit 1
fi
[[ ! -L "$build_dir" && ! -L "$install_dir" ]] || {
  echo 'Build/install directories must not be symlinks.' >&2
  exit 1
}
mkdir -p "$build_dir" "$project_root/artifacts"

apple_clang="$(xcrun --sdk macosx --find clang)"
apple_clangxx="$(xcrun --sdk macosx --find clang++)"
sdk="$(xcrun --sdk macosx --show-sdk-path)"
export CC="$apple_clang -arch x86_64"
export CXX="$apple_clangxx -arch x86_64"
export SDKROOT="$sdk"
export MACOSX_DEPLOYMENT_TARGET=14.0
export i386_CC="$doom_pe_toolchain/bin/i686-w64-mingw32-clang"
export x86_64_CC="$doom_pe_toolchain/bin/x86_64-w64-mingw32-clang"
export CPPFLAGS='-I/opt/local/include'
export LDFLAGS="-L$moltenvk_dir -L/opt/local/lib"
# Never discover an unrelated installed Vulkan loader before our MoltenVK.
export ac_cv_lib_soname_vulkan=
# Bind Wine's Vulkan bridge to the project-built graphics library.
export ac_cv_lib_soname_MoltenVK="$moltenvk_dir/libMoltenVK.dylib"
if [[ "$portable" == 1 ]]; then
  # Resolved by dlopen relative to lib/wine/x86_64-unix/win32u.so.
  export ac_cv_lib_soname_MoltenVK='@loader_path/../../../native/libMoltenVK.dylib'
fi
unset WINEPREFIX WINEDLLPATH WINESERVER WINELOADER
unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH

cd "$build_dir"
"$source_dir/configure" \
  --build=x86_64-apple-darwin \
  --host=x86_64-apple-darwin \
  --prefix="$install_dir" \
  --enable-archs=i386,x86_64 \
  --disable-tests \
  --with-coreaudio \
  --with-freetype \
  --with-gnutls \
  --with-vulkan \
  --without-x \
  --without-wayland \
  --without-cups \
  --without-gstreamer \
  --without-ffmpeg

if [[ "$configure_only" == 1 ]]; then
  printf 'Configured only: %s\n' "$build_dir"
  exit 0
fi

# Keep the host usable during long native/PE compilation.
jobs="$(sysctl -n hw.ncpu 2>/dev/null || echo 8)"
if [[ "$jobs" -gt 8 ]]; then jobs=8; fi
make -j"$jobs"
make install
mkdir -p "$install_dir/share/licenses/wine"
cp "$source_dir/COPYING.LIB" "$install_dir/share/licenses/wine/COPYING.LIB"
printf 'Installed source-built Wine into: %s\n' "$install_dir"
printf 'Next: bash independent/scripts/run-wine.sh --print-config\n'
