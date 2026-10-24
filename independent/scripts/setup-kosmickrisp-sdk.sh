#!/usr/bin/env bash
# Install the pinned experimental SDK locally, without system Vulkan changes.
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$#" != 0 ]]; then
  echo 'Usage (macOS): bash independent/scripts/setup-kosmickrisp-sdk.sh' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
version=1.4.363.0
sha256=163431e0203c8215286a17cf393643ce6b951f77d1b4f74ab30821a1f0beb09b
archive="$project_root/.cache/vulkansdk-macos-$version.zip"
installer_dir="$project_root/.cache/vulkan-sdk-installer-$version"
sdk_root="$project_root/build/vulkan-sdk/$version"
for directory in "$project_root/.cache" "$installer_dir" "$project_root/build" "$project_root/build/vulkan-sdk" "$sdk_root"; do
  if [[ -L "$directory" ]]; then
    echo 'SDK directories must not be symlinks.' >&2
    exit 1
  fi
done
mkdir -p "$project_root/.cache"
if [[ -L "$archive" ]]; then
  echo 'SDK archive must not be a symlink.' >&2
  exit 1
fi
if [[ ! -f "$archive" ]]; then
  curl -fL --retry 2 -o "$archive" \
    "https://sdk.lunarg.com/sdk/download/$version/mac/vulkansdk-macos-$version.zip"
fi
printf '%s  %s\n' "$sha256" "$archive" | shasum -a 256 -c -
if [[ ! -f "$sdk_root/components.xml" ]]; then
  if [[ ! -d "$installer_dir" ]]; then
    unzip -q "$archive" -d "$installer_dir"
  fi
  "$installer_dir/vulkansdk-macOS-$version.app/Contents/MacOS/vulkansdk-macOS-$version" \
    --root "$sdk_root" --cache-path "$project_root/.cache/vulkan-installer" \
    --accept-licenses --default-answer --confirm-command \
    install com.lunarg.vulkan.core copy_only=1
fi
printf 'Workspace SDK: %s/macOS\n' "$sdk_root"
echo 'This installs experimental driver files only; it does not switch Wine or prove DOOM compatibility.'
