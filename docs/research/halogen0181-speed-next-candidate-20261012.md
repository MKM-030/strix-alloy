# Halogen 0.18.1: next native speed comparison, 12 October 2026

**The defensible supported candidate is the stock native compute update carried from 0.17.5 into 0.18.1, tested against a fresh matched 0.17.4 control. Keep fixed MTP2/PLD3,3 and the frozen natural16K request.** No extra configuration switch has cleared this review's novelty and benefit gate. This is an unmeasured version comparison, conditional on root's current-version source/clock/startup qualification, not a promised speed or acceptance increase.

The 0.17.5 changelog explicitly reports faster prompt reading and drafted decode with unchanged checkpoints and greedy output. The 0.18.1 changes describe schema sampling, retry, sessions, cache policy and scheduling. A lone Cache-Off greedy completion has no demonstrated benefit from those newer request-policy features. The one-request gateway also does not exercise concurrent scheduling. [Official changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/CHANGELOG.md).

The earlier 0.17.4 natural16K result at capacity262,144 and the 0.18.0 result at capacity32,768 do not constitute a matched version speed comparison. Their time/order, capacity and clock qualifications differ. The completed 0.18.0 fixed2/adaptive comparison only tests drafting policy within that version. [0.18.0 comparison](halogen0180-acceptance-comparison-20261011.md).

## What is new, and what is not proved

Root's extracted 0.18.1 engine is27,096,728 bytes, SHA256 `d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab`, from image `sha256:f0b39c8908f9897f27ab0a64e964c775e136a7cf7a1bafeb4de0c6d5d1e07e29`, revision `b540030f8abf`. The retained 0.18.0 engine is27,078,280 bytes, SHA256 `71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08`. These identity pins do not qualify execution.

A bounded CPU ELF/symbol walk compared the first embedded GPU code object in these exact files. Its file offset changes `0x53000` to `0x54000`. Of1,504 shared STT_FUNC symbols, **1,492 complete bodies are byte-identical**. Eleven changed bodies have sampler/acceptance/residual-sampling names; `k_mask_rows_f32` is added. One further apparent change, `k_gather_iq4nl`, is relocational as detailed below. This establishes a finite device-body comparison, not complete host-dispatch, descriptor, library or runtime equivalence. It does not prove that every unchanged kernel has the same launch schedule.

The complete HC6<3> body remains21,468 bytes with SHA256 `be571ef631410256670c079f0545e812123278cb2d33c2a8738c910d4b6d6206`. Therefore 0.18.1 supplies no new HC6 arithmetic body in this comparison. The old two-launch HC6 split still lacks a complete current fixture, valid removable-stall budget and complete-pair advantage. It remains a separate unsupported integration hypothesis, not this supported version candidate. [HC6 ROI audit](native-mtp-roi-20261010.md).

The [native phase/cost review](native-phase-cost-review-20261010.md) qualifies aggregate phase durations and counters but no current draft/verify/copy cost decomposition. Historical host synchronization intervals include queued compute; instrumented count-times-mean GPU rankings exceed request wall. Those figures cannot price a new configuration or be translated into native tok/s.

## Narrow IQ4NL gather closure

Exact device symbol:

`_ZN7halogen12_GLOBAL__N_114k_gather_iq4nlEPKhPKxPt`

Both bodies are1,104 bytes. Their hashes differ (`a58217e87d14e763ef5e47e0c5f7d60a979ab8d0619c78aac8c8bdb22a290f59` -> `973475fb684f1b859aedf4a7b2dfd35ea4e4b72637c731027a95dfec8bda6fd7`), but **only four bytes differ**, within two immediate words at body+`0x118` and+`0x358`. Bounded LLVM-MC decoding identifies both as literals used by `s_add_u32` immediately after `s_getpc_b64`. Both old addresses resolve to device RVA `0x213f40`; both new addresses resolve to `0x2142c0`. The64 bytes at those targets are identical, SHA256 `86dd83fcd81dad815115f2846939a56fee47022ed7418bdb7610e177fef0af5d`. All other1,096 body bytes agree. No new gather computation or timing advantage follows from this relocation.

Current host registration uses name RVA `0x2f187`, registration-name reference `0x194e24a` and handle `0x19d4840`. The inline handle reference at `0x18ca538` feeds `hipLaunchKernel` at `0x18ca54f`. A host stub references the same handle at `0x18cce0d`; a direct E8-call scan found no calls to its entry `0x18ccdb0`, without claiming an exhaustive indirect-call proof.

The inline selector at `0x18ca45f` reads model+`0x7b4`, decrements it and dispatches a four-entry table at `0x4760c`. Kind1 selects `0x18ca494`, the IQ4NL branch. Current loading at `0x1867a14..0x1867ae6` admits storage13 with160-wide,90-byte rows and sets kind1. Storage10 instead establishes160-byte rows, writes kind0, and reaches the default FP8 branch at `0x18ca7b8`. The retained native lookup validator explicitly pins storage10/rank3/dimensions128,2500012,160. The official v2 precision description likewise identifies its separate lookup table as FP8. [Precision specification](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/QUANT.md).

This is an IQ4NL **n-gram/PLE row gather**, not a generic token-embedding speed change. It can serve an IQ4NL lookup representation such as a GGUF-derived checkpoint, but the pinned native-v2 FP8 representation selects another branch. Changing that representation would change the frozen target and requires distinct qualification. No model/table payload was read for this closure.

## Why no extra switch is selected

The supported keep-trunk switch avoids repeated unpacking and costs about5.5 GiB; it changes the short-prompt route below roughly1,300 tokens. [Official flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md). The completed 0.16.2 screen matched cold outputs but regressed all six request-wall means, including MTP8K/16K by8.15%/5.83%. [Closure](../benchmarks/halogen0162-upgrade-20261003.md). This review found no new 0.18.1 path-specific preparation/retention mechanism that reverses that cost case. Keep-trunk is not reopened just because the binary version changed.

Similarly, the old fixed3 result lost to warmed fixed2, and the persisted matmul plan was slower and changed every TG128 output hash. Those are evidence about their exact old experiments, **not timeless impossibility claims**. The inherited 0.17.5 verifier/prefill changes justify the clean version comparison first. Reopening a setting later would require an actual changed operation affecting that setting's cost, unchanged target semantics, and a positive complete-cost case. A version label or generic faster-decode claim alone does not justify another depth/tuning grid. [Depth closure](../benchmarks/halogen0162-greedy-depth-results-20261004/README.md), [plan closure](../benchmarks/halogen0162-matmul-20261004.md).

## Exact finite implementation and test conditions

No staged/installed source package was changed by this task. Root must first bind the complete 0.18.1 engine/API/provider/source artifacts, finish its CPU bridge/observer build, qualify the actual Prefill and Decode clock boundaries, and admit the normal profile through existing startup/runtime/request-entry gates. Source mapping alone is insufficient. A fresh 0.17.4 control must independently qualify the same phase scopes and complete request. The host's current RAM admission barrier is outside this source task; no reserve or startup-floor reduction is proposed.

Freeze one common profile for all three windows: v2 and identical tokenizer/lookup source, one slot, capacity/slot/pool32,768, chunk/arena8,192/8,192, fixed MTP2, PLD3,3, stock adaptive-backoff setting, Cache Off and ordinary kernel/tuning defaults. Explicitly require identical actual capacity and pool after startup. If root instead chooses another admissible capacity or chunk, freeze it for every window before collecting results; do not splice in historical values as controls.

Use the exact saved request:

`server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-adaptive-option-20261011/client/request-16384.json`

SHA256 `0b616f5eb0aa779244cdbba4c2c7d42c8ee43ec200fc41f596e8331440f5a28c`; actual input16,384, output cap128, temperature0, seed1, nonstream completion, Thinking Off. Preserve exact rendered prompt bytes, rather than changing the task or adding repetition. Root-owned temporary profile expectations may name each actual version while all numerical settings remain fixed. This tests the supported engine/runtime bundle; it does not isolate a particular kernel from every library/host change.

Perform exactly **0.17.4 -> 0.18.1 -> 0.17.4**, one excluded warmup and three measured requests per window: twelve calls total. No cache flush, auxiliary proposer, new hardware probe or extra parameter screen. Root owns launches, qualification, recovery and final restoration. Stop after this bracket if it supplies no useful gain.

Retain exact greedy output identity, actual input/output/cap/finish counts, qualified direct RAW phase durations, independent QPC whole-request wall, combined accepted/proposed counters and all request/profile/source/native-health/response identities. Compute Prefill and Decode from their independently qualified scopes; preserve direct raw observations without a scaling multiplier. Preserve separate whole-request committed128-token throughput and accepted-draft throughput. Attribute neural and PLD acceptance separately only with an independently qualified current-version source ledger.

Require unchanged output semantics and useful improvement against both stock bookends beyond their drift. If only Prefill improves, report a Prefill gain rather than a combined Prefill/Decode/acceptance success. Higher aggregate acceptance alone is insufficient, and unchanged acceptance can coexist with a real compute saving. Component microseconds cannot substitute for the complete native phase/request result. Three measurements support a bounded descriptive screen, not a statistical-significance claim. Any output, count, finish, clock/source or admission failure rejects the corresponding performance claim.

GPU executes the changed native compute; CPU host dispatch and lookup preparation can contribute to the bundle difference. SSD/page-cache state remains a controlled workload condition, with excluded warmups and stock bookends. No supported current NPU operation replaces the Flash greedy target or MTP verifier in this candidate. There is no new NPU acceptance/speed claim.

Scope: local read-only reports/source, bounded inert ELF/symbol/constant inspection, bounded CPU disassembly and primary documentation reads. Only this report was written. No model payload, credentials, live serving API, WSL/Docker operation, engine/provider execution, hardware access, production/staged source edit or STATE mutation occurred.
