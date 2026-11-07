# Halogen 0.19.1 MTP and next mechanisms

## Evidence and serving baseline

This note records the bounded CPU investigation on 2026-11-07. The pinned
`flash_serve` SHA256 is
`9dcf048b93111aba93032aa2ba0bea07496bc14c0cd4316a21dc39d2db749d46`.
The retained serving baseline is checkpoint v2, one 32,768-position slot and
2,048-token prefill chunks. Its profile SHA256 is
`69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`,
with controller/backend PIDs 28972/24440. The publication receipt records
`f703306afe24cba082a821e40cf96a65ac31bfe7` pushed to `origin/main`.
Provenance is `server/.local/halogen-update-20261107/primary0191/completion-closure/final-publication.json`.

The work below used saved files, exact upstream source and static ELF
inspection. Hardware qualification remains pending for source-only candidates.
Private mechanism paths below are relative to
`server/.local/halogen-update-20261107/primary0191/next-mechanisms-1722/`.
The previous broad refresh receipt is
`server/.local/halogen-update-20261107/primary0191/completion-closure/source-refresh-1713/receipt.json`.
Its next refresh boundary is 19:17:35 UTC. [Pinned Halogen release](https://github.com/peonist-ai/halogen-flash-server/tree/v0.19.1)

## Copied-log PLD closure

Four saved responses each report 154 lookup rounds, 1,078 drafted tokens and
1,076 accepted tokens. The audited default KBACK limit is seven tokens per
lookup round. Since `154 × 7 = 1078`, every observed lookup chain reached
seven proposals. Raising nominal K from three to four cannot lengthen those
same observed chains. Provenance is `pld-key/native-proof.json`.

The conditional replay covers N=3/4/5/6 and K=3/4. Under default KBACK,
FOLLOW and the K0=0 regime, every pair produces the same scheduled trace,
154 lookup rounds, 1,078 drafts, 1,076 accepted-prefix tokens and 28
single-token fallbacks. That closes the chain-length premise for another
K4 or longer-N attempt on this frozen copied-log case.
Provenance is `pld-key/conditional-replay.json` and `pld-key/assessment.md`.

The target sequence comes from canonical BPE re-encoding of the visible
output, giving 1,258 IDs plus either candidate EOS ID. Native generated-ID
identity and native MTP-head scheduling remain unproven. Agreement with the
saved counters supports this conditional reconstruction. Longer-N execution,
acceptance and latency still require separate qualification. Independent
review checked 12 captures against 57,681 native bytes, 44 instruction
assertions, four responses and all 32 replay schedules and prefix sweeps.
Provenance is `libosmos-layout/independent-pld-review.json`.

## libosmos routing-table placement

libosmos 0.5.4 moves large expert-routing placement into one 256-thread block
per expert when flattened picks exceed 256. Each block performs tiled prefix
placement in original pick order. The retained small-pick path avoids the
extra launch. Added scratch is `int32[3 × experts]`, or 6,144 bytes for 512
experts. The outputs remain integer token/place mappings with 16-slot padding.
Provenance is `libosmos-layout/upstream-review.json`. [Pinned placement kernel](https://github.com/mrsirg97-rgb/libosmos/blob/90fbace02270bde50f41bb9d9beb5f0e3bae5f43/kernels/q4x_moe.hip)

Pinned Halogen already launches histogram, scan and parallel scatter through
host planner `0x1f08e50`. Histogram/scatter use 256-thread blocks over 1,024
picks, with a 512-thread scan between them. Both audited callers form
`picks = 10 × tokens`. Its compact intervals and q4 `Item` consumers need
their own ABI proof. Current loaded-weight dispatch, native stable ordering,
injectivity and complete consumer bounds remain unproven. The upstream
reported 16K prefill gain supplies no local Halogen gain estimate.
Provenance is `libosmos-layout/feasibility.json`. [Pinned table contract](https://github.com/mrsirg97-rgb/libosmos/blob/90fbace02270bde50f41bb9d9beb5f0e3bae5f43/include/osmos/gpu/q4x_ops.h)

The 27 upstream CPU placement cases and 30 abstract adapter/bounds cases pass.
A direct port lacks an established Halogen bottleneck to remove. The retained
80.48 GiB model-capacity blocker also remains open. Provenance is
`libosmos-layout/offline-integer-oracle.json` and `libosmos-layout/feasibility.json`.

## Official NPU contract

The shipped NPU helper accepts token IDs for its own small models.
`GEN`/`LGEN` return their completions, while static batches serve embedding,
reranking and moderation. `QSETH`/`QSETMH` expose the helper's own selected
hidden rows as uint32 words reinterpreted as FP32, consumed by calibrated
CPU readout. Internal device precision remains model-specific. Provenance
is `official-npu/assessment.json`. [Pinned official NPU documentation](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/docs/NPU.md)

A Flash integration still needs a per-round proposal consumer with aligned
vocabulary, accepted-prefix feedback and rollback ownership, or a named
tensor consumer with shape, dtype/layout, synchronization and buffer lifetime.
Those bindings remain missing from the exposed helper/API. The documented
platform uses Linux `amdxdna` and XRT. Windows FP11/395 interoperability and
positive mixed-runtime savings remain unqualified. Provenance is
`official-npu/assessment.md`. [Pinned official platform contract](https://github.com/peonist-ai/halogen-flash-server/blob/47ceb439fd97ef4b62cc18042fda505113546567/docs/NPU.md)

## Existing MTP banks and Q8 candidate

The 17-bank MTP vocabulary path is statically eligible in default automatic
mode. Its loader guard follows successful MTP tensor initialization. Actual
bank loading/repacking and a populated runtime bank pointer remain unobserved.
Banks contain 34,571–65,166 rows of the 248,320-row vocabulary. The native
selector uses a 128-ID membership history, a baked cost rule, hysteresis and
four-target reselection. Provenance is `official-npu/mtp-shortlist-review.json`.

`mtp-shortlist/containment.json` and
`mtp-shortlist/conditional-selector-study.json` study visible-output BPE
membership and the source-derived selector. Native target IDs and scheduling
remain unproven. These results support conditional row-selection analysis.
Acceptance and throughput need matched runtime evidence.

`HALOGEN_DRAFT_VOCAB_Q8` is an existing GPU kernel-policy control with a loader
and logits consumer. Q4 selected rows use 1,440 logical bytes and Q8 rows use
2,720 bytes, a 1.889× increase. The selector's baked cost coefficients stay
fixed under Q8. The prepared whole-engine study compares the same frozen
requests at Q4/Q8/Q4 and requires exact target-output preservation. A direct
per-logit accuracy attribution still requires matched hidden inputs and draft
logits. Provenance is `q8-candidate/` and the native trace proof under
`official-npu/q8-verbose-proof/`.

## Pending handoff

The inactive bundle contains 53 candidate files and 50 exact rollback files.
Its transition SHA256 is
`ecae649e6e437f71ddfd53a891aea4344629f361c712f5e67773df561a93c32b`.
The 12 focused forwarding/manifest tests pass. The cloned backend suite ran
27 tests with eight Windows skips. The 45 coordinator/Q8/trace tests, 40
collector/QPC tests and 51 exporter tests pass. The bounded bank/selector
prototype passes 12 tests. Independent review retained all 1059 historical
numeric leaves and all ten historical public report hashes.

The current online package retains its exact 50 baseline files. The 2 GiB
RAM resource question remains pending. The coordinator rejects inadequate
22/22 GiB entry reserve before creating a run or stopping the selected server.
It retains the normal 30/131 GiB startup and 18/18 GiB runtime floors.
The comparison has generated zero requests. The prospective plan retains
the exact source hashes, 24-request protocol and source-only preparation
command. [Q8 study plan](../benchmarks/halogen0191-draft-vocab-q8-plan-20261107.md).
