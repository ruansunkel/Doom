#!/usr/bin/env bash
# Launch Steam or DOOM with the source-built upstream Wine runtime.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
if [[ -x "$project_root/bin/python3" ]]; then export PATH="$project_root/bin:$PATH"; fi
setup="$project_root/independent/scripts/setup-game.py"
prefix="$(python3 "$setup" --prefix "${DOOM_PREFIX:-$project_root/build/prefixes/doom-upstream}" --print-prefix)"
runner="$project_root/independent/scripts/run-wine.sh"
steam_dir="$prefix/drive_c/Program Files (x86)/Steam"
game_dir="$steam_dir/steamapps/common/DOOM"
mode="${1:-steam}"
if [[ "$#" -gt 1 ]]; then
  echo 'Usage: bash independent/scripts/doom-runner.sh [setup|steam|install|play|windowed|config]' >&2
  exit 2
fi
if [[ "$mode" == config ]]; then
  exec bash "$runner" --prefix "$prefix" --print-config
fi
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Run the independent game runner on the macOS host.' >&2
  exit 2
fi
export WINEDLLOVERRIDES='winemenubuilder.exe=d;mscoree,mshtml='
case "$mode" in
  setup)
    exec python3 "$setup" --prefix "$prefix"
    ;;
  steam|install)
    if [[ ! -f "$steam_dir/Steam.exe" || ! -f "$steam_dir/bin/cef/cef.win64/steamwebhelper.exe" || ! -f "$steam_dir/bin/cef/cef.win64/libcef.dll" ]]; then
      python3 "$setup" --prefix "$prefix"
    fi
    if [[ ! -f "$project_root/build/steam-ui/steamwebhelper.exe" ]]; then
      bash "$project_root/independent/scripts/build-steam-wrapper.sh"
    fi
    python3 "$project_root/independent/scripts/install-steam-wrapper.py" --prefix "$prefix"
    cd -- "$steam_dir"
    args=(-noverifyfiles -cef-disable-gpu -no-cef-sandbox)
    if [[ "$mode" == install ]]; then args+=('steam://install/379720'); fi
    exec bash "$runner" --prefix "$prefix" -- 'C:\Program Files (x86)\Steam\Steam.exe' \
      "${args[@]}"
    ;;
  play|windowed)
    if [[ ! -f "$game_dir/DOOMx64vk.exe" ]]; then
      echo 'Run: bash independent/scripts/doom-runner.sh install, then finish downloading DOOM in Steam.' >&2
      exit 1
    fi
    python3 "$setup" --prefix "$prefix" --check-game
    if [[ ! -f "$prefix/drive_c/windows/system32/mfc140u.dll" ]]; then
      python3 "$setup" --prefix "$prefix" --prerequisites-only
    fi
    echo 'Windows Steam must be running and signed in using this independent runner.'
    # Set the Unix working directory so DOOM resolves its game resources here.
    cd -- "$game_dir"
    export SteamAppId=379720 SteamGameId=379720
    args=('C:\Program Files (x86)\Steam\steamapps\common\DOOM\DOOMx64vk.exe'
          +r_renderAPI 1 +com_skipIntroVideo 1)
    if [[ "$mode" == windowed ]]; then args+=(+r_fullscreen 0); fi
    exec bash "$runner" --prefix "$prefix" -- "${args[@]}"
    ;;
  *)
    echo 'Usage: bash independent/scripts/doom-runner.sh [setup|steam|install|play|windowed|config]' >&2
    exit 2
    ;;
esac
