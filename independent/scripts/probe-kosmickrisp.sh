#!/usr/bin/env bash
# Check the local KosmicKrisp SDK in both native and Wine process architectures.
set -euo pipefail
if [[ "$(uname -s)" != Darwin || "$#" != 0 ]]; then
  echo 'Usage (macOS): bash independent/scripts/probe-kosmickrisp.sh' >&2
  exit 2
fi
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
sdk="$project_root/build/vulkan-sdk/1.4.363.0/macOS"
manifest="$sdk/share/vulkan/icd.d/libkosmickrisp_icd.json"
driver="$sdk/lib/libvulkan_kosmickrisp.dylib"
loader="$sdk/lib/libvulkan.1.dylib"
if [[ ! -f "$manifest" || ! -f "$driver" || ! -f "$loader" ]]; then
  echo 'First run: bash independent/scripts/setup-kosmickrisp-sdk.sh' >&2
  exit 1
fi
# Select exactly this ICD, independent of inherited loader or layer settings.
unset VK_ICD_FILENAMES VK_ADD_DRIVER_FILES VK_INSTANCE_LAYERS VK_LAYER_PATH
unset VK_DRIVER_FILES VK_LOADER_DRIVERS_SELECT VK_LOADER_DRIVERS_DISABLE
unset VK_LOADER_LAYERS_ENABLE VK_LOADER_LAYERS_ALLOW
export VK_DRIVER_FILES="$manifest"
export VK_LOADER_LAYERS_DISABLE='~all~'
export VK_LOADER_DEBUG=error,warn
file "$loader" "$driver"
status=0
for architecture in arm64 x86_64; do
  printf '\nTesting %s device creation with DOOM features:\n' "$architecture"
  if ! VULKAN_PROBE_ARCH="$architecture" bash "$project_root/independent/scripts/probe-vulkan.sh" "$loader"; then
    status=1
  fi
done
if [[ "$status" != 0 ]]; then
  echo 'KosmicKrisp is not ready for this x86_64 Wine/DOOM runner.' >&2
fi
exit "$status"
