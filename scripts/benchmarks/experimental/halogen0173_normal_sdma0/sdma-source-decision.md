# Normal Halogen 0.17.3: SDMA source scope

Recommend one bounded whole-engine `HSA_ENABLE_SDMA=1 → 0 → 1` cohort on the actual normal 0.17.3 profile. Keep the candidate off unless that cohort establishes a repeatable, clock-qualified improvement with unchanged output and acceptance. The supported configuration path and the DXG SDMA worker handoff exist. Their net removable cost has not been measured; neither the earlier scalar wait nor the remaining HIP host intervals predict a speedup.

This is a source and retained-evidence decision, authored 2026-10-09. No build, GPU work, service lifecycle action, request, or production change was performed for this audit. Its only new files are this document and `refs.json`.

## Current runtime contract and provenance

The retained normal service manifest `bacaffddb3a44d90bbda464ee46a6a95` identifies Halogen 0.17.3 image `ghcr.io/peonist-ai/halogen-flash-server@sha256:3bca0132db3c859c997d52d148e6ea4b7b497b8a695c5ccab97135193fde592a`, `HSA_ENABLE_SDMA=1`, and `HSA_ENABLE_DXG_DETECTION=1`. Its normal preloads are `/candidate/libhalogen0173-v2-preflight.so:/candidate/hip-register-private-rw.so`; there is no BN64 candidate in this profile. `runner.py:281` supplies the explicit SDMA1 default. `service.py:377` passes manifest environment entries to Docker, and lines 390–392 verify them against the container. A candidate environment override has a direct path without rebuilding ROCr or changing a copy-site adapter. The flag must be set before starting a fresh engine/runtime; do not assume editing an already initialized process changes its blit selection.

The actual 0.17.3 image's retained OCI configuration history explicitly installs `rocm[libraries]==7.14.0` and `rocm-sdk-device-gfx1151==7.14.0` from AMD's `whl-multi-arch` index. The retained SDK source audit maps SDK 7.14.0 / TheRock `418cd5f63abb7a604bad5874cd7b2e29334e640f` / ROCr 1.21.0 to `ROCm/rocm-systems` commit `2b22ab0195cc1461cd9abf3b969e9dd7c10af350`. Both ROCr and HIP/ROCclr analysis below use that commit.

The 0.17.3 SDK layer digest differs from the retained 0.17.2 layer digest, so image version alone did not establish byte identity. Root subsequently retained a read-only scan of the actual normal `flash_serve` PID87 mappings in `normal-sdma0-comparison-20261009/current-mapped-runtime.json`: mapped HSA is 4,887,129 bytes, SHA256 `1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5`, and mapped HIP is 28,933,697 bytes, SHA256 `6f3c9fe6b655a611e04a9a5a157cb46c425717e2873973f11a67bb6bbf6587b5`. These independently measured current hashes match the retained SDK/source pins. The HSA ELF contains the SDMA flag string; HIP need not parse that ROCr flag itself. No runtime import was used. An initial executable-suffix filter found no rows and was corrected to a generic map scan; the retained baseline receipt closes that preparation limitation. Keep these runtime identities identical across all three windows.

## What the flag changes on DXG

Pinned `flag.h:111–120` parses explicit `0` as SDMA_DISABLE and also disables SDMA gang. `amd_gpu_agent.cpp:917–966` makes that user setting override architecture defaults and instantiate `BlitKernel` for affected copies. H2D uses a dedicated compute blit queue and D2H shares the utility compute queue (905–908). Normal resource creation failures throw an error; the pending-copy-status placeholder is not the ordinary execution path. Explicit engine-copy callers are covered too: `DmaCopyOnEngine` redirects global SDMA_DISABLE to `BlitDevToDev` at 1278–1285.

With SDMA1 and DXG on gfx11, `CreateBlitSdma` selects **BlitSdmaV4** (804–855), rather than assuming a bare-metal V5/V6 path. Its source comment describes driver GCR wrapping and submission into another queue. `libhsakmt/src/dxg/wddm/queue.cpp:1039–1094` consumes pending write-pointer work on an SDMA host worker, host-waits leading dependency-signal polls in BLOCKED state, clears those poll packets, prepares the packet, and submits it. `Submit` also waits the paging fence and invokes HwsSubmit/SwsSubmit (1151–1158).

SDMA0 removes that SDMA-specific path for copies reaching ROCr. It replaces it with compute queue dispatch, barriers, shader work, and cache/fence cost. DXG compute submission itself also has a worker/driver path. There is therefore a concrete bypassable SDMA operation, but no source proof that the alternative is faster. Bulk weight upload during startup and any affected large transfer can regress; compute blits can contend with engine kernels.

Copy scope is broader than the previous four-byte scalar site. CPU↔GPU copies reaching ROCr use the host-facing blit objects. Ordinary same-GPU async copies below the default `HSA_FORCE_SDMA_SIZE` of **1 MiB** can select the potentially SDMA D2H blit to avoid cache flushes (`GetBlitObject:3324–3333`; `flag.h:227–228`); larger ordinary same-GPU copies select compute. Synchronous ROCr `DmaCopy` uses the compute D2D blit. Engine-targeted calls and ROCclr's own routing complicate this, so neither “all D2D changes” nor “all D2D is unaffected” is correct.

HIP/ROCclr can already choose shader copies for small sizes or memory/preferences, or host copies for direct-access memory. Retained `rocblit.cpp` selects these alternatives before ROCr, queries/assigns copy engines, then calls either the regular or engine-specific async copy API (470–594, 2126 onward, 2260 onward, 2690–2709). Actual `sdmaCopyThreshold_` and per-call memory residency/engine assignment were not established here. A HIP API direction and byte count do **not** prove that a call currently uses SDMA.

## Ordering and lifetime

This flag does not turn synchronous HIP calls into asynchronous calls or shorten the caller's required source lifetime. `hip_memory.cpp` keeps its common enqueue plus `finishCommand` for non-host-async copies; public `hipMemcpy` and `hipMemcpyAsync` still pass their respective synchronization mode. ROCclr's blocking D2H path also performs an upstream wait before ROCr dispatch (`rocblit.cpp:654–663`); SDMA0 alone does not remove that wait.

The selected compute blit retains all supplied dependency signals as barrier-and packets, propagates the original output signal into the dispatch, and uses system acquire/release fence scopes (`amd_blit_kernel.cpp:643–711`, 779–784, 872–875). Its synchronous entry waits with acquire semantics (611–640). The bytes, dependent ordering, and completion contract are supported by source; whole-engine parity is still required because this globally changes scheduling and resource use.

## Retained cost evidence and prior-trial nonoverlap

The closest host census is **0.17.2**, one diagnostic request lasting 9,555.117690 ms after a separate warmup. It contains 112,040 valid records, without footer/loss counters that would establish capture completeness. Its observed copy directions are 301 H2D calls / 21,507,176 API argument bytes / 6,216.734394 ms inclusive host time; 230 D2H / 22,916 bytes / 161.047203 ms; and 1,062 D2D / 237,379,152 bytes / 15.761737 ms.

| Observed group | Calls | Inclusive host interval sum, ms |
| --- | ---: | ---: |
| H2D 4 B, synchronous, RVA 0x17b91be | 13 | 6,204.254343 |
| D2H 384 B, synchronous | 56 | 67.701380 |
| D2H 4 B, synchronous | 113 | 56.259020 |
| D2H 12 B, synchronous | 56 | 34.155102 |
| H2D 16 B, synchronous | 1 | 4.500018 |
| H2D 12 B, asynchronous, largest such group | 56 | 3.301609 |
| H2D 7,680 B, asynchronous | 56 | 3.218744 |
| D2D 20,480 B, asynchronous | 57 | 4.034947 |
| D2D 768 B, asynchronous, one site | 56 | 3.534553 |

Additional D2D groups include 256 B × 164, 512 B × 193, 768 B × 241, and 184,320 B × 57. The 8 MiB × 26 group should already use compute under ordinary ROCr routing, but the census does not record engine IDs. There is also a 20 MiB H2D asynchronous call whose 0.017171 ms interval is enqueue time, not device transfer time.

The 6,204.254343 ms scalar interval includes earlier GPU work waiting to complete. It is **not removable transport time**. Other H2D intervals total 12.480051 ms; all remaining copy intervals total 189.288991 ms. These are inclusive API intervals containing waits and overlapping device activity, not an SDMA savings budget. The census motivates frequent small-copy exposure, but it neither establishes current 0.17.3 active SDMA coverage nor measures its worker overhead. No tok/s forecast is justified.

The rejected 0.17.2 scalar-async experiment replaced only the guarded 4 B H2D call with a D32 asynchronous value fill on the explicit legacy queue. It had 52 successful enqueue records totaling 0.087949 ms across four requests, exact greedy output and combined acceptance parity, and no repeatable qualified prefill/decode gain. Its incompatible candidate clocks further limit phase-rate interpretation. SDMA0 retains synchronous HIP semantics and changes transport selection globally; it does not repeat that hook or its hypothesis.

The retained-record searches found no exact SDMA0 candidate/cohort. Public retained benchmark manifests that record this flag all use SDMA1 (natural-long 0.16.2; arena16384, draft-vocab-q8-terminal, and stock-adaptive 0.17.2). This is “no retained exact trial found,” not a claim that nobody has ever tested the flag.

## Minimal bounded experiment

Root owns all implementation, lifecycle, hardware, requests, and measurements. Use the existing frozen workload and unchanged normal 0.17.3 image, model, libraries, preloads, memory policy, context/slots, MTP2, PLD3,3, and native greedy path. Make a default-off candidate manifest override that changes **only** `HSA_ENABLE_SDMA` to `0`; preserve DXG1, AMD_SERIALIZE settings, prompt cache, and all other controls.

Run normal SDMA1-before, candidate SDMA0, then restored SDMA1-after. Each window contains one excluded warmup and three measurements: frozen synthetic pseudoprose calibrated to 8,192 input tokens, 128 normal generated tokens, temperature0, seed1, thinking off, cache off. Retain exact requests, current runtime/file/environment identity, raw phase_ms, raw API rates, request wall times, guest RAW/Windows-QPC clock qualification, and output hashes. Compare both stock windows and sample spread, not only a favorable mean. Combined API MTP/PLD draft counters must not be mislabeled as separate native MTP acceptance; retain available native and combined counters distinctly.

Preserve all existing startup and memory floors and watchdogs. Record startup/load time separately because SDMA0 also affects weight uploads and the 64 GiB hybrid copy path. Stop on startup, memory, copy/runtime, output, or acceptance failure; restore the visible normal SDMA1 server. A material clock mismatch makes phase speed claims unqualified; preserve raw numbers and wall results rather than applying a correction as measured phase speed. Do not add a sweep, a new instrumentation cohort, BN64, resolver work, scalar-async replay, or a new copy-site adapter.

If output/counter parity or reliable net improvement is absent, leave SDMA0 off and close this candidate. A clock-qualified cohort can determine net benefit; the source/census evidence alone cannot.
