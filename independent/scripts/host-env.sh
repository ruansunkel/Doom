#!/usr/bin/env bash
# Source this file in a host shell; all overrides are scoped to that shell.
doom_env_file="${BASH_SOURCE[0]:-$0}"
doom_project_root="$(cd -- "$(dirname -- "$doom_env_file")/../.." && pwd)"
doom_pe_toolchain="$doom_project_root/.cache/host-tools/llvm-mingw-20261020-ucrt-macos-universal"
export PATH="$doom_project_root/.venv/bin:$doom_project_root/.cache/host-tools/shellcheck-v0.11.0:$doom_pe_toolchain/bin:/opt/local/bin:/opt/local/sbin:/Applications/CMake.app/Contents/bin:$PATH"
export PKG_CONFIG_PATH=
export PKG_CONFIG_LIBDIR='/opt/local/lib/pkgconfig:/opt/local/share/pkgconfig'
