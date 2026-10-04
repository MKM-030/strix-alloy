# Halogen optimization window — 4 October 2026

The nine-hour optimization remains active until 08:39:15 UTC (10:39:15 Berlin).
The first completed step reproduces the earlier 8K stock workload. It confirms
that the later 32K sampled-conversation rates did not establish a regression
of that 8K test. No new optimization is promoted by this control.

| Stock control, exact 8192 input | Prefill tok/s | Decode tok/s | MTP acceptance |
| --- | ---: | ---: | ---: |
| Earlier late stock, PP-only / MTP TG128 | 1714.94 ± 17.55 | 47.06 ± 0.60 | 60.00% |
| Fresh control, PP-only / MTP TG128 | 1731.31 ± 3.91 | 46.59 ± 0.08 | 60.00% |

Each fresh cell has one excluded warmup and three measured repetitions.
The prefill column is a separate one-output-token serial request, while decode
is from 128-output-token MTP requests. Serial TG128 measures 35.78 ± 0.42 tok/s.
The profile has 262144 capacity, v2 weights, cache Off and stock depth 2.
Requests are greedy (temperature 0), seed 1, with thinking disabled.
All twelve corresponding prompt/request/output hashes match the earlier
stock control, including warmups. The first MTP warmup was slower and remains
in the raw evidence; it is excluded under the unchanged warmup rule.

The current cold client differs from the old measured revision only by commit
`2bb5642`'s bounded mutable-state read retries. Those reads occur outside the
per-request wall interval. Request construction, sampling, iteration order and
rate arithmetic are unchanged. Both source hashes are retained. The current
source seal remained fixed for the complete lifecycle. The sequential comparison
is descriptive and does not prove a new tuning gain or its cause.

The 18-GiB physical/commit reserve held. Owned controller/backend shutdown,
cleanup and recovery passed. Numeric minima, all phase rows and nine raw artifact
hashes are retained in the [evidence JSON](halogen9h-optimization-20261004.json).
Original artifacts are under ignored
`server/.local/optimization9h-20261004/stock8k-c`.

The [32K sampled gather experiment](halogen0162-gather-20261004.md) has a
different prompt and conversation mix; its 1087.22/40.74 rates and 83.86%
acceptance are not substitutes for the 8K row above.

The [persistent local hipBLASLt plan](halogen0162-matmul-20261004.md) was rejected:
the frozen 8K run measured 1716.62 prefill / 44.48 MTP decode / 55% acceptance
and changed deterministic decode outputs. Training times are excluded.
The tiny NPU variable-matrix probe also failed its numerical gate; it adds no
qualified NPU speed or acceptance result. The bounded lookup
[mmap-advice ablation](halogen0162-mmap-advice-20261004.md) was rejected after
the first candidate request crossed the 18-GiB physical reserve; it completed
zero requests and has no throughput result. Owned shutdown and memory recovery
passed, with the retained failure lock subsequently retired after identity and
terminal-state verification. The selected-expert
[NPU replay](../research/halogen-npu-top10-20261004.md) remains a partial graph;
no full Halogen MTP, acceptance or GPU speed gain is claimed from it.

## Status at 02:10 UTC / 04:10 Berlin

The matched stock result remains 1731.31 prefill / 46.59 MTP decode / 60%
acceptance. Relative to the earlier 1714.94 / 47.06 control, the descriptive
changes are +0.95% prefill and -1.00% decode. No new overall speed or acceptance
improvement has been qualified during this window.

These are separate PP8192/TG1 and TG128 phase measurements on a greedy story
request, not throughput for an arbitrary conversation. The 32K sampled article
workload uses a different prompt, thinking policy, output lengths and cache
opportunities. Its 1087.22 / 40.74 / 83.86% values cannot establish a regression
or improvement against the 8K control. Acceptance means accepted draft tokens
divided by proposed draft tokens; higher acceptance alone does not imply faster
decode when draft depth and computation change.

The first high/residual NPU projection passed precision but took 1.17655 ms
versus 0.70204 ms on CPU at tiny geometry. The extended tiny expert still failed
precision and was not promoted. A subsequent guarded
[full-width runtime expert probe](../research/halogen-npu-v2-dynamic-20261004.md)
using actual v2 weights passed all twelve calls and strict ORT provider
attribution. Its mean host call was 126.94446 ms versus 114.60971 ms on CPU in
the same window; repeated transfer of 187.5 MiB of runtime weights is not a
useful live decode path. This is an expert subgraph, not full MTP.

The latest E-backed loop formatting attempt failed before any lookup payload
extraction. It retained 40.256 GiB physical and 198.685 GiB commit headroom.
Its receipt and fresh namespace queries confirm the owned mount, loop and
worker are absent. Direct E placement is supported by the existing validator
and is being prepared as the next bounded storage experiment.

## Status at 03:00 UTC / 05:00 Berlin

No new end-to-end speed or acceptance improvement has been qualified. The
matched comparison remains 1731.31 PP8192-only / 46.59 MTP TG128 tok/s / 60%
acceptance. The 1087.22 / 40.74 / 83.86% sampled 32K conversation result remains
a different workload. The work so far consists of measured comparisons,
rejected tuning candidates, NPU subgraphs and live-interface implementation;
full NPU MTP is unfinished.

A new root-owned [routing tap](../research/halogen-mtp-routing-live-20261004.md)
captured 73 complete speculative MTP MLP calls
with the unchanged stock output hash. They used 215 different experts among
730 slots. Consecutive calls shared 1.2083 experts on average out of ten. A
64-expert resident set selected using only the first half of the trace covered
45.68% of expert slots and zero complete calls in the second half. This small
trace does not support a tiny whole-call static-set cache. Capture timing is
intrusive and supplies no throughput claim. Original shutdown and memory
recovery passed; minimum physical/commit headroom was 22.6227 / 113.9947 GiB.
Artifacts are retained under
`server/.local/optimization9h-20261004/mtp-route-capture-353f04fbb6cf42cb8a4f9030aa4eafc9`.

The FP32 constant-bank NPU attempt executed zero NPU calls because strict
provider placement failed. Read-only BF16 rounding changes 95,746,308 of
98,304,000 weights and fails the strict CPU reference gate. This rules out the
qualified lossless-conversion path; it does not measure live drafting quality
or NPU performance for an approximate BF16 model.

The direct-E diagnostic extraction stopped after 503,316,480 payload bytes
without a canonical extraction receipt. Its observer last read a fresh frame
in about 21 ms. At refusal, its diagnostic stage was `sleep` for over two seconds
and its stack pointed into `Event.wait`; this does not distinguish waiting,
GIL reacquisition or OS scheduling, or establish heartbeat-file transport
staleness. All owned processes are terminal, reserve held, and the partial
output remains unqualified. No SSD speed result is claimed.

## Status at 03:39 UTC / 05:39 Berlin

No new end-to-end speed or acceptance improvement is qualified. The unchanged
matched stock result remains 1731.31 PP8192-only / 46.59 MTP TG128 tok/s / 60%
acceptance. Full NPU MTP remains incomplete.

The [live BF16 candidate](../research/halogen-npu-live-bf16-20261004.md)
uses actual captured routes and a 150-MiB resident bank, removing runtime weight
feeds. CPU replay passed its labelled graph/approximation contracts. Strict NPU
provider admission failed before any replay because two Gather nodes remained
outside the compiled expert partition; there are zero NPU calls or NPU timings.
The independent complete-MLP CPU sum also fails the existing approximation gate
for 2 / 1 elements; native intermediate arithmetic is still being diagnosed.

The root-owned [GPU event run](../research/halogen-mtp-event-timing-seam-20261004.md)
captured 73 original MTP MLP calls, with matched stock output and ordinary
cleanup/recovery. Instrumented GPU brackets average .404612 ms (median .390229,
p95 .487068). They include waits and enqueue/observer overhead and are not
exact uninstrumented latency. Earlier NPU subgraphs have not demonstrated a
speed advantage over this native complete MLP.

The [SSD preparation](halogen0162-lookup-direct-20261004.md) finally completed
the full 51.2-GB extraction with verified payload XOR, canonical output hash,
unchanged source identity and terminal owned observer/worker. Physical/commit
headroom minima were 44.058 / 198.347 GiB. Independent full readback and ordinary
lookup-source qualification remain pending; no SSD decode gain is claimed.

The later rank-two row-Gather variant also failed strict provider admission
before any NPU replay. It reuses the exact 150-MiB bank and changes only the
Gather shape/index contract; its CPU replay passes, but no NPU latency exists.
The independent SSD readback is now running under a separate owned supervisor.

At 03:49 UTC, the official Halogen main and newest tag `v0.16.2` still point to
`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`.
[Official tag](https://github.com/peonist-ai/halogen-flash-server/tree/v0.16.2).
The rechecked Adrenalin 26.9.2 note lists installed GPU driver
32.0.32015.2008 and NPU MCDM 32.00.20102.3930. Searches found no indexed official
26.9.3 or 26.10.1 notes; that absence is not a universal release check.
[AMD package contents](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html).
No driver or firmware change was made.

At 03:53 UTC, independent full SSD readback and normal lookup-source
qualification have passed. Complete hash/extent/metadata agree, all owned
reader/observer processes are terminal, and the normal immutable qualification
seal is available. The matched stock A / SSD candidate / stock B matrix is
prepared but has not supplied timings. The stock numbers above remain the
only qualified overall result.

At 04:03 UTC, the matched SSD matrix is running in its first stock cell. Three
of six request samples have been retained. Neither partial rows nor the earlier
unmatched 32K rates establish a placement gain. The root continues to own the
single engine launch; the 18-GiB physical/commit floor remains unchanged.

At 04:20 UTC the full SSD stock A / E: / stock B matrix completed with all
eighteen requests and normal cleanup/recovery. E: measured 901.00 prefill,
38.49 decode and 114.18 normalized three-turn seconds; the second stock control
measured 1033.54 / 40.72 / 104.32 seconds. All cells accepted 2094/2497 drafts
(83.8606%) and retrieved 14/14 fixtures. E: is not promoted: its improvement
against the first stock cell does not survive the warmed stock bookend.
The [placement report](halogen0162-lookup-direct-results-20261004/README.md)
confirms all corresponding request/output/reasoning hashes match. Its native
lookup reads were 22.5/10.1 seconds for stock A, 11.4/9.5 for E: and 11.4/9.7
for stock B. Those observations support retaining the warmed stock comparison;
they do not prove an isolated cause for throughput differences.

The [sampled-depth dispatch audit](../research/halogen-sampled-mtp-depth-20261004.md)
establishes that this sampled workload uses one draft per round regardless of
the startup depth flag. A new directly saved greedy client and depth 2 / 3 / 2
coordinator have been prepared; that is a separate workload, with no timing
result yet. Root also started a stock / paired-DeltaNet / stock 8K window at
04:21 UTC. Neither preparation establishes a speed or acceptance improvement.

## Status at 04:43 UTC / 06:43 Berlin

The latest unchanged stock control is **1605.07 ± 15.65 PP8192-only**, **46.874 ±
0.448 MTP TG128 tok/s**, **36.357 ± 0.093 serial TG128**, and **60% acceptance**
(207/345 measured proposals). The earlier 1731.31 prefill measurement remains
historical. Prefill fell 7.29% and its client wall rose 7.84% even after clock
correction. Matching profile, engine environment and prompt/request/output
hashes do not establish the cause; wrapper support sources changed between
these windows. No thermal, background-load or file-cache cause is proven.

The [paired DeltaNet candidate](../research/halogen-dn-fused-pair-negative-20261004.md)
failed the existing startup arithmetic answer check before readiness. It has
zero benchmark samples; normal cleanup/recovery and unchanged source seals
passed. It is rejected without another run. The separate
[norm-fold audit](../research/halogen-dn-norm-fold-audit-20261004.md) also finds no
distinct saved normalization launch for cache Off or the actual Exact32K
workload, so no norm-fold experiment was launched.

The greedy coding depth 2 / 3 / 2 matrix is now running. It is separate from the
sampled article workload. A new saved
[Light EP admission probe](../research/halogen-npu-light-ep-route-20261004.md)
and bounded owned-process guard are prepared; they have no hardware result yet.
Complete draft-head timing is being prepared separately from the earlier MLP
bracket. No new end-to-end speed or acceptance gain is qualified, and full NPU
MTP remains unfinished.

## Status at 05:06 UTC / 07:06 Berlin

The [greedy depth matrix](halogen0162-greedy-depth-results-20261004/README.md)
has completed. Depth3 measured 45.8395 decode tok/s and 68.3220% acceptance;
the warmed depth2 stock B measured 46.9304 tok/s and 73.9142%. Each cell produced
the same 4509 tokens across six EOS responses, with identical requests, outputs
and reasoning, 14/14 retrieval checks, zero caps and ordinary cleanup/recovery.
Implementation and review answers remain ungraded. Depth3's six-request wall
was 162.1064 seconds versus 159.7677 for stock B, 1.46% slower. The separate
normalized three-turn estimate was also 0.584% slower. Retain depth2; the
earlier apparent improvement against stock A did not survive the second control.

The [Light EP probe](../research/halogen-npu-light-ep-route-20261004.md)
discovered the requested Light NPU device but failed strict session admission:
nodes remained assigned to CPU with CPU fallback disabled. There were zero NPU
calls and no NPU timings. The retained child is terminal, its owned job is
closed, provider unregistration and bootstrap shutdown passed, and minimum
physical/commit headroom was 48.0187 / 202.5903 GiB. Do not repeat this exact
graph under unchanged provider defaults.

A complete native MTP forward event timing run is now root-owned. Its new tap
includes transforms, the entire head block, vocabulary projection, argmax and
the native synchronization/result copy. Wrapper host time is recorded
separately. This instrumented diagnostic supplies neither a new throughput
baseline nor accepted-token latency; its output and timing gates are pending.

The user's historical 1731.31 prefill / 46.59 MTP decode comparison has been
answered directly: latest matched stock is 1605.07 / 46.87, with unchanged 60%
acceptance. The prefill decline is real and unexplained; the lower 32K sampled
conversation rates are a separate workload. No end-to-end speed or acceptance
gain has been qualified during this optimization window. Full NPU MTP remains
unfinished.

At 05:09 UTC, the
[complete count1 MTP forward diagnostic](../research/halogen-mtp-full-head-event-timing-20261004.md)
passed matched request/output and ordinary cleanup/recovery. Seventy-three
single-token GPU brackets averaged 3.323555 ms, median 3.298629 and p95 3.587692;
57 wrappers averaged 3.325287 ms of instrumented host time. Forty-two other-count
forwards were counted but not timed. This is wider than the prior MLP-only
0.404612-ms scope, but does not provide total request MTP cost, exact stock
latency, accepted-token cost or NPU speedup. Minimum physical/commit headroom
was 22.4347 / 113.9627 GiB. The retained coordinator is terminal, exit0.

The [stock wrapper reconstruction](../research/halogen-stock-wrapper-reconstruction-20261004.md)
reproduced both retained manifests and entrypoint bytes exactly. Normalized
controller/PowerShell/Python/container launch arguments and the tracked measured
request path are identical. A rollback of these tracked wrappers would not
isolate an identified changed inference path; the actual prefill-drift cause
remains unproven. The recovered
[QMoEBf format](../research/halogen-npu-light-qmoe-contract-20261004.md)
and [full-head state ABI](../research/halogen-mtp-full-head-state-abi-20261004.md)
are concrete integration prerequisites, not a deployed full NPU draft.
