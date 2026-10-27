# Halogen trained proposal path implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Root alone controls hardware and the serving lifecycle.

**Goal:** Build a real trained proposal path for current Halogen that can improve measured Decode and useful acceptance while preserving Prefill, and place work on NPU only when an end-to-end comparison proves a benefit.

**Architecture:** Retain the target's native filters, verifier, correction and commit. A separate default-off consumer may supply up to three independent IDs only on four proven PLD miss edges. Implement the actual pretrained Inco DFlash2 equations and conditioning contract, first as a CPU reference suitable for a GPU implementation; an NPU partition requires real feature publication, ownership and measured timing.

**Tech Stack:** Windows PowerShell, C++20/MSVC, lazy PyTorch CPU reference, existing Halogen 0.18.16 v2, later Root-owned HIP/NPU execution.

**Spec:** The design and requirements below, backed by `primary01816/current-pld-nohit-consumer/findings.json`, `npu-trained-producer-research/contract-final.json`, `implementation-design.json` and the pinned SGLang/model sources referenced there.

## Global constraints

- Keep the full NPU/CPU/GPU/SSD goal active; a CPU contract, isolated kernel or source-only success is not runtime integration or acceleration.
- Root alone controls GPU/NPU/WSL/engines; one large engine. Leave the normal visible server online after hardware work.
- Startup admission remains 35 GiB physical / 131 GiB commit. Runtime reserve is 18 GiB each; new long-context/NPU requests require 22 GiB each.
- Preserve models, drivers, BIOS, voltages, global WSL settings and unrelated programs. Do not commit or push mixed foreign changes.
- Keep previous failed ready64, synchronous projection, old Pixel, untrained classifiers and already rejected policies closed.
- Exact non-repetitive requests, CacheOff/no_store, warmup exclusion and complete output/count/finish parity remain mandatory for engine qualification.
- No new speed claim until qualified engine measurements; no component-ms conversion into token rates, borrowed clock ratio or implicit async lead.

## Design and requirements

The current engine SHA is `8c184edfcb5d249d4ce525db5afe8afb32186126c7b01f1e2f007510a6c54132`. Its INFO capability argument for DFlash2 is literal zero. Neither the frontend enum nor the model card establishes a working native loader.

The new trained model is pinned at `incoai/Qwen3.8-Flash-Next-DFlash2`, revision `a22a1744e85c17364dcc54a6a420af7135d4c7f6`: 81 tensors, 603065600 parameters. It expects concatenated completed-layer means of four HC streams at zero-based layers 5,15,25,35,45, width12800. Current v2 feature equivalence is unqualified. Do not substitute old Pixel taps or normalized final HC output. Target embedding and full output head are external dependencies.

Use runtime block4 / three proposals only after its source semantics are reproduced; trained block8 remains a supported numerical test. The convolution has hidden width2560, group width16, 160 groups, two taps, base shape[2,2,2560] and projection shape[640,2560]. The selector uses rank256 and top16. The full attention implementation must reproduce the worker's noncausal query/cache positions and effective left window2047, rather than assuming a generic causal mask.

The generic consumer must preserve normal hit/fallthrough behavior and use the original empty branch whenever ownership, freshness, token definition, capacity or native eligibility is uncertain. A genuine accepted/corrected prefix and request generation must drive future sidecar state. A pointer or caller-set Boolean does not establish native ownership.

## Review focus

- Every JE/JNE edge needs an independent successful injection and fallthrough test; shared consumed state must not mask missing coverage.
- No frame writes before all checks pass. A successful modeled handoff changes only RBP and the selected stack ID bytes, then enters native filters at0x1cf97a4.
- A CPU frame is not native SIMD/XSAVE/unwind proof. Real relays must preserve the complete live state and original branch behavior.
- Model source equations, shape/layout, dtype and block boundary behavior must match the pinned source independently; synthetic fixtures establish arithmetic only.
- No hidden target features, authoritative next anchor or committed KV may be invented while target verification is outstanding.

## Task 1: Current no-hit semantic consumer

**Files:** `primary01816/current-pld-nohit-consumer/{consumer.h,consumer.cpp,test_consumer.cpp,README.md,findings.json}`.

- [x] Write refusal cases and demonstrate that an always-decline stub fails positive cases.
- [x] Implement default-off bounded consumption on0x1cf77bb/77da/7803/7d58 only; preserve the original fallthrough/empty targets.
- [x] Add model-origin, current owner/round, native allowance, actual defined-token and one-shot checks, including independent successful cases at all four edges.
- [x] Independent source/CPU review: 29 checks pass; four edge encodings, R9/R12 and CFA are separately checked.
- [x] Root independently rebuilds the frozen source: MSVC `/W4 /WX`, 29 checks and zero failures. Source pin verification is recorded separately before publication.

## Task 2: Faithful convolution and selector reference

**Files:** Create `scripts/research/dflash2_reference/{contract.py,source_oracle.py,math_ops.py,test_math_ops.py}`. Preserve source provenance/license. Reserve `reference.py` and `weights.py` for the complete model after worker/cache semantics are established.

**Interfaces:** `grouped_conv(hidden_states, delta, base, block_size, num_groups, group_size, taps)`, keyword-only `score_edges(predecessor_table, successor_table, candidate_ids, unary_logits, hidden, anchor_token_ids, top_k)`, and `follow_maps(maps, initial_indices, edges)` follow the pinned source argument semantics. No import-time inference, downloads or device selection.

- [x] Write CPU tests against independently extracted, hash-pinned source functions; demonstrate failure before implementing operators.
- [x] Implement exact convolution, dynamic input/output coefficient preparation, selector edge scoring and map following without SGLang, FlashInfer, Triton or distributed dependencies.
- [x] Test real model dimensions, block4/block8, block boundary reset, both convolution sides, selector rank/top-k, dtype/shape errors and noncontiguous input as defined by source behavior.
- [x] Limit CPU threads and allocations in tests; use no model payloads or accelerator calls.
- [x] Independent review and Root CPU verification. Report no learned quality, acceptance or throughput claim.

## Task 3: Real native and model state attachment

- [ ] Implement four exact-current-image branch relays with original branch flags, continuation and complete state preservation; no live installation before independent review.
- [ ] Bind actual native accepted GEN, slot birth/generation, reset/cancel/retirement and post-commit authoritative prefix/bonus. Demonstrate stale, reused, rejected and late publications retain stock behavior.
- [ ] Derive actual completed-HC target feature capture and immutable publication; independently reproduce the trained feature contract for current v2.
- [ ] Reproduce full DFlash worker/cache masking, target embedding/head access, exact tensor mapping and reference execution before loading trained payloads or using a device.

## Task 4: Useful device placement and engine qualification

- [ ] Evaluate every implementation on GPU as well as NPU. GPU-shared target head and selector may avoid full duplicated NPU vocabulary weights; this is currently a design, not an available shared allocation.
- [ ] Investigate preparation of already-known target-context KV separately from speculative next-token prediction. Establish exact equations, ownership, real readback/publication and time lead before an overlap claim.
- [x] Implement the source-proven 17-tensor context partition in `scripts/research/dflash2_reference/context_kv.py` with independent CPU tests in `test_context_kv.py`: FC, shared hidden RMSNorm, five K/V projections, K per-head RMSNorm and NeoX RoPE. Context preparation is private; only verified input rows (anchor plus accepted proposals) may later be selected for publication. It does not invent a hidden state for the bonus/correction token or write a live cache.
- [ ] Root executes a finite device experiment only for a complete new mechanism with plausible net benefit and frozen workload. Compare costs per committed token and full engine rates, not acceptance alone.
- [ ] Keep the consumer/producer disabled unless output semantics, memory reserve and end-to-end speed are verified. Restore normal serving and retain all failed evidence.

The initial measured baseline remains 1858.90 Prefill /54.37 Decode tok/s with66.04% native head acceptance on8192-to128, plus1906.29 on separate serial PP1. This plan does not redefine completion around those already recovered values.

## Integration findings to retain

### Continued source implementation, 2026-10-26 13:24 UTC

Ruling: retain frozen v4/observer-v2 and implement in separate v5/observer-v3
source packages within this existing workspace. Do not create another managed
worktree or commit/push the mixed foreign controller/voice changes. The cost
is an explicit later integration step; no unqualified source enters serving.

The first real early-PF generation binding is implemented in v5, with the
existing locked Connector Birth registry feeding Bridge before Initial. An
actual existing PF Observer Scope additionally binds request/controller,
prompt interval and model. Pre-Initial access does not create a Frontier.
Native Initial must join that same generation and late model before exposing
the completed binding. CPU qualification and independent review are ongoing;
current completion does not include Stage allocation, HIP completion or live
dispatch. The source review found that using the Birth generation alone as a
revocable lease ID permits reuse after a local scope drop. A regression and
a Bridge-local never-reset incarnation counter are being qualified.

The parallel observer-v3 work separates validated successful PF chunk return
from actual request retirement and exports the already-observed Scope for
that binding. Root serializes all compiler work with Voice; no engine or
GPU/NPU measurement was started in this source continuation.

Source checkpoint qualified: final v5 has127/127 new MSVC checks plus96+11
legacy checks; the actual kernel-cookie C accessors pass10 Linux modes with256
checks. observer-v3 passes205/205 against the27-failure frozen-v2 regression.
The sealed root receipt is
`primary01816/native-npu-continuation/prefill-generation-root-qualification/receipt.json`.
This is still CPU/source/socket qualification with synthetic native frames.

Next implementation uses a new composition-v3 source copy. The existing
Adapter dispatch must process the actual Scope-only v3 export before its
`!hc_proof` early return, bind the v5 lease and announce Stage.begin once per
incarnation. Each PF proof rechecks the actual v5 lease/cookie and its admitted
Chunk.scope before acquiring/submitting a complete raw-chunk job. Actual
Initial joins the same lease to the genuine frontier via Stage.joined.
Stage callbacks announce ownership acceptance only; neither begin nor joined
means GPU readiness. Retirement clears the local active ID before a single
logical revoke; buffer release remains the provider's actual completion duty.
Verify proofs receive no fabricated PF lease. No native relay/site/startup or
assembly changes, no installer and no consumption activation are included.
The v3 native export has a distinct symbol so the larger Proof cannot be
written through the old v2 ABI. One v3 TLS Tracker must serve both that export
and the original HIP forwarding. Native integration and GPU completion remain
unchecked in Task3/Task4 until actually exercised.

The saved current-image call graph places MTP verification under scheduler0x1cf4b20 even when Prefill and the first output use a separate serial setup. Direct runtime edge observation remains unperformed. The existing PLD opening check compares against a native MTP proposal, not an already known target token: an independent first proposal can be discarded on mismatch. Thus the present consumer is not yet an unrestricted DFlash verifier. A supported no-head/PLD configuration must be assessed before any opening-check bypass is considered.

The context-KV partition has17 BF16 tensors totaling117971200 bytes. Its layers share the projected target features and do not run context attention, MLP or convolution. This creates a concrete possible NPU preparation task, but the existing worker begins after target-forward return. Starting after completed target layer45 would require actual owned publication and only leaves layers46/47 as possible, unmeasured lead. Full stock Prefill cache materialization and compact-window/page-alignment behavior must not be silently replaced by an assumed last2048 rows.

## Continued implementation and independent verification

The corrected context reference now follows the pinned native/sequential CPU
RMSNorm and RoPE order, including BF16 product materialization. The earlier
loose BF16 test is explicitly superseded as qualification. Root's frozen run
passed14 tests in59.504seconds, peak997670912bytes below1GiB. Exact FP32/BF16
source-stage oracles and missing-norm/missing-RoPE mutants are included.

`attention.py` and `backbone.py` now provide the actual author-layout CPU
attention and five-layer query body. Root independently passed9 attention tests
and9 backbone tests, with zero-tolerance FP32/BF16 block4/block8 source-method
comparisons. The author's TRT backend repeats p+B cache length for B
single-query decode rows, so all queries share
`[max(0,p+B-2048),p+B)`. This supersedes an assumed per-query sliding mask.
The CPU SDPA realization is not a claim of TRT/GPU/NPU bitwise identity.

The source-only native commit observer follows real verifier-call,
verifier-return, commit-return and normal history-publish points. Root verified
54 checks under both MSVC and Linux GCC with warnings treated as errors. It
separates committed target INPUT rows (old anchor plus accepted proposals) from
emitted OUTPUT tokens (accepted proposals plus bonus/correction). It still
does not supply GEN-birth/full-prefix authority, live relays or GPU readiness.

Current v2 may defer raw HC scatter into the next layer's pre-step. A return
from layer45 therefore does not prove that its completed raw streams have been
materialized. Exact current-buffer/source binding remains in progress; the
earlier possible two-layer lead is an upper-bound hypothesis, not measured lead.

Normal server identities and all CPU receipts are saved under
`primary01816/native-npu-continuation/`. No accelerator cohort, native installer,
trained model payload or server restart occurred for this continuation.
The normal adaptive server remains online; the full optimization goal remains
active and unachieved.

### Superseding source checkpoint, 2026-10-26

The earlier online statement is historical: current normal restoration failed
the unchanged35GiB admission and the server is offline. No further admission
retry without changed conditions or the existing30/35GiB answer.

observer-v4 typed native status passes384/384 host checks. Composition-v4 now
requires actual matching returned coverage rather than five submissions alone.
Status RED462/16 -> GREEN457/0 includes real-thread actor tests (separate
RED211/8 -> GREEN211/0). Full real11-TU Linux DSO links without undefined
symbols; real default/unbound fixture13/13. These advance source integration,
not Task3/4 native/device completion or measured engine speed.

Ruling: preserve v3/v5 and frozen dependencies; do not activate v4 Consume.
Actual multi-outer PF Scope continuation, direct Stage lifecycle revocation,
synchronized consumer grant, Stage-owned allocation/fence/publication and
incremental accepted-input integration remain required. Contention is a sticky
fault request, not quiescence; in-flight Stage operations and already-produced
local Offers can complete. The provider must retain outstanding GPU storage.
No new diagnostic series alone is justified by these limitations. Current
claims and exact receipts are in composition-v4/STATUS.md and the main report.

### Owned Stage provider implementation

Decision by Root within the existing delegated implementation scope: add a
separate default-off current-native-stage-v1 provider. Allocating a buffer for
every prompt chunk scales to several GiB at long context and cannot meet the
bounded reserve requirement. Reusing one buffer after a host callback returns
would race outstanding GPU readers. Use two preallocated8192x12800 BF16 concat
buffers instead (400MiB total at maximum size), with explicit producer and
reader completion events. A full pool declines immediately and retains stock
serving; it never waits for the worker in the native callback.

An injected current-process backend supplies allocation/free, event create,
record/query/destroy and the existing mean enqueue. No import/device selection,
auto binder, interposer activation or inferred stream ownership. Stage acquire
correlates the actual lease and PF Proof with one slot/forward/tap; submit must
match that exact acquired job. Five successful submissions record a producer
event, not readiness. A private reader lease is issued only after a successful
event query; logical revoke cannot free or reuse unfinished storage. The reader
must supply its own actual completion fence before collection/reuse. Initial
join records the genuine native frontier separately from GPU readiness.

Tests must first fail for unfinished/stale/foreign output, duplicate taps,
exact-job mismatch, producer-not-ready, pool exhaustion, logical revoke with
in-flight work, unreleased reader and partial allocation/event failure.
Root serializes CPU compiler work and later decides whether a complete new
mechanism warrants an actual device fixture; no engine restart is warranted by
this component alone. Real native callback attachment, repeated outer Scope,
Bridge-to-Stage lifecycle notification and synchronized consume remain open.
The provider supplies private storage lifetime, never an async native grant.

Source checkpoint: injected-backend provider now implements that bounded
lifetime protocol. Strict MSVC RED41/28 -> GREEN412/0 with unchanged tests;
Linux GCC GREEN412/0. Independent review has no blocking source findings under
the serialized backend contract. Actual HIP allocation/events and native
integration remain unqualified; do not mark Task3/4 complete. A raw HIP wrapper
must not expose ambiguous free/destroy failures as retry-safe release errors.
Native Init/ChunkReturned authority and actual stream completion remain
separate. Real worker projection must split read chunks into at most2048 rows
with start_position=chunk.base+offset while retaining the reader lease.

### Multi-outer-Prefill continuation decision

Preserve Bridgev5 and Observerv4. The first actual Scope binds one canonical
generation lease. Compositionv5 tracks the true currently observed Scope
separately. Every later actual Scope must first pass normal Bridge processing
(including complete prompt-content/GEN checks), then advance exactly one local
sequence between fully returned forwards, before Initial and before full
coverage. Recheck the real prefill getter/socket cookie and the unchanged
canonical lease. Do not rebind, reset coverage, restart Stage or rewrite proofs.
Actual Proof.pf_scope and returned Scope must exactly match current observation.
Initial matches canonical id/scope and birth, then the existing enriched native
owner fields; it must not compare the old pre-Initial owner byte-for-byte.

Providerv2 separately compares underlying capture identity, excluding only the
local observation sequence. Canonical lease equality remains strict. First
capture matches the canonical sequence; only a new forward at tap0 may keep
that capture sequence or advance exactly one after all five prior submissions.
Every tap of one forward retains the exact same actual Scope. Storage,
producer/reader events, reservations and retirement rules stay unchanged.

Use isolated composition-v5/provider-v2 source copies and distinct v5 exports.
Root runs frozen failing regressions before implementation, then host tests on
both toolchains and the real-module default-off Linux link. No native image
installation, new callback site, relay, startup or assembly work is included.
Do not retry the rejected callback task. This closes a named source requirement;
it does not establish accepted-input integration, native consumption, NPU gain
or a new model token rate. The normal-server35GiB startup floor stays unchanged.
