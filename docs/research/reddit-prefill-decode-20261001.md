# Strix Alloy: Reddit review and prefill/decode experiments

Snapshot window: 22 September 2026 00:00 through 1 October 2026 22:56, Europe/Berlin.
This is the window fixed at the start of the task, not a rolling window during tests.
Host: existing BOSGAME Ryzen AI Max+ 395, Windows 11 / WSL2 DXG, 128 GiB unified
memory. No driver, BIOS, clock, compiled engine, weight format or model was changed.

## Scope and evidence quality

The public Arctic Shift archive returned 73 posts and 1,521 comment objects in
that interval. 1,373 comments belong to those 73 posts; 148 belong to older posts.
20 comments on the selected posts have deleted/removed/empty bodies. They were
not reconstructed. Direct Reddit listing/JSON/RSS requests were restricted or
stale, so archived timestamps, pagination with overlap and ID deduplication were
used. The archive is complete for the returned query, not proof that it captured
every live, removed, edited or not-yet-archived Reddit record.

The metadata ledger includes every retrieved post. The link index contains 253
extracted URL strings, including image, shopping, local/example and malformed
addresses. This is not a claim that 253 independent technical pages were read.
Relevant technical repositories/docs were inspected in depth; inaccessible
external pages and lower-relevance links remain indexed, not falsely marked read.
Category labels in the CSV are heuristic hints, not benchmark evidence.

Raw archives stay in the ignored local task directory. Published indexes contain
metadata and links, not a redistribution of complete comment bodies or API keys.

## Implemented bounded changes

`server/draft_profiles.py` now accepts optional `prefill_chunk` and `prompt_lookup`.

## Measured outcome

The task retained 90 measured benchmark requests plus warmups. Inputs, actual
output counts, timings, cache counters and hashes are in the companion JSON.
Halogen uses clock-calibrated phase rates and separate Windows wall times.

| Halogen prefill block | PP8192 tokens/s | Sample standard deviation | Change |
|---:|---:|---:|---:|
|2048 baseline|1374.713|5.916|reference|
|4096|1465.492|2.279|+6.60%|
|8192|1502.223|13.020|+9.27%|

Both larger blocks produced a different 128-token continuation from the baseline
at the 8192-token input. Each candidate's own serial and MTP outputs agreed.
The cause is not established by hashes alone. These are experimental throughput
results, not a general quality qualification. Neither replaces the old default.

GUFO used three-token Latin-vocabulary MTP, unchanged prefill and checkpoints.
A-B-A testing provides six control and three candidate samples per workload.

| Workload, 256 output tokens | Control decode | Lookup decode | Change | Wall reduction |
|---|---:|---:|---:|---:|
|Copying provided text|59.550|61.869|+3.89%|1.81%|
|Small file edit response|59.378|64.641|+8.86%|6.34%|
|Original prose|36.320|36.036|-0.78%|-0.94%|

All compared GUFO prompt and output hashes matched. Per candidate request, 59/60
lookup proposals were accepted in the copying case, 116/116 in the edit case,
and zero proposals occurred in prose. The workload is a fixed-length throughput
probe, not proof of a completed file edit or an end-to-end agent benchmark.

## Research conclusions and references

Rulith was inspected at 7f04d24185cb2438ea444ea3f9c0d88852dfb0db. Its approximately
100 tokens/s headline is aggregate throughput over eight conversations, not the
single-user number. Its published single-user MTP result is about 46 tokens/s
short and 42 at 86K occupied context. Its 1237 PP result uses a 95.6K input.
Different checkpoint, draft head, allocation and concurrency prevent ranking
that result directly against this machine's short-prompt Halogen run.

The Rulith patch manifest ties changes to a specific pwilkin base and order.
Its important ideas are tiled prefill, reduced launch/readback cost, PLE sharing
and proper sampled speculative acceptance. No upstream patch script was executed.
The withdrawn unified-memory environment-variable result was not adopted.

Related source: halo-box/strix-llama.cpp PR 91 (merged September 29) combines
chunked DeltaNet, parallel PLE gathering and QSA scorer/top-k kernels. It reports
large gains against its own older base, with quant-specific operator and numeric
checks. Those are not measured gains on our pinned PROJFIX binary. A port/rebuild
and model-level numerical validation would be separate work, not a config change.

The strixhalo-verified tool-call work has another useful target: sampling one
candidate before a full grammar scan and avoiding scheduler rebuilds between
turns. Its streaming CPU-read path is disabled on Windows in that release.
Its Linux/Vulkan speedup and modified graph cannot be transplanted by setting
an environment variable on our ROCm engines. That grammar port was not implemented.

The clean-room HGN specification describes layout, tensor conventions and a
GUFO port plan, not a ready HGN loader/kernel path. It calls out head-order and
normalization conversions. A format change was not confused with this task's
unchanged-weight performance comparison.

## Interfaces, qualification and final operation

The optional prefill chunk is validated as 2048, 4096 or 8192 and cannot exceed
the configured context. The Halogen launcher carries the explicit value through
to both the prefill chunk and a sufficiently sized MAX_TOK arena. Defaults and
runtime binary pins are unchanged. GUFO prompt lookup can be enabled, disabled
or preserved explicitly; it is not a silent routing or model-selection change.

Ready local profiles:
- `server/.local/gufo-mtp-lookup-262k.json`: measured opt-in lookup, Latin draft vocabulary, depth 3.
- `server/.local/halogen-prefill4096-experimental-262k.json`: different-output prefill experiment.
- `server/.local/halogen-prefill8192-experimental-262k.json`: different-output prefill experiment.

The GUFO prefill override is implemented but was not hardware-benchmarked here.
No new Rulith, Vulkan, HGN or speculative-sampling kernel was ported or rebuilt.
No full-length agentic task, sampled-quality or filled-262K quality qualification
was performed. The 256-token edit probe is not a completed file-edit benchmark.

Full source regression: 477 tests, 408 passed, 68 skipped and one existing failure
in the old Halogen backend: `test_sessions_probe_cleanup_terminates_real_descendant`
with `DUMMY_DESCENDANT_SURVIVED`. All 42 managed-server tests and the executed
current-backend tests passed. 27 PowerShell source files parsed successfully.
All five changed production files and three new test files matched the exact
fresh export used for those tests; `git diff --check` returned zero.

The first old Halogen shutdown timed out on its original memory-recovery floor.
The failed observation was retained. A later eight-sample check exceeded the same
unchanged floor after both controllers and the owned container were verified dead;
only that run's stale ownership lock was released. No floor was reduced.

Final verification: Halogen-v2 is READY at capacity 262144 with draft depth 1,
prefill chunk/arena 2048, cache Off and the 18 GiB reserve. A real authenticated
request returned OK; wrong/missing authentication returned 401. PROJFIX, GUFO
and NPU test ports were closed. Free physical memory was 37.26 GiB at this check.
The running Halogen uses the original allocation profile. No default registration,
API key, BIOS, driver or model weights were replaced. Changes remain uncommitted.

Additional coverage qualification: four retrieved post bodies were unavailable.
The complete metadata and related-URL ledgers are `strixhalo-post-index-20261001.csv`
and `strixhalo-link-index-20261001.csv`. Not every linked page was fully reviewed.
The original archives, bounded reading packs and raw benchmark logs remain under
`server/.local/reddit-research-20261001-2256/`.

## Selected primary sources

- https://github.com/rulith-dev/rulith-inference/tree/7f04d24185cb2438ea444ea3f9c0d88852dfb0db
- https://github.com/rulith-dev/rulith-inference/blob/7f04d24185cb2438ea444ea3f9c0d88852dfb0db/docs/results.md
- https://github.com/halo-box/strix-llama.cpp/pull/91
- https://github.com/AIdevsmartdata/strixhalo-verified/blob/main/CHANGELOG.md
- https://github.com/jtsylve/hgn-spec/blob/main/PORTING-GUFO.md
- https://github.com/gufo-org/gufo/pull/350
- https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md

The hipStreamCreate OOM gist linked by post 1wul62u was not readable through the
available GitHub/web routes; its contents were not assumed or implemented. Linux
kernel/IOMMU/zram changes, eGPU/RDMA hardware and alternative quantizations were
not treated as free tuning flags for this existing Windows/DXG model setup.

## 2 October implementation and applicability ledger

This section records source work after the historical measurements above. It is
**not** a claim that the new candidates have passed live model qualification.
The managed state was STOPPED without an error when inspected at 00:48 local;
no other engine was launched for this source-only pass. All candidate profiles
are ignored under `server/.local/`; the registered profiles and pins remain
unchanged. The current controller will record a SHA-256 of the exact profile
bytes on the *next* launch; the older stopped state has no such field. The
common harness refuses to attribute measurements to an unverifiable profile.

| Backend / idea | Pinned-source finding and action | Status |
|---|---|---|
| Halogen 4096/8192 | Opt-in profiles already forward the chunk and matching arena. Added functional/hashes/repeat-state gate and optional top-5 token-logprob comparison. The prior 8192 continuation differed from 2048; this remains a hard candidate-vs-control failure until explained. | **Experimental, not promoted**. No exact-logit API was found in the inspected service source; the harness probes for actual per-token top-N data and labels any comparison a proxy, never full-logit equivalence. |
| GUFO prompt lookup and routing | The pinned `7e924c2` Windows binary supports `--prompt-lookup` as a process flag, not a per-request flag. Existing MTP lookup remains. A content-aware HTTP router would either need a rebuilt request-level switch or two simultaneous large engines; neither is safe under this reserve. | No pretend router. Isolated serial control and lookup profiles are deterministic and testable. |
| GUFO state reuse / prefill | Pinned source contains `text_generation_scheduler.cpp` snapshot phases, Qwen Flash-Next GPU verification, prompt lookup and `--prefill-chunk`. Added an isolated `--cache-disk` lookup profile (8 GiB disk budget, 4 GiB staging ceiling) for shared-prefix checkpoint tests, with the same 18 GiB managed physical/commit floor. | Candidate only. Snapshot capture can increase cold TTFT; compare multi-turn wall and `usage.gufo` snapshot/restore phases before adoption. [Upstream issue #318](https://github.com/gufo-org/gufo/issues/318) is a proposal, not a ready Windows patch. The later Q4/Q8 27B changes in [#247](https://github.com/gufo-org/gufo/commit/53f8b0a14c2cb71082879d1fc1ca1948957bf8eb) are not a verified drop-in for this Flash-Next quant. |
| PROJFIX checkpoint reuse | The pinned `40a9f4d0` + eight patches already has `--ctx-checkpoints`, `--cache-ram`, context checkpoints, and scheduler reservation. Added an isolated 64-checkpoint candidate, explicitly capped at the existing 8192 MiB cache default. New generated controls request 18 GiB, not the earlier generator's 12 GiB. | Source-level option tests passed; model quality, memory and agent-loop A/B still pending. No registered command changed. |
| PROJFIX chunked GDN / PLE / QSA | [halo-box PR91](https://github.com/halo-box/strix-llama.cpp/pull/91) is HIP/CUDA-source code but changes 17 coupled files plus operator tests. Its WMMA f16 GDN is explicitly *not bit-identical*; conv fusion needs graph lifetime changes. The pinned tree already calls `qwen4exp_ple_prefetch` and has a tiled GDN, F32 PLE fusion and `idx-relu-sum`; it lacks PR91's chunk path and `qsa-prefill.cu`. The generic HIP top-k is not PR91's scorer/top-k implementation. | Existing PLE prefetch is not double-ported. The remaining coupled kernels need a separately rebuilt binary and quant-specific operator, long-context, hash and probability qualification; the current runtime hash gate rejects an unqualified replacement. |
| PROJFIX grammar / scheduler / MTP | Pinned `common/sampling.cpp` already samples a single token then checks grammar with full-vocabulary fallback. It explicitly asserts that grammar/reasoning-budget samplers are unsupported with backend sampling; merely enabling that path would be wrong. A reversible **source-only** `backend-grammar-fast-optin.patch` now guards the eager/trigger-free/no-reasoning case and fails closed without full raw logits. `set_sampler` still marks scheduler reservation when attaching a new chain, but reusing it across request-owned sampler lifetimes needs graph-identity and pointer-lifetime work. Patch 0002 already keeps speculative checkpoints on device; patch 0007's adaptive policy measured negative. | The grammar patch is not built or promoted. The [verified changelog](https://github.com/AIdevsmartdata/strixhalo-verified/blob/main/CHANGELOG.md) is based on a different Vulkan graph. Its Windows streaming CPU-read path is disabled upstream. No Vulkan-to-HIP transplant or HGN weight migration. |

The common `reddit_bench.py` uses the same deterministic prompt bytes, tokenizer
artifact and output caps for all three backends: target-text PP512/2048/8192/16384,
serial/speculative TG128 where the selected profile supports them, a real three-
turn coding/tool-style exchange, and 8K/32K/64K occupied-context probes (131K
optional). Actual server token counts, not the PP label, are authoritative:
chat framing can differ. Every request records Windows wall time, exposed engine
phases, SHA-256 hashes, draft acceptance when reported and sampled minimum
physical/commit headroom. One profile/run ID is accepted at a time; no harness
command starts or switches an engine.

`quality_gate.py` adds arithmetic, German, Cyrillic, exact JSON and tool-like
JSON, AST-constrained executable Python unit checks, 8K/16K needle retrieval,
five repeated requests interleaved with distractors, multi-turn recall and
strict same-backend candidate/control hashes. If the endpoint returns actual
token-level top-5 logprobs, aligned shared candidates are compared with a
configured absolute logprob tolerance. Missing or rejected logprobs are
reported as unavailable, **not** assumed equivalent. Generated code is AST
restricted and run with isolated Python flags and a timeout; this is a bounded
local evaluation, not a security sandbox for arbitrary untrusted programs.

Fresh source-only regression on 2 October: server 47/47, benchmark 53/53,
PROJFIX 25/25, GUFO wrapper 20/20, Halogen 96 passed/19 skipped. Three pinned
GUFO CPU tests (`config`, `ngram`, `prompt_lookup`) also passed separately.
The prior old Halogen descendant
test failure remains outside these selected suites. Neither the model-quality
gate nor matched live engine benchmarks were run after this code change. Follow
`server/.local/NEXT_STEPS.json` for exact profiles, commands, sequential
restarts and rollback; a passing source test is not model qualification.
The managed Halogen state was observed READY at the start of this continuation
and STOPPED later during source work; no backend was switched for these tests.
The separate [implementation ledger](implementation-ledger-20261002.md) and
[GUFO upstream review](gufo-upstream-review-20261002.md) record additional
reversible source-only candidates and their different validation boundaries.
