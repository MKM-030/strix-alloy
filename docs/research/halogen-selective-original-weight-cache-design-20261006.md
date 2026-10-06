# Selective original-weight GPU cache: conditional design, 2026-10-06

This source-supported design retains the prepared BF16 weight for one ordinary
Prefill projection. It is conditional on the completed, exact-output component
comparison showing enough benefit to justify a serving experiment. No adapter,
script, profile, running process or frozen replay input was changed for this
note. It authorizes neither implementation nor hardware work. Serving gain is
unknown.

The intended outcome is higher measured Prefill throughput while preserving
Decode, output correctness and native accepted/drafted counts. A component
millisecond difference is not a measured token rate. The design does not imply
a Decode or acceptance improvement.

## Source and call pins

The pristine Halogen 0.16.2 executable is 26,052,768 bytes, SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The retained host disassembly SHA-256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
These are source identities, not a fresh live-process receipt.

| Bound routine or window | Half-open RVA extent | File offset / bytes | SHA-256 |
|---|---|---|---|
| FC dispatcher | `[178cf90,178efa7)` | `178bf90` / 8215 | `f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9` |
| Packed helper | `[17f8280,17f8de1)` | `17f7280` / 2913 | `0624974055273bd4dee85357d971b3a4b32930d96c03bcd833b0fd2d860e48f3` |
| Original preparation | `[17ec6e0,17ecede)` | `17eb6e0` / 2046 | `34bb1998a74e03c63c714ea1e43d505eb88e59ff1c6266f39ba997a6f174d12d` |
| BF16 library wrapper | `[18c6b80,18c6be6)` | `18c5b80` / 102 | `6336433c1a337ff1faf7f72767ea869bfab343355ce74130226bd0ba76651a7d` |
| Direct-original call window | `[17f860a,17f869b)` | `17f760a` / 145 | `2412026d0faf8a8a9854cd006715567d58998b465442d014df823e47be6e8789` |

The 145-byte window hash was obtained by a bounded read of the pristine local
executable. The routine hashes and caller bindings are recorded in
[the independent capture audit](halogen-prefill-ht-independent-audit-20261006.md)
and [the completed stock-route audit](halogen-prefill-ht-stock-route-20261006.md).

The selected projection is
`layers.0.linear_attn.in_proj_qkv.weight`, logical `M8192/N10240/K2560`,
store16, variant `0x1208` (4616 decimal), descriptor mode4, BF16 output.
The required source edges are:

- Ordinary QKV: `17913fb -> 178cf90`, return `1791400`.
- FC to packed helper: `178cfbb -> 17f8280`, return `178cfc0`.
- Original preparation: `17f865c -> 17ec6e0`, return `17f8661`;
  pristine call bytes `e8 7f 40 ff ff`.
- Direct-original library multiply: `17f8696 -> 18c6b80`, return `17f869b`;
  pristine call bytes `e8 e5 e4 0c 00`.

The completed capture binds original preparation, original X and Y, one
default-stream library submission and exact source allocation snapshots for
this route. Its observer work is not a speed measurement.

## One callsite shim, with an explicit assembly review prerequisite

The narrow proposed implementation patches only the five-byte preparation
call at `17f865c`, behind a new default-off mode in the existing adapter family.
It leaves the original library multiply untouched. Global FC, packed-helper,
HIP launch and hipblasLt hooks are unnecessary for this design.

At the pinned preparation edge, `RBX` is the descriptor D, `EBP` is M, and the
seventh stack argument is original scratch W. `R12` is also W. An explicit
assembly relay can copy this context into its own correctly aligned call frame,
invoke a C prepare-and-choose wrapper, receive the chosen W pointer in `RAX`,
write it to the caller's local `R12`, and return to `17f8661`. It must not rely
on reading `RBX` or `RBP` from compiler-generated C after an unknown prologue.

This deliberately changes the pinned caller's local register state; it is not
a conventional ABI-preserving function-entry replacement. The source then
calls `18d3870`, retains R12 under the ordinary ABI, and executes
`mov rsi,r12` at `17f8689` before its unchanged library call. At the common
packed epilogue, `17f8b50..17f8b61` restores the outer caller's saved R12.
The replacement does not change X, Y, dimensions, router, plan selection,
library workspace or the output/result path.

Caller checks can use the pinned frames rather than generic hooks. If S is
the relay's incoming stack pointer, `[S]` must be `base+17f8661`. The packed
frame uses six pushes plus `sub rsp,0xe8`, so `[S+0x120]` must be
`base+178cfc0`. Only after that check, the FC frame's six pushes plus
`sub rsp,0x48` make `[S+0x1a0]` the ordinary QKV return, which must be
`base+1791400`. These offsets are derived from the retained source, not yet
verified by a runtime candidate.

Before implementation or activation, an independent review must verify the
assembly frame, argument widths, seventh-argument placement, stack alignment,
caller reads, intentional R12 change, errno/result behavior and all fallback
paths. Installation must verify the pristine live bytes and complete pinned
source ranges before modifying the call, prove the relative relay distance,
and use the existing controlled startup/lifecycle. It must not patch a live
serving instance.

## First miss and immutable hit contract

Prepared W needs exactly `10240 * 2560 * 2 = 52,428,800` bytes (50 MiB).
On the first admitted match, allocate one owned GPU buffer and call the
unchanged original preparation directly into it. No device-to-device copy
from engine scratch is needed. Prove its submission and completion once before
publishing the entry. Include allocation, preparation, completion and binding
cost in the first-miss result; excluded component setup is not a free serving
operation.

Admission binds the actual descriptor pointer and all 120 bytes of its fixed
prefix, the exact diagnostic name and pointer, shape/mode, and equality of
preparation arguments with descriptor packed/signs/scales fields
`+30/+38/+40`. The selected source allocations must cover packed
13,107,200 bytes, signs 5120 bytes and scales 20,480 bytes. Bind the allocation
identities, device, model/checkpoint/index identities and an exclusive,
immutable single-engine model lifetime. Pointer equality alone does not permit
pointer reuse or model reload.

Descriptor matching alone is insufficient. Original preparation reads layout
control u32 `18dcf70`, option bytes `18dcf80` and `18dcf90`, and lazy
initialization flags `18dcf78`, `18dcf88` and `18dcf98`. Snapshot their
initialized values after the first original preparation and require them to
remain unchanged. Bind the original direct-route globals and scratch/router
identities without changing dispatch or cache policy.

A hit returns resident W only on a complete match. A changed descriptor,
control, source allocation or lifecycle retires the entry for that process
and forwards original preparation into original scratch. An ordinary
nonmatching layer simply forwards stock and never adopts the selected entry.
Unqualified failures must not publish or substitute an incomplete buffer.

Hot hits should have no allocation queries, `/proc/maps` scans,
synchronization, copies, logging or general library interposition. Necessary
first-binding checks and immutable-lifetime proof belong at completed
boundaries. Thread-safety and retirement must preserve the buffer until all
queued consumers finish; initial implementation must retain the existing
exclusive measurement ownership.

## Lifetime and memory

The 50 MiB allocation is additional GPU-accessible memory. It does not remove
the original packed tensor: Decode still needs that representation. Keep
`HALOGEN_PREFILL_KEEP_TRUNK` absent/zero and `18dcf41=0`; the selective shim
does not alter the native HT threshold or populate the whole-engine cache.

The entry must survive every queued library use. Explicit release requires a
quiescent lifecycle boundary, completed GPU work, then `hipFree` of only the
owned buffer and a cleanup receipt. An arbitrary preload destructor cannot
be assumed to run before HIP teardown. Until an explicit release contract is
reviewed, the cache's maximum lifetime is the verified engine process, with
resource recovery proved at its owned normal termination/reap. It cannot be
shared across engine runs or silently survive reload.

The existing physical/commit reserve and startup admission remain unchanged:
18 GiB continuously, 22 GiB for a new request/component, and context262144
startup with at least 44 GiB physical and 131 GiB commit, stable for 60 seconds
within the existing deadline. A small additional allocation does not authorize
relaxing those limits. Root remains the sole hardware owner and must restore
the normal server ready and open after an admitted serving experiment.

## Original whole-cache audit remains separate

The earlier source audit found `180c4e0` to be packed-pointer-to-prepared-W
lookup only. With `KEEP_TRUNK=1`, startup `176e490..176e6ea` prepares and
retains the eligible trunk vector and changes the default native HT M
threshold from 1280 to 192. Map destructor `185a450` visibly frees host nodes
and buckets; that audit did not establish GPU-value eviction or request-level
release. This remains evidence about the existing process-scoped whole cache,
not an implementation of this selective entry.

The completed whole-cache serving regression in
[the upgrade benchmark](../benchmarks/halogen0162-upgrade-20261003.md)
does not test selective 50 MiB retention. Its results must remain reported
separately; they neither qualify this design nor justify repeating that
rejected whole-cache cohort.

## Device assessment and conditional serving return

**GPU:** this keeps original arithmetic and the original library GEMM while
removing repeated preparation for one admitted projection. It is a plausible
Prefill mechanism, pending exact component output and cost evidence.

**CPU:** it can manage the binding, metadata and lifetime. The hot comparison
must remain small enough that its own overhead does not consume the saved
preparation cost.

**NPU:** this cache needs no alternative arithmetic. The NPU's small internal
SRAM does not supply this 50 MiB GPU buffer, and shared DDR does not add memory
capacity. There is no useful NPU contribution to this particular design.

For a first request with r matching full 8192-token chunks, stock pays r
preparations. The proposed cache pays one preparation plus allocation,
completion and r wrapper costs. Cold savings therefore require the avoided
`r-1` preparations to exceed those costs. An 8K first request has only one
selected operation and can lose; 16K can reuse once; long inputs can reuse
across more full chunks. A smaller final chunk remains outside this exact
shape contract. Later requests can hit immediately, but resident-memory and
cache-pressure effects can still erase an engine benefit.

The measured component advantage would bound savings for this one layer-0
projection. It must not be generalized to all layers, shapes, context lengths
or token rates. A complete exact component result and plausible request-level
return must precede any implementation or hardware integration. If those
conditions are met, the next evidence is an admitted frozen serving comparison
reporting actual Prefill tok/s, Decode tok/s, output hashes and native
accepted/drafted counts, with first-miss and steady hits distinguished.
Acceptance preservation remains an expectation until that comparison; an
increase is not a consequence of caching original weights.
