# Operating-state diagnostic and historical metadata — 5 October 2026

No safe performance change is established by the retained evidence. The next
concrete diagnostic is a native Windows read of the active adapter's WDDM
engine-frequency, adapter-performance and segment-size records, with adapter
identity and node metadata attached. It can inspect the ready engine without
restarting it. It cannot recover an earlier startup escape result or prove the
cause of the historical 48.423621 versus current roughly 41.3–42 decode tok/s.

This audit read retained source, SDK headers, logs and manifests. It also checked
Microsoft's public structure documentation. It made no hardware/provider query,
process inventory, inference, settings change, build, model-payload read or Git
mutation. No executable collector was built or run.

## Original startup escape

The retained ROCr tree is
`server/.local/rocr-private-source-52061e485927476c8aba16b0e941de14/source/projects/rocr-runtime`.
Its ROCm source commit is `2b22ab0195cc1461cd9abf3b969e9dd7c10af350`;
the retained SDK is 7.14.0, with TheRock commit
`418cd5f63abb7a604bad5874cd7b2e29334e640f`.

`libhsakmt/src/dxg/wddm/device.cpp:90–100` calls
`SetPowerOptimization(false)` after creating a device and restores `true` during
normal destruction. At lines 342–366 the function encodes private Wkmi data,
uses the original adapter/device handles and context zero, sets driver-private
escape type and HardwareAccess, invokes the original `D3DKMTEscape` once, stores
its signed 32-bit `NTSTATUS`, logs through `pr_debug`, then frees the buffer. A
failed status does not change the subsequent behavior. `pr_debug` is removed
under `NDEBUG` (`librocdxg.h:200–219`), so a larger debug level cannot guarantee a
startup receipt.

The smallest source observer would add one unconditional bounded status record
adjacent to that original call. It must preserve arguments, call count, returned
status handling and the destructor's original restore call; it must neither
retry nor issue a diagnostic escape. A successful NTSTATUS establishes acceptance
of that call, not a queried effective policy or a throughput gain. No such
observer is installed or qualified here, and the earlier result cannot be
recovered retroactively without an existing record.

This call belongs to the separately loaded **vendor `librocdxg`**. The source-stock
private Linux `libhsa`/`libhsakmt` build does not replace it. In
`runtime/hsa-runtime/core/runtime/thunk_loader.cpp:56–95`, DXG detection selects
`librocdxg.so` and loads it explicitly. The restored manifest run
`babc627cdc474863b0aa8b2104297d4c` binds `/usr/lib/librocdxg.so` from
`/home/revn/ciru-runtime/venv/lib/python3.14/site-packages/_rocm_sdk_core/lib/librocdxg.so.1`
and `/usr/lib/libdxcore.so` from `/usr/lib/wsl/lib/libdxcore.so`, with installed
libhsa and no private-HSA mount. The historical and initial-slow manifests use
that same DXG source path. A retained vendor-DXG seal from the earlier standalone
replay is `0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`;
this is retained provenance, not fresh proof of a currently loaded mapping.

`libhsakmt/CMakeLists_wsl.txt:119–161` builds the `rocdxg` target with this device
source and requires Windows SDK and `shared/amdgpu-windows-interop/wkmi` headers
and the Wkmi encoder library. Those private dependencies are absent from the
retained tree. Reconstructing a source-stock vendor bridge and adopting it would
therefore require additional dependency and ABI/provenance qualification. A
private-libHSA logging patch alone cannot observe this call.

A plain preload wrapper is also unqualified: `dxcore_loader.cpp` resolves from an
explicit DXCore handle, and `runtime/hsa-runtime/core/util/lnx/os_linux.cpp:283–311`
uses `dlinfo`/`dladdr` to reject an export from a different library. No interposer,
extra power call, driver-private payload reconstruction or live library change
is selected.

## Native Windows getter candidate

The official local SDK is
`C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0`.
The concrete read sequence is:

1. Take the exact adapter LUID from the retained/current GPU-counter cohort;
   verify its identity using a native adapter getter, retaining LUID, name,
   vendor/device IDs and driver version. The retained active LUID is
   `0x00000000_0x00011884`, physical adapter index 0. Treat a changed LUID or failed
   identity query as unavailable rather than substituting the first adapter.
2. Open that adapter with `D3DKMTOpenAdapterFromLuid`. Query
   `KMTQAITYPE_PHYSICALADAPTERCOUNT` (30) and
   `KMTQAITYPE_NODEMETADATA` (25) for the selected node. In
   `shared/d3dkmdt.h:2283–2287`, `NodeOrdinalAndAdapterIndex` packs the physical
   index in the high word and node ordinal in the low word. Retain engine type,
   friendly name and metadata flags. The PDH `eng_2` label is an attribution lead,
   not an independently proved node-ordinal mapping.
3. Query static `KMTQAITYPE_GETSEGMENTSIZE` (3), optionally
   `KMTQAITYPE_GETSEGMENTGROUPSIZE` (42), and
   `KMTQAITYPE_ADAPTERPERFDATA_CAPS` (63) once. Preserve all returned sizes and
   temperature thresholds with units and statuses.
4. For a bounded request window, query `KMTQAITYPE_NODEPERFDATA` (61) with the
   verified physical index/node ordinal, and `KMTQAITYPE_ADAPTERPERFDATA` (62)
   with that physical index. Bracket each synchronous call with host QPC and UTC
   anchors; retain the signed status and raw values separately for each query.
   Use a fixed sample/output ceiling, stop file, hard outer deadline and the
   existing 18-GiB physical/commit guard. Close the adapter on every normal/error
   path and retain the close result. The caller owns and terminates the logger.

The SDK declares complete input/output buffers for these query types; Microsoft's
[query enumeration](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmthk/ne-d3dkmthk-_kmtqueryadapterinfotype)
documents their purpose. This surface needs no GPU device or queue creation,
`D3DKMTEscape`, HSA/ROCr load, inference submission or policy setter. Source review
and a bounded availability run are still required before a measured cohort.
Read availability and collection overhead are currently unqualified.

The
[node-performance record](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmthk/ns-d3dkmthk-_d3dkmt_node_perfdata)
contains current engine frequency and normal/overclocked maxima in Hz, voltage in
mV and maximum frequency-transition latency in units of 100 ns. The maxima are
reported capabilities, not a proved current power limit or throttle reason.

The
[adapter-performance record](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmthk/ns-d3dkmthk-_d3dkmt_adapter_perfdata)
contains memory frequency/maxima in Hz, memory/PCIe transfer amounts, fan RPM,
temperature in 0.1°C and **power in tenths of a percentage, not watts**. Public
documentation describes `PowerStateOverride` as the GPU powered-on flag; the
local header describes overriding dxgkrnl's linked-adapter power view. Preserve
the raw byte and documentation distinction. Neither interpretation exposes AMD's
private power-optimization policy. The transfer amounts are collected on an
interval basis whose boundaries are not established by the host query bracket;
do not label them instantaneous bytes/s or sum/difference them without qualifying
the provider interval. The
[caps record](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/d3dkmthk/ns-d3dkmthk-_d3dkmt_adapter_perfdatacaps)
has static bandwidth maxima and thermal warning/damage thresholds.

An unsupported or failed query remains unknown, with its raw status retained.
Zero values are usable only after successful status and field qualification.
Agreement between request-aligned WDDM frequencies and ADLX would strengthen the
observed current operating range; disagreement is a telemetry lead. These
records cannot establish an unobserved historical machine state, package watts,
STAPM/SMU limits, limiter reason or a safe tuning value.

DXCore's local header also offers support-gated frequency/temperature/memory
state getters (`DXCoreAdapterState:44–57`) and an exact-LUID factory lookup.
The complete newer-state input mapping was not established in this audit, so
the concrete route above uses the fully declared WDDM records. An optional
[DXGI memory-budget query](https://learn.microsoft.com/en-us/windows/win32/api/dxgi1_4/nf-dxgi1_4-idxgiadapter3-queryvideomemoryinfo)
reports the querying process's current budget and usage for a physical adapter
and local/nonlocal group. A standalone logger's usage/reservation is not the WSL
engine's reservation and is not a BIOS UMA-reservation measurement; it must be
labelled accordingly. No memory reservation setter is needed.

## Retained memory and power comparison

All four ADLX discovery logs below return success for the Radeon 8060S device
`1586`, total VRAM 65,536 MB, dedicated-usage range 0–65,536 MB and shared-memory
range 0–32,587 MB:

| Retained cohort | First sample UTC | ADLX log SHA-256 |
|---|---|---|
| Earlier stock8K sensor cohort `fb606…` | Oct 4 05:26:44.009 | `7d6027f61df7888197d7cf761ea11b3894d8fd795e74575f9111050a59be50a2` |
| Initial colleague-control sensors `956f…` | Oct 4 22:00:50.238 | `3cd4600c0cca78d67ebf6a8bbe313d984f0835e652c7addbe909be70b02b14a5` |
| Conditioned-control sensors `0bbd…` | Oct 4 22:22:24.033 | `2cc59c21f93da0702cd48a7db0e82876adc51cc47c6e0bee639ae043b81c329f` |
| CPU/paging-control sensors `3427…` | Oct 4 23:16:18.564 | `f031f4063a716341f6cabcb71e18f444e5adf08017366f16dbda06bae479df7d` |

This supports unchanged **reported capacities/ranges at those observations**.
Usage itself is dynamic. These values do not identify a physical firmware UMA
reservation, driver-managed partition, adapter budget or WSL allocation policy.
No bound historical/current BIOS-UMA readback was found. The exact 48.423621
stock reference has no matched sensor cohort, so the earlier sensor discovery
cannot be silently attached to that request.

The exact historical, initial-slow and later restored manifests all retain
context/pool 262,144, one slot, host reserve 18 GiB,
`HALOGEN_HYBRID_COPY_BYTES=68719476736`, pinned trunk and the same device64/chunk64
and vgm64 profiles. The existing
[gap audit](halogen-performance-gap-audit-20261005.md) also qualifies matched
startup allocation for the historical and initial-slow engines. Host reserve is
an admission threshold, not a GPU/BIOS reservation. No changed requested memory
partition is proved by these manifests.

The earlier scout (Oct 3 23:49:30 UTC) names active scheme `REV:N Performance`.
The gap audit records the root's later readback with the same name, AC EPP0 and
maximum CPU100; the exact older/newer raw scheme GUID and per-setting receipts
are not both retained here. Therefore the name supplies no evidence of a changed
scheme, but does not prove identical policy values or OEM firmware mode at the
two performance windows.

The sealed later Windows mode receipt at Oct 4 22:38:37.597483 UTC has AC online,
energy saver0, successful configured-AC GUID
`ded574b5-45a0-4f42-8737-46345c09c238` (Best Performance) and successful effective
callback mode4 (MaxPerformance). This is a later standalone timestamp, not a
historical/current paired request measurement. The
[Windows/ADLX report](halogen-windows-power-readback-20261005.md) retains
SmartShift=false and PowerDistribution=false; SmartShiftMax support query failed
with ADLX_FAIL and remains unknown. Manual/auto/preset GPU tuning is unsupported
in the discovery logs. `IsAtFactory=false` alone identifies neither an applied
tuning value nor an available supported setter.

The retained evidence supplies no useful live power, queue-priority, memory
partition or firmware change. The WDDM getter candidate is diagnostic work only.
Its source and API review must preserve that distinction before any separate
root-owned availability or benchmark run.
