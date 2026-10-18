# Independent NPU ROI decision — 10 October 2026

**Bounded no-go: no presently justified NPU attachment for Halogen Prefill,
Decode or acceptance.** This decision follows the completed consumer and
quality evidence; it does not claim every future NPU algorithm is impossible.
No new hardware diagnostic, producer, live hook or serving cohort is warranted
by the inspected evidence. The root agent owns later execution and lifecycle.

This review used local source and retained reports only. It performed no
GPU/NPU/provider operation, API request, WSL/Docker command, model-payload read,
build, test, STATE edit, commit or push. Only this report was created. No
general update sweep was repeated; root's retained 10:14 UTC check is not due
before 12:14 UTC.

## One real early-input mechanism, and why it is not admitted

The strongest retained mechanism outside synchronous Decode projection is
**prepare the next Prefill chunk's PLE key/value results from owned known prompt
tokens while the target handles the preceding chunk**. PLE row IDs and gathered
input depend on the token slice, preceding carry, immutable table/constants and
model generation. A producer could deliver a completed same-generation result
before the next key/value projection, removing GPU projection work without
waiting for a changing target hidden row.

The exact 0.17.2 source evidence is concrete:

- `ple_early_token_publish_0172_v2.c:384` writes an owned second-chunk token
  slice and carry before the first original Target call. The native prefetch
  launch/worker/join taps preserve the existing native calls; the receipt
  explicitly keeps `input_ready_lead_qualified=false` at line 445.
- `ple_engine_binding_0172_v2.h` pins the exact 0.17.2 image and native prefetch
  functions. It does not qualify a 0.17.4 rebasing or runtime replacement.
- The successful observation had 17.520212 ms small-token publication,
  14,708.678294 ms from publication to the second key, and a 200.944243 ms
  native wait-to-join interval. Most native lookup was already overlapped.
- The archived v5 input replay took 0.859 s through its sampled ready boundary,
  and saved raw FP8, original-order IDs, BF16 and FLOAT inputs. It ran after
  the observer stopped. It establishes neither current native input parity
  nor a live Windows-to-WSL result lead.

Source: [current PLE overlap report](halogen0172-prefill-overlap-20261008.md),
[publisher](../../scripts/benchmarks/halogen_ple0172_early_tokens/ple_early_token_publish_0172_v2.c),
[image binding](../../scripts/benchmarks/halogen_ple0172_early_tokens/ple_engine_binding_0172_v2.h).

The useful consumer is ordinary target state, not draft logits. The executed
M8192 NPU projection passed its development tolerance but changed
**88,572,989 of 104,857,600 native BF16 words**. The stricter CPU discrepancy
also remains. Later target verification of proposed draft IDs does not repair
changed prompt key/value state. The retained screen therefore does not qualify
this producer for the unchanged target arithmetic contract.

The actual single NPU call cost 203 ms, with 15 ms feed copying and 26.610 s
session creation/compilation reported separately. It returns a 400 MiB FLOAT
pair, whose native BF16 representation is 200 MiB. The actual publication route
would still need conversion, owned IPC, upload, completion ordering, generation
validation and retirement. The exact-GPU retained-result control proves that
substitution can preserve the fixture, but its poisoned/captured stock and
ready consumer intervals have unequal evidence work and cache histories. It
does not prove a production consumer win.

Sources: [NPU PLE component](halogen-ple-npu-component-20261008.md),
[exact native controls](halogen-ple-owned-controls-20261008.md),
[independent input qualification](halogen-ple-independent-input-20261008.md).

The cost test must be applied at the real consumer:

`max(0, P - L) + H + J + Q < G`

Here `P` is complete preparation/producer cost, `L` is actual generation-bound
lead until the consumer, `H` is complete output packing/transport/upload,
`J` is lookup/validation/publication, `Q` is target slowdown caused by concurrent
work, and `G` is native critical-path work actually removed. The 14.709-second
interval supplies a potential lead; it is not 14.709 seconds of saving. The
8.648-second worker interval is likewise not removable critical-path time.
The observed native key/value projections total about 54.753 ms and publication
38.640 ms in different instrumented scopes. Subtracting them cannot establish
an approximately 16 ms saving. A complete matched consumer cost is absent.

Supported Windows GPU/NPU coexistence and a cross-WSL buffer/fence contract are
also unqualified. DDR is shared and concurrent preparation can slow the target.
Offline preparation avoids concurrency only when amortized before real service;
with Cache Off and new prompt slices its startup/preparation cost cannot simply
be omitted. Thus a large causal window alone does not admit this NPU placement.

**Disposition:** source-concrete future PLE preparation, but no currently
qualified numerical producer, faster complete consumer, actual publication
lead or coexistence. Do not reopen the unchanged observer/component merely to
add measurements.

## Evidence closing the other tempting routes

| Route | Retained result | Consequence |
| --- | --- | --- |
| Synchronous paired E/H projection | GPU host 0.487170 ms; corrected NPU session 1.850025 ms before bridge | Late GPU inputs supply no independent lead; retain GPU. |
| Native vector H | Fastest complete retained native call 355.6 µs; original resident GPU H mean 158.707 µs | Capture, bridge and publication add cost; no new unchanged screen. |
| Whole count1 embedding branch cache | Fixed GPU producer had 292 hits/skips and exact output/acceptance; Decode 32.539 versus 41.589 tok/s stock-bookend mean | Whole gather/RMS/M1 suppression already exists and loses. An NPU prewarm cannot fix this consumer. |
| Checked-copy cache derivative | Partial +2.168% Decode versus stock-before; rejected interference, no stock-after or complete hit/skip coverage | No qualified consumer win; do not report or use the partial rate as admission. |
| PLD mixed prepared prefix | Exact original-GPU component, case-mean saving only 0.2–17.6 µs with order/outlier sensitivity | No demonstrated margin for producer, validation and contention; retired. |
| Low-rank native MTP head | Actual native query is late GPU data; no established positive lead | Serialized full capture/IPC/logit-return cost lacks a removable current-head budget. |
| Frozen rank64/top256 shortlist | Native winner recalled in 11/15 captured heads | Exact rescoring cannot recover the four omitted winners; no NPU attachment or refit. |
| Causal PLD64 | Natural16K cohort: zero tail substitutions, zero native PLD attempts; its only copied offer has an opening mismatch | No realized mechanism or new NPU lead; do not refit to this completed cohort. |
| Token-hash neural skip selector | Held-out MLP worse than prior and linear controls; skip diagnostic included 15 rows accepting both horizons | Faster NPU placement does not repair prediction utility. |
| DFlash context projection | BF16 native/mixed sessions rejected before dispatch; FLOAT mixed route 7.8769 ms excludes capture/IPC/H2D and differs numerically | No qualified NPU-only accuracy or complete route win. |
| DFlash consumer | Natural full-context seven-query shadow 0.6875 useful prefix at 37.054 ms; tail4096 0.625 at 27.948 ms | Lower component cost came with lower mean utility; native/NPU attachment remains off. |

Sources: [practical NPU placement](halogen-useful-npu-decision-20261005.md),
[vector-H decision](halogen-npu-native-hidden-vector-decision-20261005.md),
[whole-branch cache finding](halogen-next-mechanisms-20261006.md),
[checked-copy result](halogen-checked-copy-completion-20261006.md),
[mixed-prefix result](halogen-npu-pld-mixed-embedding-result-20261007.md),
[low-rank decision](halogen0172-npu-lowrank-mtp-decision-20261008.md),
[shortlist result](halogen0172-mtp-shortlist-cpu-20261009.md),
[PLD64 native result](halogen0174-causal-pld64-20261010.md),
[zero-offer audit](halogen0174-pld64-zero-offer-scope-20261010.md),
[selector result](halogen0173-selector-pilot-20261009.md),
[DFlash component checkpoint](halogen0173-dflash-components-20261009.md),
[DFlash context-window shadow](halogen-dflash-context-window-v2-shadow-20261010.md).

The DFlash ContextProjector's source consumes actual five-tap target features,
not prompt IDs. `provider.py:_project` validates those owned features;
`append_prefill` projects contiguous accepted rows; `apply_verification`
projects only accepted verifier rows. That causal input cannot inherit the PLE
known-token lead. Preparing earlier accepted DFlash rows before later prefill
chunks is structurally possible, but current native consumer utility and the
qualified NPU mathematical route are absent. The synthetic full-body finite
accumulator's 11.70% cost reduction preserves one frozen fixture and supplies
neither native utility nor serving gain.

Sources: [provider](../../scripts/research/dflash_k3_provider/provider.py),
[tensor graphs](../../scripts/research/dflash_k3_provider/tensor_graphs.py),
[full-body component](halogen-dflash-finite-fullbody-component-20261010.md).

## Action and reentry requirements

Keep all present NPU acceleration paths disabled. Prioritize root's native
phase/GPU work rather than additional NPU protocol scaffolding. The present
NPU deltas for actual Prefill, Decode and native acceptance remain unmeasured;
an unintegrated candidate is not a measured zero delta.

Reenter future PLE preparation only after independent evidence changes the
negative case: an output producer satisfying the unchanged ordinary-target
contract, a current-image matched exact-GPU-result consumer with positive
complete budget, a real same-generation ready boundary before consumption,
and a supported coexistence/publication path whose added cost fits that budget.
The first missing condition is mathematical target validity; no NPU timing
experiment can establish it by itself. If those conditions become available,
root can seal one finite experiment before execution, retain stock bookends,
report cold and warmed costs separately, and measure complete request wall,
Prefill/Decode, exact greedy output, proposed/accepted counts, real substitutions
and reserves. There is no recommendation to run that experiment now.

The 4 MiB L2 plus 2 MiB distributed L1 remains private NPU SRAM. It is not a GPU
capacity mechanism through the checked interfaces; additional DDR copies consume
existing memory. Retain the [memory/fabric decision](halogen-npu-memory-fabric-20261005.md)
and existing root reserve/lifecycle requirements.

## Follow-up: native-opening-seeded historical tails

Root asked whether replacing the whole width-three PLD offer with the native
cached opening plus two causal historical IDs supplies a distinct opportunity.
**No-go under the supplied requirement that this opening be guaranteed
authoritative. It is a speculative MTP ID.** This conclusion uses source and
earlier evidence; the completed natural16K suffixes and labels were not rescored.

The exact 0.17.4 main disassembly makes the distinction visible. At
`0x180378b`, native head wrapper `0x18beb50(model,current,0,0)` returns EAX;
`0x1803790` stores it into request `+0x1a0`. An existing nonnegative value is
reused. The cached-ID equality at `0x18031a9` gates PLD admission, but target
verification still follows at `0x1803202 -> 0x18bee70`. Actual target outputs
at model `+0x20[i]` are compared with all copied draft IDs at
`0x1803210..0x1803224`. The ordinary neural path independently demonstrates
rejection: after verifying `[current,cached_opening]`, `0x1803d11` compares the
actual target result with request `+0x1a0`, and a mismatch commits only the
target correction. Cached-opening equality is therefore not first-token
acceptance. Earlier retained native openings matched target-next in 12/15
boundaries, with three explicit mismatches.

Evidence: `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/root-phase0174-linkage-01/function-17f1ee0.stdout.txt:14821`
and `:15097`; [earlier opening provenance](halogen-independent-proposer-benefit-20261006.md).

A historical lookup conditioned on that already available draft ID can be
causal in principle: keep only committed history in the index, use the pending
native ID only in the query, and let the unchanged target verify the complete
offer. Rewriting before the native opening comparison can preserve its actual
invariant when the new first ID equals the same valid cached opening. It is
a hybrid native/history proposer, not an independent predictor or an oracle.
A negative/missing cached opening must decline: native generation occurs
downstream and the current synchronous provider must not invoke it.

The existing PLD64 contract intentionally keeps stock slot zero, selecting a
different historical tail without changing native opening-gate eligibility.
It is not permission for a full rewrite. `tail_adapter.h:113` requires
`candidate.ids[0]==stock[0]` and line 129 writes only slots one onward. The
provider Key has no copied cached-opening field, the immediate LiveGuard does
not recheck that field, and the journal verifier at line 116 rejects a changed
stock opening. A full rewrite would need a separately bound/guarded opening,
new transaction/evidence semantics and complete original/post-write IDs before
resuming the same native guard, verifier, commit and replay. Changing one
comparison in the current adapter would not establish that scope.

Prior work already investigated this mechanism class. The frozen
[count-mode backoff hybrid](halogen-count-mode-backoff-screen-20261007.md)
seeded each chain with the native opening, queried committed history plus the
pending seed, and produced **zero extensions in fifteen rounds**. It was
retired. [Strata pending-MTP chaining](halogen-strata-lookup-complement-20261006.md)
also documents the distinct hybrid query. Neither proves that the exact proposed
trigram-plus-native-opening rule fails on every family; no admitted held-out
yield for that rule was found. The related negative evidence does not justify
another unchanged family screen or fitting to the completed natural16K cohort.

Its ideal benefit would come from skipping later native draft generation and
committing more useful IDs in a verification round. Seeding the opening cannot
improve that opening's target correctness; a first mismatch rejects both tails.
Additional verifier width, commit/replay, lookup and relay cost must fit any
extra committed-token yield. No such matched budget or yield is established,
and bounded CPU history search supplies no NPU placement rationale.

The retained current hook observed only **one copied PLD frontier per request**
in a 128-output request. Even an ideal replacement concerns one width-three
opportunity, not every Decode round. At that same frontier, at most four output
IDs can be committed versus at least one from fallback; the local theoretical
increment is at most three. That is not a throughput forecast or a bound on a
changed rollout's later opportunities. Broader ingress/coverage evidence is
absent, so a new live rewrite or cohort is unjustified. No implementation,
expanded qualification gates or new experiment follows from this review.
