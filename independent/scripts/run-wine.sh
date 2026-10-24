#!/usr/bin/env bash
# Isolated source-built Wine smoke runner; the game launcher is independent/scripts/doom-runner.sh.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: bash independent/scripts/run-wine.sh [--prefix PATH] [--trace-libraries] -- WINE_COMMAND [ARGS...]
       bash independent/scripts/run-wine.sh [--prefix PATH] --print-config

Runs the project's macOS Wine runtime with patched MoltenVK.
Uses the upstream Wine runtime. Prefixes must stay inside build/prefixes/.
Portable packages use bundled native libraries; development builds use /opt/local/lib.
EOF
}

if [[ "$#" == 0 ]]; then
  usage >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ -x "$project_root/bin/python3" ]]; then export PATH="$project_root/bin:$PATH"; fi
prefix="$project_root/build/prefixes/upstream-smoke"
runtime_root="$project_root/artifacts/wine-upstream"
print_config=0
trace_libraries=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --prefix)
      if [[ "$#" -lt 2 || -z "$2" ]]; then
        echo '--prefix requires a path.' >&2
        exit 2
      fi
      prefix="$2"
      shift 2
      ;;
    --print-config) print_config=1; shift ;;
    --trace-libraries) trace_libraries=1; shift ;;
    --help|-h) usage; exit 0 ;;
    --) shift; break ;;
    *) usage >&2; exit 2 ;;
  esac
done
if [[ "$print_config" == 1 && "$#" -gt 0 ]] || [[ "$print_config" == 0 && "$#" == 0 ]]; then
  usage >&2
  exit 2
fi
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run this runtime on the macOS host.' >&2
  exit 2
fi

# Discard inherited runtime overrides before invoking any subprocesses.
unset WINEDLLPATH WINEPATH DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
unset WINELOADER WINESERVER WINESERVERSOCKET WINELOADERNOEXEC
runtime="$runtime_root/bin/wine"
if [[ ! -x "$runtime" ]]; then
  runtime="$runtime_root/bin/wine64"
fi
server="$runtime_root/bin/wineserver"
graphics="$project_root/build/moltenvk-doom2016/MoltenVK/libMoltenVK.dylib"
native_dependencies=/opt/local/lib
if [[ -f "$project_root/package-manifest.json" || -d "$runtime_root/native" ]]; then
  graphics="$runtime_root/native/libMoltenVK.dylib"
  native_dependencies="$runtime_root/native"
fi
if [[ ! -x "$runtime" || ! -x "$server" ]]; then
  printf 'Build and install the selected source Wine runtime into %s first.\n' "$runtime_root" >&2
  exit 1
fi
if [[ ! -f "$graphics" ]]; then
  if [[ "$native_dependencies" == /opt/local/lib ]]; then
    echo 'Build the graphics library first: bash independent/scripts/build-moltenvk.sh' >&2
  else
    echo 'Bundled graphics library is missing; copy a fresh, complete portable package.' >&2
  fi
  exit 1
fi

# resolve() follows existing symlink parents even when the new prefix is absent.
prefix="$(python3 - "$prefix" "$project_root" "$runtime_root" "$runtime" "$server" "$graphics" <<'PY'
from pathlib import Path
import sys

prefix, project, root, runtime, server, graphics = (
    Path(value).expanduser().resolve() for value in sys.argv[1:]
)
for path, parent in ((root, project), (runtime, root), (server, root), (graphics, project)):
    try:
        path.relative_to(parent)
    except ValueError:
        raise SystemExit("Runtime and graphics symlinks must stay inside the source-built workspace.")

try:
    prefix.relative_to(project / "build" / "prefixes")
except ValueError:
    raise SystemExit("Prefixes must stay inside this workspace's build/prefixes directory.")
if prefix.exists() and not prefix.is_dir():
    raise SystemExit("The test prefix path exists and is not a directory.")
print(prefix)
PY
)"

if [[ "$print_config" == 1 ]]; then
  printf 'Runtime: %s\nPrefix: %s\nGraphics library: %s\n' "$runtime" "$prefix" "$graphics"
  printf 'Source: upstream Wine\n'
  printf 'Native dependencies: %s\n' "$native_dependencies"
  exit 0
fi

export WINEPREFIX="$prefix"
export WINESERVER="$server"
# The source build currently dlopens MacPorts FreeType/GnuTLS by basename.
export DYLD_FALLBACK_LIBRARY_PATH="$native_dependencies"
export PATH="$runtime_root/bin:/usr/bin:/bin:/usr/sbin:/sbin"
mkdir -p -- "$prefix"
# Set this after system shell/subprocess launches, which can strip DYLD options.
if [[ "$trace_libraries" == 1 ]]; then export DYLD_PRINT_LIBRARIES=1; fi
exec "$runtime" "$@"
