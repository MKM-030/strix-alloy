# Windows fabric-clock support audit — 5 October 2026

**No supported Windows route to observe and hold the required FCLK at its top
level is qualified for this Ryzen AI Max+ 395 / Radeon 8060S host.** The reviewed
interfaces supply specific negative evidence, rather than a reason to try a
setter. This is a source/documentation disposition, not proof that every OEM or
future interface is incapable. GPU/NPU overlap qualification remains false.

The author read retained reports/JSON and official upstream documentation/source.
No process, native API, provider or hardware probe, build, installation, setting,
model payload or measurement was performed. The supplied stock server identity
(PID 24904; controller run `370cc96915474e509d12e7329b44f0e7`) was not inspected or
modified. Retained host inventory names BOSGAME LIMITED / BeyondMax Series,
BIOS 3.10, graphics driver `32.0.32015.2008` and NPU driver `32.0.20102.3930`;
these are prior inventory values, not a fresh readback.

## What the requirement actually tests

Pinned Halogen 0.16.2
[FLAGS](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L172-L179)
requires the GPU fabric clock held at its top level and explicitly treats
`HALOGEN_NPU_WITH_GPU=1` as unsupported. Its
[host helper](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/deploy/host/halogen-fabric-clock#L14-L41)
uses Linux AMDGPU `power_dpm_force_performance_level` plus `pp_dpm_fclk`.
Readback accepts `high`, or `manual` with exactly one selected state and that state
the top FCLK entry. A GPU, memory, SOC or NPU frequency sample does not satisfy
this contract. No numeric conversion between these domains is assumed.

## Concrete Windows and WSL candidates

| Candidate | Authoritative/retained disposition |
| --- | --- |
| Existing native WDDM getter | The [retained acquisition](halogen-wddm-collector-compile-plan-20261005.md) qualified node/adapter buffers, identity and close. Its engine/memory clocks expose no FCLK selection or hold readback; it contains no hold setter. |
| ADLX 1.5 on this host | [Retained capability receipt](halogen-adlx-20261004.md) reports success/false for all six queried GPU tuning domains. [System-power receipt](halogen-windows-power-readback-20261005.md) reports SmartShift=false and PowerDistribution=false; SmartShiftMax support failed and remains unknown. These do not qualify FCLK control. |
| Current AMD SMI native route | [AMD SMI installation support](https://rocm.docs.amd.com/projects/amdsmi/en/latest/install/install.html#supported-platforms) targets Linux GPU platforms and the AMDGPU kernel driver. Linux sysfs controls cannot be transplanted into WSL. |
| New AMD SMI WSL route | The official [experimental WSL backend](https://rocm.docs.amd.com/projects/amdsmi/en/develop/how-to/amdsmi-wsl-mode.html) exists, is opt-in/off by default, and states fabric features are unavailable. The exact clock/control dispatch below independently closes this candidate. |
| Windows XRT-SMI | AMD's [NPU Management Interface](https://ryzenai.docs.amd.com/en/main/xrt_smi.html#xrt-smi-configure), updated 28 September 2026, defines `configure --pmode` as NPU performance policy. `examine --report platform` reads NPU mode/power. Neither documents holding or observing the GPU's FCLK. NPU performance/turbo is not a fabric-hold contract. |
| Ryzen Master fabric controls | AMD documents [DF PState fabric telemetry](https://docs.amd.com/r/en-US/68886-ryzen-master-user-guide/DF-PState) and [fabric clock controls](https://docs.amd.com/r/en-US/68886-ryzen-master-user-guide/Clock-Control), but [supported platforms](https://docs.amd.com/r/en-US/68886-ryzen-master-user-guide/Supported-Platforms) are AM4, AM5 and SP6. AMD's [395 specification](https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-max-plus-395.html) names FP11. Desktop form factor alone does not qualify Ryzen Master or an OEM SDK on this host. |

The newer AMD SMI WSL backend matters: an unqualified blanket claim that AMD SMI
has no WSL backend would be stale. Its exact source path is:

1. `amdsmi_get_clock_info(handle, AMDSMI_CLK_TYPE_DF, &info)` dispatches to
   `WSLGPUBackend::GetClockInfo` in
   [amd_smi.cc](https://github.com/ROCm/rocm-systems/blob/develop/projects/amdsmi/src/amd_smi/amd_smi.cc).
2. [WSLGPUBackend](https://github.com/ROCm/rocm-systems/blob/develop/projects/amdsmi/src/amd_smi/amd_smi_wsl_device.cc)
   calls `rocdxg_smi_get_clock_info` with the same clock enum.
3. The [ROCDXG implementation](https://github.com/ROCm/rocm-systems/blob/develop/projects/rocr-runtime/libhsakmt/src/dxg/rocdxg_smi.cpp)
   accepts only clock types 0 (GFX/SYS), 3 (SOC) and 4 (MEM); every other type
   returns `HSAKMT_STATUS_NOT_SUPPORTED`. DF is enum 1 in the
   [official header](https://github.com/ROCm/rocm-systems/blob/develop/projects/amdsmi/include/amd_smi/amdsmi.h).
   The backend maps that status to `AMDSMI_STATUS_NOT_SUPPORTED`. No live
   availability call is needed to learn this source-defined result.
4. `amdsmi_set_clk_freq` and `amdsmi_set_gpu_perf_level` use `rsmi_wrapper`;
   that wrapper returns `AMDSMI_STATUS_NOT_SUPPORTED` for an attached WSL
   backend. Thus the experimental backend supplies neither the required DF
   observation nor its hold setter.

These current `develop` references are mutable source checked on this date;
they are not pins for the installed vendor library. No private PMLog, SMU,
driver escape, replacement DLL or speculative frequency mapping is proposed.

## Vendor contract qualification gate

The remaining missing evidence is a **vendor contract**, not another GPU/NPU
workload or a repeat of the same getters: an official BOSGAME firmware/manual or
AMD Windows SDK support specification for an explicitly supported FCLK hold and
readback on the retained BOSGAME BeyondMax / BIOS 3.10 identity.
To qualify a candidate it must name FP11/395 support, the callable support/query
entry points, what top-state/held readback means, and how the hold is released.
No such contract was found in the reviewed primary sources. Until one is
available, preserve serialization and the running stock server; performance
buttons, Windows MaxPerformance, NPU turbo and a current clock maximum cannot
substitute for the missing fabric proof. Do not contact vendors without direct
user authorization.

[Retained OEM inventory](halogen-update-gpu-scout-20261004.json),
[NPU producer gate](halogen-npu-early-token-producer-20261005.md).

## Bounded OEM / retained ROCr addendum — 5 October 2026

The bounded official-documentation search is complete. Official-domain searches
for BOSGAME BIOS 3.10, M5 BIOS fabric, Strix Halo FCLK Windows SDK, and FP11 fabric
clock SDK returned no explicit qualifying contract. Following the M5 page's
support links reached the public download center, driver page, FAQ and BIOS
download table. This is a scoped negative finding; it does not establish that
unpublished OEM documentation or another interface cannot exist.

| Evidence | Exact consequence |
| --- | --- |
| BOSGAME's [M5 page](https://www.bosgamepc.com/en/products/bosgame-m5-ai-mini-desktop-ryzen-ai-max-395) identifies Ryzen AI Max+ 395 / Radeon 8060S and describes colored performance/noise modes. | Positive product/mode documentation, but no FCLK/DCLK readback, frequency hold, API or BIOS 3.10 semantics. The duplicated green-mode list also cannot establish an exact top-state policy. |
| The [download center](https://www.bosgame.com/pages/download-center) names M5; the [driver page](https://www.bosgamepc.com/en/pages/support) lists its AMD chipset package. | Positive download navigation, with no fabric support/query contract. No package was downloaded or installed. |
| The official [BIOS table](https://www.bosgamepc.com/en/pages/bios-download-center) lists BIOS/EC files for other models, including M1/M2, M3 and M4. | Its inspected table contains no M5/BeyondMax BIOS 3.10 entry or fabric-control manual. The M5 related-product card below the table is not a BIOS entry. |

Retained ROCr commit `2b22ab0195cc1461cd9abf3b969e9dd7c10af350`,
`libhsakmt/src/dxg/wddm/device.cpp`, calls `SetPowerOptimization(false)` between
`CreateDevice()` and `CreatePagingQueue()` (lines 90–92), then calls
`SetPowerOptimization(true)` before device destruction (lines 97–101). The method
returns `void` (line 342); lines 363–365 obtain the original escape's `NTSTATUS`,
debug-log it and free the buffer. The bounded search of retained WDDM C++/headers
and `librocdxg.h` found only those lifecycle/method occurrences and no documented
FCLK/DCLK guarantee, fabric support query or held top-state readback. See the
[operating-state source audit](halogen-operating-state-source-audit-20261005.md)
for its existing private-Wkmi/build limitations. This evidence does not establish
what the private request does to fabric policy. No escape was invoked or payload
reconstructed.

**Concrete blocker:** no reviewed AMD/OEM contract identifies FP11/395 support,
support/query entry points, FCLK/DCLK clock-domain identity, top-state held
readback semantics and release behavior under the existing BIOS/drivers. The
source call and OEM mode descriptions cannot fill those missing facts. No
hardware action or overlap qualification follows from this addendum; the stock
server remains untouched.
