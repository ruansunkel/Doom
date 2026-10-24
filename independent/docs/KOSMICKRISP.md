# KosmicKrisp tests for the DOOM runner

Tested 24 October 2026. The working DOOM installation continues to use patched
MoltenVK. The official KosmicKrisp SDK has now been installed locally and probed;
DOOM cannot use that binary with our current Wine runtime.

## Measured SDK results

The pinned SDK **1.4.363.0** was downloaded from LunarG and verified against
[its published release metadata](https://vulkan.lunarg.com/sdk/files.json):

```text
vulkansdk-macos-1.4.363.0.zip
SHA-256: 163431e0203c8215286a17cf393643ce6b951f77d1b4f74ab30821a1f0beb09b
```

It lives in `build/vulkan-sdk/1.4.363.0`. Installation used `copy_only=1`,
without copying drivers to system directories. Reproduce setup and diagnosis:

```bash
bash independent/scripts/setup-kosmickrisp-sdk.sh
bash independent/scripts/probe-kosmickrisp.sh
```

The diagnostic intentionally exits nonzero while either architecture cannot
create a device with both required DOOM features. Run it on the host with GPU
access; a sandboxed native probe failed initialization before GPU enumeration.

- The Vulkan Loader is universal (`x86_64` and `arm64`).
- `libvulkan_kosmickrisp.dylib` is **arm64 only**. The x86_64 probe fails with
  `VK_ERROR_INCOMPATIBLE_DRIVER` (-9); loader diagnostics explicitly report
  `have arm64, need x86_64`. Our Rosetta Wine process cannot load this driver.
- With host GPU access, the arm64 probe successfully enumerated **Apple M1 Max,
  Vulkan 1.4.363, depthBounds=0, shaderCullDistance=1**. It correctly refused
  device creation with the missing required feature.

Recorded local logs: `build/kosmickrisp-native-arm64.log`,
`build/kosmickrisp-native-x86_64.log`, and
`build/kosmickrisp-loader-x86_64.log`. These are capability tests, not a DOOM
launch or gameplay validation.

The next development work needs a driver usable from x86_64 Wine (for example,
a custom x86_64 KosmicKrisp source build, whose feasibility is unverified), or
an architecture bridge/runtime that can call the arm64 driver. After that,
DOOM still needs a depth-bounds solution on this GPU. Advertising the feature
alone would be an experimental game workaround, not correct hardware support.
The full Xcode and native LLVM/Mesa source-build dependencies are currently
missing. The SDK alone does not resolve either blocker.

## Why consider it

[LunarG describes KosmicKrisp](https://www.lunarg.com/products/kosmickrisp/) as an
MIT-licensed Mesa Vulkan driver using Metal 4, with Vulkan 1.4 conformance.
It targets Apple Silicon on macOS 26 or newer. This M1 Max on macOS 27 meets
that broad platform requirement.

The current [MoltenVK repository](https://github.com/KhronosGroup/MoltenVK)
announces Khronos deprecation and recommends KosmicKrisp for Apple Silicon
Macs. That makes it relevant to the long-term backend choice, while the
game-specific compatibility checks below remain necessary.

## Important DOOM/M1 Max limitation found in source

The assessment inspected Mesa commit
`19a135296672f24ec1699ada244d5b80ced371da`, committed 24 October 2026 in UTC.
Its [physical-device feature table](https://gitlab.freedesktop.org/mesa/mesa/-/blob/19a135296672f24ec1699ada244d5b80ced371da/src/kosmickrisp/vulkan/kk_physical_device.c)
contains:

```c
.depthBounds = pdev->info.gpu_apple_family >= 10,
.shaderCullDistance = true,
```

Our existing M1 Max runtime log identifies **Apple GPU family 7**. The initial
unmodified DOOM Vulkan test failed while requesting `depthBounds`; the patched
MoltenVK advertises it and skips the unsupported hardware test.
The pinned [Metal bridge](https://gitlab.freedesktop.org/mesa/mesa/-/blob/19a135296672f24ec1699ada244d5b80ced371da/src/kosmickrisp/bridge/mtl_device.m)
counts supported Apple families from 1 upward, so the comparison uses ordinal
family numbers, not Metal's larger enum constants.

Consequently, the inspected KosmicKrisp source would not advertise the required
depth-bounds feature on this GPU. The native SDK probe above now also confirms
the missing feature. Vulkan 1.4 conformance does not imply every optional Vulkan
feature is available.

| Requirement | Patched MoltenVK baseline | Inspected KosmicKrisp source |
| --- | --- | --- |
| M1 Max/macOS platform | Existing DOOM gameplay confirmed | Broad platform requirements match |
| `depthBounds` | Advertised by DOOM-specific workaround | Requires Apple GPU family >= 10; M1 Max is family 7 |
| `shaderCullDistance` | Advertised by workaround | Advertised |
| Vertex-input behavior | DOOM-specific workaround present | Different compiler/runtime; actual DOOM test needed |
| Gameplay | Confirmed with source-built Wine 11.20 and MoltenVK | Not tested |

Keep the source-built MoltenVK as the initial reference. Before switching to
KosmicKrisp, resolve its architecture and depth-bounds blockers and validate any
DOOM compatibility workaround. No general feature-compatibility or
performance claim follows from the API version alone.

## Integration differs from direct MoltenVK loading

The [macOS Vulkan SDK guide](https://vulkan.lunarg.com/doc/view/latest/mac/getting_started.html)
requires the **Vulkan Loader** for KosmicKrisp. It does not support substituting
the driver directly for our `libMoltenVK.dylib`.

The intended experimental path is:

```text
DOOM -> Wine Vulkan bridge -> Vulkan Loader -> KosmicKrisp ICD -> Metal 4
```

The SDK documents per-process driver selection through `VK_DRIVER_FILES`, using
`share/vulkan/icd.d/libkosmickrisp_icd.json`. Its metadata reported SDK
**1.4.363.0** when checked. The setup script pins that release and its published
archive checksum.

For our current Wine design, both the loader and driver must be loadable in an
**x86_64 process under Rosetta**. Support for Apple Silicon GPUs does not by
itself establish those binary slices. The SDK describes universal libraries
generally, but inspection now confirms that this driver is arm64 only.

Our current `run-wine.sh` deliberately selects source-built MoltenVK and
overrides inherited graphics settings. A KosmicKrisp mode must explicitly select
the loader and ICD manifest; merely setting `VK_DRIVER_FILES` before calling
the existing helper is insufficient. Keep backend selection local to the test
process rather than changing system-wide Vulkan configuration.

KosmicKrisp does not require/support `VK_KHR_portability_enumeration` as MoltenVK
does. The project's Vulkan smoke probe already checks whether that extension
exists before enabling it.

The shared probe builds a native macOS program, defaulting to x86_64 to match
Wine. Set `VULKAN_PROBE_ARCH=arm64` to check native Apple Silicon support:

```bash
bash independent/scripts/probe-vulkan.sh
# Once a loader/ICD is obtained and its manifest path is known:
VK_DRIVER_FILES=/absolute/path/to/libkosmickrisp_icd.json \
  bash independent/scripts/probe-vulkan.sh /absolute/path/to/libvulkan.1.dylib
```

The default source-built MoltenVK passed this probe on the M1 Max with both
required features enabled. The installed KosmicKrisp results are recorded above.
The explicit-library probe measures device creation only; it does not change the Wine backend or
establish game compatibility.

## Build requirements and next test

[Mesa's build guide](https://docs.mesa3d.org/drivers/kosmickrisp.html) lists full
Xcode plus Command Line Tools, Meson >= 1.9.1, CMake, pkg-config, LLVM >= 20.1.8,
libclc, SPIR-V LLVM Translator, SPIR-V Tools, and Python packages Mako, packaging,
and PyYAML. Those are separate native Mesa requirements; our cached LLVM-MinGW
PE cross-compiler is not a replacement for a native LLVM development SDK.

A future KosmicKrisp source build would also run on the Mac host. Full Xcode
and the native Mesa build dependency set remain uninstalled; only the binary
Vulkan SDK has been installed locally.

Next steps beyond the working Wine/MoltenVK baseline:

1. Resolve the measured SDK architecture blocker with a compatible driver/runtime.
2. Verify the loader/driver architectures and ICD library resolution.
3. Resolve the measured missing `depthBounds` feature on the M1 Max and rerun
   the capability check with both DOOM features.
4. Add an explicit experimental backend mode and run the Windows Vulkan smoke
   probe through Wine. A missing required feature should remain a clear failure.
5. If that passes, compare DOOM startup, rendering, gameplay, and performance
   against the known-working baseline in a separate prefix.
