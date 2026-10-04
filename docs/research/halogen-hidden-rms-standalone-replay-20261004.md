# Exact standalone hidden-RMS replay

The retained native gfx1151 RMS kernel can be launched without starting Halogen
or loading a model. The new host-only
[replay source](../../scripts/benchmarks/halogen0162_hidden_rms_replay.c) implements
two frozen A/B calls through dynamically resolved HIP module APIs. Root compiled
and executed the original kernel successfully on October 4. For these two inputs,
the native output matches the NumPy RMS reference bit for bit. The complete NPU
head remains unqualified.

The retained original code artifacts are:

| Artifact | Identity |
|---|---|
| `backends/halogen-wsl2-0.16.2/.local/flash_serve` | 26,052,768 bytes, SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| `server/.local/optimization9h-20261004/mtp-route-static-20261004/engine-gfx1151.hsaco` | 17,704,408 bytes, SHA256 `45941c0579dc3487d07978a50c85cbaa141bbb674b225e708e82d81397334a83` |
| Retained RMS GPU disassembly | SHA256 `dbd3c9ea1e560f13aad9156fb7867bfe441872b8591ee87b6fc2d15d1b2bba95` |

Static Windows LLVM inspection of those code artifacts proves the binding:

1. The host `.hip_fatbin` begins at file offset/RVA `0x50000`. Its first offload
   bundle has target `hipv4-amdgcn-amd-amdhsa--gfx1151`, relative offset 4096 and
   size 17,704,408; the raw shader starts at engine file offset `0x51000`.
2. The HIP wrapper at RVA `0x18da728` has a relative relocation at `0x18da730`
   to bundle RVA `0x50000`. Constructor call `0x1858d76` passes that wrapper to
   `__hipRegisterFatBinary@plt` (`0x18d3b20`), then call `0x1858d85` passes the
   returned handle to the registration routine at `0x18483d0`.
3. That routine's call at `0x1848906` registers host identity `0x18d5160` with
   the exact device name `_ZN7halogen12_GLOBAL__N_117k_rmsnorm_groupedEPKtS2_Ptii`
   (name RVA `0x248c5`). The native hidden-RMS launch returns at `0x17db632`.
4. The raw shader symbol is a 1004-byte protected global function at `0x22d200`.
   Its 64-byte descriptor is the same mangled name plus `.kd` at `0x1f6cc0`.
   The ELF is AMDGPU HSA ABI4, little-endian 64-bit, gfx1151 (`e_flags=0x4a`).

Kernel metadata gives three eight-byte buffer arguments at offsets 0, 8 and 16,
then two four-byte values at offsets 24 and 28. The module API must supply the
hidden arguments: total kernarg size is 288, alignment 8, including hidden group
size X at offset 44. Packing only a 32-byte `extra` block would omit them. Static
LDS is 1024 bytes, private storage is zero, wave width is 32, and maximum workgroup
size is 1024. The replay uses the existing native hidden-RMS configuration: input,
raw gamma, output, width 10240, groups 1, grid `[1,1,1]`, block `[256,1,1]`, zero
dynamic shared memory, and default stream. There is no substitute kernel.

The harness first checks the engine and shader seals and compares every shader
byte to the original engine payload. Root supplies an actual regular Linux HIP
library path and its SHA256, two exact 20,480-byte input/gamma files with their
SHA256 values, and an exclusive new output directory. Inputs are read as raw BF16
words without conversion or adjustment. It loads one module, resolves the exact
name, reuses three 20,480-byte device buffers for two calls, synchronizes each,
and records input/gamma/output hashes and error/call/cleanup counts. Successful
outputs total 40,960 bytes plus a report smaller than 4096 bytes. Failure records
preserve the error; external controller exit status remains authoritative.

Compile only the host source with the reviewed HIP headers, libdl and libcrypto;
do not link an alternative SDK HIP implementation. Root owns compilation, frozen
fixture preparation, runtime execution, 22-GiB admission and the continuous
18-GiB reserve watch, Linux deadline, owned container cleanup and recovery check.

The existing pinned Docker image is
`ghcr.io/peonist-ai/halogen-flash-server@sha256:0c61bf84ac22308a53f5d1ca6b86806702d7039e5ebc51cae4c66621b92fe04a`.
Its existing runtime needs `/dev/dxg`, `HSA_ENABLE_DXG_DETECTION=1`, and read-only
mounts of `/usr/lib/wsl/lib/libdxcore.so` to `/usr/lib/libdxcore.so` and
`/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocdxg.so.1`
to `/usr/lib/librocdxg.so`. The retained DXG library seal is
`0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`.
The source dynamically loads the actual image's HIP runtime. It does not need
the engine-specific preflight/registration observers or any model mount. Existing
runtime library search paths/dependencies must be preserved by the root wrapper.

This method qualifies only the original standalone kernel on supplied frozen
inputs. It does not observe a new complete-head residual, live wire D,
target verification, MTP acceptance, end-to-end speed or NPU execution. Those
requirements stay open, and the earlier failed CPU screen/tolerances stay intact.

## Execution and arithmetic evidence

The host replay was built with GCC `-O2 -Wall -Wextra -Werror`, the reviewed HIP
headers, `libdl` and `libcrypto`; executable SHA256 is
`1e308fd9fcc555df89aae2e7312187a66a6ef3d2102adce8023e9146c4dfc01c`.
The dynamically loaded pinned image HIP library has SHA256
`6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5`.
The C harness verified every retained shader byte against the sealed engine.

The frozen fixture manifest is
`server/.local/optimization9h-20261004/rms-kernel-fixtures-32a8c40bb6e345b3bf6a90d9fda3e666/fixtures.json`,
SHA256 `1b0c66d46406598028d573353a6e24f42e54527e69a3cf022bf0ffa4284e15a6`.
It retains input, raw gamma, original CPU-ORT RMS and NumPy RMS words. A is the
retained live hidden residual; B is the already frozen distinct synthetic feed.

| Input | Native vs NumPy BF16 word differences | Native vs CPU-ORT BF16 word differences | Maximum native vs CPU-ORT absolute error |
|---|---:|---:|---:|
| A | 0 | 2 | 0.0078125 |
| B | 0 | 4 | 0.00390625 |

Native A output SHA256 is
`bf43576e6a9d47efb9a15bcba42d74618ade2ea64b025e747d1c6960e2ddff34`;
native B is
`0a46c80b3de775d94eee31b1ca4b3927fe8368353f12f5a40314d88591a31711`.
The successful owned window is
`server/.local/optimization9h-20261004/alloy-rms-original-02735783579e4a018abc755f9ab19c9b`;
its native replay receipt SHA256 is
`4fecd22ab29a9f6d27139eb3b9c313cd7dd5229c406c84f406e8dfd6bbeed9ec`.
It records two successful launches/synchronizations, eight copies, three
allocations/frees, one module load/unload and no errors. The owned Windows job
closed, the owned container was removed and the memory monitor stopped. Minimum
physical/commit headroom was 46.694/203.505 GiB. No full model was mounted.

An earlier controller attempt failed before child launch because a relative
`wsl.exe` path resolved beneath the workspace. That failed receipt remains under
`alloy-rms-original-eb4ba7daca374bec9d2907ef5ca6da02`; the successful controller
uses `C:\Windows\System32\wsl.exe` explicitly.

These results establish the native RMS result for A/B, rather than general
full-D or FC parity. Epsilon/gamma, the frozen tolerances and the earlier failed
NumPy full-D seed screen were not changed.
