# NPU re-evaluation: compressed native MTP vocabulary projection

**Status:** source-feasible candidate; no justified hardware or serving implementation now.

**Date:** 2026-10-08.

**Scope:** independent CPU-only reads of retained reports, source, and bounded disassembly of the inert current ELF. Only this decision file was created. No hardware, timings, benchmarks, tests, installations, WSL commands, serving/lifecycle operations, profile changes, continuation edits, or model-weight payload reads occurred.

## Decision

A distinct mechanism is **low-rank representation of the actual native MTP vocabulary rows**, evaluated by two small dense NPU projections. It would approximate proposal logits and leave the target verifier authoritative. It is different from E/H projection replacement, token embedding reuse, ready64, a new autoregressive 0.8B model, and the previously proposed untrained token-only parallel student. It does not require a new language model or pretend that target weights can be arbitrarily split into a complete drafter. It requires a new derived factor asset and accuracy evaluation, whose results are not available.

The native 0.17.2 insertion locations can be made concrete. The decisive negative is readiness: the vocabulary query is already on the GPU at the last MTP stage, with **no established positive lead** before the projection consumer. A smaller matrix does not hide GPU capture, Windows/WSL scheduling, NPU dispatch, result transport, upload, or native selection. Stock already projects a reduced Q4 vocabulary, so a full-vocabulary baseline would exaggerate removable work. There is no retained current-version isolated reduced-head budget or complete cost result establishing a margin for this route.

Do not implement a live NPU shim or schedule a hardware run on this assessment. The useful delivered result is the exact current proposal/verification binding below and a complete cost model for a genuinely different representation. The next action is conditional asset design described at the end, rather than another defeated-consumer diagnostic.

## Evidence that changes the starting point

- Current independent PLE inputs are no longer a 25-second-only path. The actual archived second-chunk v5 worker took 0.859 s through its sampled ready boundary and saved raw FP8, original-order IDs, BF16, and FLOAT. This is archived CPU preparation, not a live publication lead or native input comparison. The preceding actual observer recorded 17.520212 ms for small token publication and 14,708.678294 ms from publication to the second key; most native lookup was already overlapped. These facts cannot be used as decode drafter lead.
- The actual full M8192 PLE NPU call returned in 203 ms and passed its development tolerance, with 88,572,989 key/value BF16 words differing from the native reference. It supplies neither speculative token IDs nor permission to approximate ordinary target prefill: target verification of future draft IDs does not correct changed prompt state.
- The mixed embedding component's 0.2–17.6 microsecond case-mean branch margins are retired. The 0.8B independent proposer required 45.22 ms for three predictions, 22.46 ms per append, and 418.29 ms per 512-ID rebuild; its 47.73% offline prefix match is not native acceptance. Neither is reopened here.
- The current reduced-head default already exists: absent/empty `HALOGEN_DRAFT_VOCAB` selects adaptive groups, and the image supplies `draft-vocab.lists`. English has 48,082 selected rows, rather than all 248,320. The Q8 experiment descriptively regressed from 42.75 to 40.41 decode tok/s and from 61.95% to 60.00% combined acceptance; its after bookend is missing. This rejects a gain claim for that experiment, not every compressed representation.

Sources: [current PLE status](C:/Projects/strix-alloy-clean/docs/research/halogen0172-prefill-overlap-20261008.md), [PLE component](C:/Projects/strix-alloy-clean/docs/research/halogen-ple-npu-component-20261008.md), [mixed embedding result](C:/Projects/strix-alloy-clean/docs/research/halogen-npu-pld-mixed-embedding-result-20261007.md), [independent proposer](C:/Projects/strix-alloy-clean/docs/research/halogen-npu-independent-proposer-screen-20261006.md), [Q8 terminal report](C:/Projects/strix-alloy-clean/docs/benchmarks/halogen0172-draft-vocab-q8-terminal-20261008.md), [current reduced-head audit](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/draft-vocab-candidate-20261008/draft-vocab-candidate.md).

## Exact native 0.17.2 token consumer

The reviewed data file is `PREP/runtime-inventory/static-audit-data/usr/local/bin/flash_serve.data`, 26,178,504 bytes, with existing receipt SHA256 `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`. Its `.text` VA minus file offset is 0x1000. This review used ordinary ELF section parsing and the already present `C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin/llvm-objdump.exe` against that inert file. The following locations were found from actual current instructions and connected data flow, **not by rebasing the old 0.16.2 addresses**. Existing file pins are provenance; a new full-file rehash was not performed.

| Current location | Static contract |
| --- | --- |
| `0x173ea9b..0x173eb0b` | Existing PLD allowance and context eligibility. Model position is `model+0x2e0`, capacity bound uses `model+0x110`; request width is `+0x190`, context begin/end are `+0x198/+0x1a0`. Request sampler `+0x168` and PLD suppression `+0x1f0` bypass lookup. |
| `0x173ef7c..0x173f082` | Hash-table search using request `+0x1b0/+0x1b8/+0x1c0/+0x1c8`. A node's continuation index is signed int32 at node `+0x10`. Lookup miss returns to `0x173eb11`, which supplies no PLD block. |
| `0x173f082..0x173f144`, vector sibling `0x17400a8..0x17400f9` | `RBX=min(available suffix,native allowance)`. Both copy paths place host int32 IDs at the **original** `RSP+0x6a0`. |
| **`0x17400ff`** | Exact hit-only join before native constraints/opening check. `RBX` is stock count; request pointer is at original `RSP+0x10`. The block loads constraint field `request+0x218`, stores its address at stack `+0x18`, then tests it. Null constraints pass count through `R13D=EBX` at `0x17401ce` to `0x173eb24`. This is an interior machine-state seam, not an exported callback. |
| `0x173eb62..0x173eb79`; missing-head sibling `0x173f149..0x173f16f` | Cached opening ID is request `+0x178`, current token `+0x174`, model pointer `+0xf0`. Missing opening calls native MTP wrapper `0x17f7790`. The first PLD ID must equal the native opening; mismatch follows native fallback. |
| **`0x173ebd0 -> 0x17f7980`** | Copies `[current, drafts...]` to stack `+0xa00`; verifier call receives `RDI=model`, `RSI=inputs`, `EDX=n+1`. Verifier sets model byte zero to 1, calls Target `0x17f79f0` with `ECX=-1`, then clears the flag. It requires positive count, enabled MTP, count within model `+0x14`, nonzero position, and zero model `+0x15c`. |
| `0x173ebe0..0x173ec32` | Consecutive comparison of draft IDs with target `model+0x20[a]`. Builds accepted drafts plus authoritative correction/bonus at stack `+0x380`. |
| **`0x173ec40 -> 0x17f9c00`** | Calls native accepted-prefix commit with model and `a+1` count. Subsequent native output loop and PLD append at `0x173ed40 -> 0x176eaa0` remain. Native stop/error branches can bypass ordinary continuation. |

At the copy join, incoming paths observed in these bounded windows are `ja 0x17400ff` at `0x173f0fb`, `jmp 0x17400ff` at `0x173f144`, and the vector-copy fallthrough. This is not an exhaustive computed-edge, register-liveness, trampoline, or lifecycle proof.

A token-only future producer can consume through this hit-only seam while preserving constraints, opening, verifier, commit, output and replay. Start without constraints and cap at `min(stock_n,3,native_allowance)`; misses cannot obtain proposals here. The allowance in the inspected current code is the minimum of model verification capacity minus one, request `+0x108`, and remaining model capacity; positive request `+0x200` additionally caps at that value minus one. Keep these native bounds rather than reconstructing them from an external frame.

The old offline [packet selector](C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_pld_proposal_wire.py) remains useful for owned IDs/identity but does not install this current ABI. Its local lock does not synchronize native reset/destruction or cancellation. No live 0.17.2 external outcome callback, birth nonce, complete lifetime map, or no-hit splice is qualified by this read.

## New representation and exact computation hook

For the pooled learned vocabulary rows `W` of width 2560, derive `W approximately V U`, with `U` shaped `[r,2560]` and `V` shaped `[pooled_rows,r]`. For native final MTP query `x`, compute `z=U x` and the selected group's approximate logits `V_group z`. Retain the image's group/token mapping. This uses real output-head rows; input embeddings and the PLE ngram table are different weights and cannot substitute for them. Fit/quantize the factors offline; do not claim a rank, factor precision, or source reconstruction is already qualified.

This operation is supported in principle by the dense BF16/FLOAT projections already executed by the installed NPU path. It requires a new graph/export and actual placement qualification; existing projection receipts do not establish execution of these new shapes. Constants can stream from DDR using supported tiling. No assumed extra SRAM or universal resident-weight capacity enters the design.

Illustrative rank64 geometry, **not timings or an accuracy result**:

| Scope | Factor elements / BF16 bytes | Dense reference arithmetic |
| --- | ---: | ---: |
| English group 48,082 rows | `(2560+48082)*64 = 3,241,088` / 6,482,176 B | 3,241,088 MACs versus 123,089,920 MACs for a dense 2560-wide group |
| Shared 198,759-row pool | `(2560+198759)*64 = 12,884,416` / 25,768,832 B | Static factor storage; group slicing and runtime allocation are additional |

Stock uses packed 3-/4-bit source dequantization and further Q4 draft-row repacking, not a dense BF16 baseline. The quoted MAC ratio is therefore not a predicted runtime speedup. Factors may be derived from the actual staging rows or exact reconstructed stock rows; their chosen oracle and rounding must be explicit. Rank error can worsen proposal quality, while removal of a repacking error might improve it; neither direction follows from source inspection.

**Exact current call:** at `0x17f1c68`, the MTP routine calls reduced-head consumer `0x17f2080` with `RDI=model`, `RSI=model[+0xd50]+(count-1)*5120`, and `EDX=position+count`. The query is a device pointer to the final 2560-word row. That call is followed by selection `0x17f2560` at `0x17f1c8d`, `hipDeviceSynchronize` at `0x17f1c92`, and a four-byte D2H chosen-ID copy at `0x17f1cbd`. The consumer chooses the current group and format, projects core/tail rows, and scatters reduced FLOAT logits into full output storage; native output pointer `model+0xd58` is passed to selection.

An initial representation substitute must supply complete selected FLOAT logits and preserve native full-buffer fill/scatter and selection semantics. That means roughly `4*group_rows` result bytes (192,328 B for English), plus capture/widening of the 5,120-byte query and GPU upload. Returning only a four-byte top ID would remove GPU selection, but changes the selection ABI and model fields; it is a separate, unqualified scope, particularly for constraints. The separate target forward uses the full head at `0x17f8906/0x17f891c` and must remain untouched.

**Readiness lead is zero in the inspected path.** The query follows a just-enqueued native kernel and cannot be read as authoritative host data at Target entry or from token IDs. Capturing it adds stream completion/readback before the Windows call. A token-derived early query surrogate would require a separately trained predictor and returns to the missing-student problem. It cannot inherit the PLE chunk lead.

## Accuracy and complete cost model

The numerical target is proposal utility, not strict E/H tensor parity. In an explicitly qualified greedy path, approximate draft logits can be tolerated because the unchanged full target verifies every proposed ID and commits its own correction/bonus. Exact final greedy output, stop/EOS, grammar, native caches/replay, and accepted-prefix state still require qualification. This does not establish a sampling-preserving acceptance/residual algorithm for non-greedy requests.

Score joint accepted-prefix survival and actual committed output tokens, not aggregate acceptance or factor reconstruction MSE alone. Native opening equality remains required for an external PLD feed. Replacing the MTP vocabulary projection itself also changes the cached native opening; preserving control-flow locations alone does not establish all adaptive/replay invariants. There is no guarantee of 100% acceptance.

For one projection opportunity define:

`A = query completion/capture + pack/widen + WSL->Windows IPC + NPU feed/dispatch/two projections/public return + Windows->WSL IPC + validate + GPU upload/scatter publication + any added host selection work`.

Include queue/scheduler tails, reusable-buffer ownership, no per-round process creation, failures/timeouts and discarded work. Initialization/export/compiler cache, steady-state private factors, provider allocations and startup must be amortized over the actual request. A native fallback must remain possible before any logits write; after partial publication, silently continuing stock is not a safe assumption.

With native removable projection work `G`, established lead `L=0`, and lookup/substitution cost `J`, equal-quality break-even requires `A+J < G`. No component in `A` is free because the payload is small. The retained 2.211–2.423 ms row-pipe exchange includes GPU acknowledgment/readback and does **not** measure this FLOAT-logit route; it is a warning about scope, not a lower bound or forecast. The retained 77–82 microsecond small native NPU calls disprove a universal 45-ms launch floor but do not price either factor projection or this IPC. The older 3.323555-ms complete MTP-head bracket is neither current reduced-vocabulary `G` nor removable trunk/replay work.

For a new complete request, the actual requirement is:

`sum(candidate round times)/candidate committed tokens < sum(stock round times)/stock committed tokens`.

Round times include retained head/trunk work, native lookup/opening, verifier width, commit/replay, lower accepted-prefix lengths, fallback, transport, NPU and shared-DDR/power contention. An overlapping token-only producer would additionally need actual ready-window coverage and supported GPU/NPU coexistence. The retained [Windows fabric audit](C:/Projects/strix-alloy-clean/docs/research/halogen-windows-fabric-support-20261005.md) supplies no supported hold/query/release contract; this review neither refreshes nor bypasses it. A deliberately serialized projection offers no overlap lead and must win its entire added latency.

## Implementable next step and disposition

The representation has a concrete CPU implementation path: a bounded converter over pinned current pooled output-head rows, blockwise factor fitting at explicitly chosen ranks, a manifest binding source type/group asset/token IDs/rounding, and a reference `U/V` projector. It must preserve the existing row mapping and use actual final-MTP queries for causal top-ID/prefix scoring. A source decomposition and a low matrix MSE alone are insufficient. No such factor asset or eligible final-query corpus was found in the reviewed retained work; the existing E/H fixtures are not that final projection query.

**That implementation is not justified now:** the current reduced-head removable budget and a complete serialized bridge advantage are absent, and no early input removes the round trip. Creating a converter, more protocol tests, a live hook, or another old component run would not itself resolve this negative cost case. If later independent evidence supplies a credible full-cost margin, the bounded converter/reference projector is the first useful implementation, before any native or NPU execution. For the earlier parallel token-only student, the current `0x17400ff` binding is reusable source evidence, but its trained asset, actual lead, coverage and lifecycle remain missing.

Retain stock 0.17.2. No new acceptance, Prefill tok/s, Decode tok/s, hardware-speed or serving-gain value follows from this decision.

Additional source paths: [native math delta](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/ple0172-math-delta-audit/source-audit.md), [Q8 source contract](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/draft-vocab-candidate-20261008/q8-implementation-plan.md), [earlier parallel-student disposition](C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/npu-draft-next-20261008/findings.md), [old token insertion audit](C:/Projects/strix-alloy-clean/docs/research/halogen-npu-native-pld-injection-scope-20261005.md), [old multistudent cost evidence](C:/Projects/strix-alloy-clean/docs/research/halogen-multi-draft-feasibility-20261006.md), [actual NPU/WSL handoff](C:/Projects/strix-alloy-clean/docs/research/halogen-npu-wsl-handoff-20261007.md).
