# Halogen optimization window — 4 October 2026

**No optimization has delivered a qualified overall gain, and full NPU MTP
remains incomplete**. The latest direct 8K stock control,
without ADLX or MTP observers, measured **1661.02 ± 4.57 PP8192-only**, **47.060 ±
0.556 MTP TG128 tok/s**, and **60% acceptance**. The earlier ADLX-observed control
remains a separate historical receipt. Stock variation has no isolated cause;
this sequential control does not measure ADLX overhead or establish a tuning
gain. The nine-hour hardware optimization window ended at 08:39:15 UTC
(10:39:15 Berlin). Its optimization objective was not achieved; the closeout
below records the final process lifecycle and remaining limits.

| Stock control, exact 8192 input | Prefill tok/s | Decode tok/s | MTP acceptance |
| --- | ---: | ---: | ---: |
| Earlier late stock, PP-only / MTP TG128 | 1714.94 ± 17.55 | 47.06 ± 0.60 | 60.00% |
| Initial window control, PP-only / MTP TG128 | 1731.31 ± 3.91 | 46.59 ± 0.08 | 60.00% |
| Intervening unchanged stock control | 1605.07 ± 15.65 | 46.874 ± 0.448 | 60.00% |
| Earlier stock control with ADLX observation | 1768.47 ± 4.06 | 46.355 ± 0.404 | 60.00% |
| Latest direct stock control without observers | 1661.02 ± 4.57 | 47.060 ± 0.556 | 60.00% |

Each current cell has one excluded warmup and three measured repetitions.
The prefill column is a separate one-output-token serial request, while decode
is from 128-output-token MTP requests. Latest serial TG128 measures
35.942 ± 0.291 tok/s. In the same TG128 requests, MTP prefill measured
1584.50 ± 5.19 tok/s and serial prefill 1615.92 ± 11.95 tok/s.
The profile has 262144 capacity, v2 weights, cache Off and stock depth 2.
Requests are greedy (temperature 0), seed 1, with thinking disabled.
All twelve corresponding prompt/request/output hashes in the latest control
match the earlier stock control, including warmups. The unchanged warmup rule
excludes the first repetition of each cell.

Relative to the initial control, latest calibrated PP-only is 4.060% lower.
Independent client request wall also rises from 4.75530 to 4.95592 seconds
(+4.219%); the decline is therefore visible beyond the phase-rate display.
Raw guest PP changes from 1731.222 to 1522.115 tok/s, while the whole-request
monotonic/raw correction changes from 1.000052 to 1.091313. Calibration offsets
part of that raw-rate decline; it does not explain the independent wall increase.
These are descriptive comparisons of three measured samples per control,
with no isolated cause for the stock variation.

The current cold client differs from the old measured revision only by commit
`2bb5642`'s bounded mutable-state read retries. Those reads occur outside the
per-request wall interval. Request construction, sampling, iteration order and
rate arithmetic are unchanged. Both source hashes are retained. The current
source seal remained fixed for the complete lifecycle. The sequential comparison
is descriptive and does not prove a new tuning gain or its cause.

The 18-GiB physical/commit reserve held. Owned controller/backend shutdown,
cleanup and recovery passed. The latest lifecycle result records unchanged
source seals; its 50 recorded source pins were copied without a new hash loop.
Numeric minima, phase rows and recorded pins are retained in the
[evidence JSON](halogen9h-optimization-20261004.json). Original controls are
retained under ignored `server/.local/optimization9h-20261004/stock8k-c`,
`dn-pair-stock8k-a`, and `adlx-control-stock8k-1`. The latest direct receipt is
`stock8k-final-no-observer-1`.

The published [depth1 coding comparison](halogen0162-greedy-depth1-results-20261004/README.md)
retains depth2: depth1 raises acceptance by 6.001 percentage points but takes
1.857% longer actual wall and 2.757% longer normalized time than warmed stockB.
Its different 32K coding workflow does not replace the 8K control. The separate
QMoEBf `model_root` session-configuration candidate also failed at the first
inference invocation, with the same XRT null-read location. The subsequent
public CAPI session-allocator candidate reaches call 0 using the provider's
CPU-addressable `RMM` allocator, then faults without returning output. Its
early module snapshot cannot attribute this new access violation to XRT.
Details and separate cleanup scopes are in the
[session allocator report](../research/halogen-qmoe-session-allocator-20261004.md).

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

## Stock control completed at 05:32 UTC / 07:32 Berlin

The [ADLX-observed stock control](../research/halogen-stock-adlx-control-20261004.md)
completed twelve requests with nine measured rows, identical historic
prompt/request/output hashes, ordinary cleanup/recovery and unchanged source
seals. PP8192/TG1 measured 1768.4717 ± 4.0632 tok/s; MTP TG128 prefill/decode
measured 1678.9173 ± 7.1358 / 46.3550 ± 0.4039 tok/s. Serial TG128 measured
1762.9222 ± 8.2040 prefill and 35.6829 ± 0.3762 decode. MTP accepted 207/345
proposals (60%). These are means and sample standard deviations across three
measured repetitions per cohort.

The intervening control's PP8192/TG1 guest mono/raw clock ratio was 1.0833332;
this control's ratio was 1.0000147. The corrected rates already account for
those ratios. Host-measured client wall also fell from 5.12831 to 4.65772 seconds
(9.18%), so the rebound is present in actual request wall, not only in native
clock arithmetic. Corrected PP was 10.18% above the intervening control and
2.15% above the initial window control; this sequential stock variation does
not establish an optimization gain, a restart effect or a thermal cause.

QPC-aligned measured PP-only telemetry contained 14 samples: GPU temperature
74–80 °C (mean 76.43), clock 2083–2770 MHz (mean 2664.14), reported GPU power
109–151 W (mean 139.79), and usage 68–100% (mean 94.93%). MTP and serial TG128
each contained 24 samples; their complete request windows reached 88 and
87 °C respectively. VRAM clock was 1000 MHz throughout all 62 measured samples.
The research report retains the complete cohort ranges and means.

Host epoch/QPC anchors averaged 204.63 ms apart, with 220.04 ms maximum gap and
0.810 ms maximum absolute affine consistency residual. The nearest selected
sensor sample was 46.37 ms from a request boundary. GetCurrentGPUMetrics/TimeStamp
spans were 0–1 ms, averaging 0.208 ms over 360 successful samples; they exclude
later sensor getters, output and logger costs. One-hertz sampling, unbracketed
host anchors and unavailable sensor refresh latency limit phase precision.
TG128 telemetry covers prefill and generation together. No guest UTC or raw
ADLX driver timestamp was used for alignment. Earlier workloads have no
comparable GPU sensors, and ADLX overhead was not isolated.

No new end-to-end speed or acceptance gain is qualified. The rejected tuning
candidates remain rejected, depth2 and stock placement remain selected, and
full live NPU MTP is still unfinished.

At 05:46 UTC, guarded [official offline QMoE packing](../research/halogen-qmoe-offline-pack-20261004.md)
passed both actual expert geometries. A streamed, aligned synthetic 512-expert
bank is prepared for strict provider admission. It contains zero experts and
has no NPU inference, acceptance or speed result. Approximate q4c-to-affine
INT4 preparation also passed its one numerical fixture. These prerequisites
do not change the stock numbers or qualify a complete NPU draft.

At 05:59 UTC, the root-owned
[strict Light QMoEBf admission](../research/halogen-qmoe-graph-contract-20261004.md)
failed during its sole session-creation attempt: `com.ryzenai:QMoEBf(-1)` was
not a registered function/op. Graph/header/manifest, source/helper and complete
provider-copy pins validated; the actual Light NPU device was selected with
CPU fallback disabled. There were zero calls, no numerical result and no
kernel attribution. The 1.8323-ms failed-construction host timing is not NPU
latency. Missing operator registration does not establish an unsupported
512-expert/top10 shape; that capability was not tested.

Provider unregistration, DLL-directory closure, WinML bootstrap shutdown and
root-owned job closure passed; the child is terminal, exit1. Child observed
physical/commit minima were 48.146 / 202.802 GiB, while the guard observed
48.172 / 202.824 GiB. This first receipt supplies no fallback or inference result. The stock
baseline remains **1768.47 PP-only / 46.355 MTP decode / 60% acceptance**.
No end-to-end gain is qualified, and full live NPU MTP remains incomplete.

At 06:03 UTC, root's changed candidate explicitly registered custom operators
from the same pinned Light DLL. That resolved the missing-operator gate, but
ORT 1.25.2 then rejected `Unsupported version '27' in custom op 'QMoEBf` during
initialization. It again completed zero calls; the 10.2292-ms host construction
time is not NPU latency. Its profile contains two session events and zero Node
events. This custom-op API compatibility rejection does not test 512/top10
shape support. Both candidate receipts are retained separately in the
[graph report](../research/halogen-qmoe-graph-contract-20261004.md).

The second child's provider unregistration, DLL-directory closure, bootstrap
shutdown and owned-job closure passed, with terminal exit1. Child observed
physical/commit minima were 45.908 / 200.606 GiB; guard minima were
45.930 / 200.627 GiB. No unchanged attempt is proposed. The stock baseline
remains 1768.47 / 46.355 / 60%; no new end-to-end gain or full NPU MTP is
qualified.

## Subsequent ORT 1.29 QMoEBf receipts

Root isolated the existing complete ORT 1.29 package under
`server/.local/optimization9h-20261004/qmoe-ort129-stage-f1e210f85e8e4f609aa66df0b80e5495/`.
Its sealed manifest SHA256 is
`3760ee417baa2ecea0d5c8921f3a80568483a28cd1b24479f9ef4f8b8583216f`:
630 files, 45,280,440 bytes and C API maximum 29. Installed runtimes were not
replaced. Three separate guarded children kept graph, Header, synthetic zero
bank and inference inputs identical while source versions added diagnostic
observability, flushed stages/faulthandler, then per-call stages.

| Receipt under `server/.local/optimization9h-20261004/` | Probe source SHA256 | Guard result SHA256 |
|---|---|---|
| `qmoe-light-admission-73b5e986a34b421ea8a0223b839529a0` | `0c0e0071e8c3953f91df0729c3c86e44c959f8616e1feb392cae95a01c942abc` | `5f2ffd973c15e8b24990577725218e6cb72055f92b0e1cbb69ab244c04ad913c` |
| `qmoe-light-admission-0c46d0d069b044d6a0de52ebd3faa948` | `99dab6096f8813451902520f97b7e1fd04a51319b96b895b39fcbb8ea2bb240a` | `f155a8f28e08ba71a10153bc7bf6d8df602569c0fbfb04890967e0bd1fd025fb` |
| `qmoe-light-admission-b7796faf67894b17a6465a48ff29b1d2` | `a371cea50c0d902af76095cdbd324ced66edd8a013d37f2275abbe9fae18ad7d` | `8764d9cd321ed9bcca0c68f9ad51895372f53fad001f11e9b4ace5531c3cc098` |

The first child has empty stdout/stderr and no child JSON, so its session
and call progress is unknown. The second completes strict session
initialization, reaches `synthetic_admission_calls`, then faulthandler reports
an access violation inside ORT `run_with_ort_values`/`invoke`; its per-call
index and count are unknown. The third additionally flushes
`synthetic_call_0_prepare` and `synthetic_call_0_invoke`, with no returned
marker and no call 1. It proves one attempted host inference invocation and
zero returned calls. Missing counters for the earlier runs remain unknown.

All three exit 3221225477 (`0xC0000005`, Windows access violation). None writes
`admission.json`; each created ORT profile is zero bytes. There is no returned
output, numerical qualification, successful NPU latency or profile attribution.
The guards record `owned_job_closed=true`, `ort_stage_final_verified=true`
for all 630 staged files, and the unchanged 18-GiB physical/commit reserve.
Child provider unregistration, DLL-directory closure and bootstrap shutdown
are unobserved after the hard crash; owned-job closure is observed cleanup.

Runs B and C establish that the historical custom-op API 27 versus 25
initialization rejection is resolved under ORT 1.29. Strict session
initialization completes, while the first inference invocation does not
return. This does not establish successful 512/top10 execution, NPU dispatch,
weight residency, routing, shape/padding or activation correctness. The
Python stack locates the host boundary, not the faulting native instruction
or its cause. At that stage, native fault-address/module collection was being
prepared separately; the subsequent collector receipt is below. No further
unchanged inference run is proposed.

Both earlier registration/API negative receipts remain intact. The stock
baseline stays **1768.47 PP-only / 46.355 MTP decode / 60% acceptance**.
No gain is qualified and full live NPU MTP remains unfinished. This publication
read retained receipts only; no tests, weight payloads or hardware were run.

Exact raw hashes and shared graph/runtime pins are in the
[graph report](../research/halogen-qmoe-graph-contract-20261004.md) and evidence
JSON. These are diagnostic failures, not additional throughput measurements.

## Subsequent native fault-address collection

Root's separate `server/.local/optimization9h-20261004/qmoe-light-admission-d35f5a8b9b034d63a4f58faf0850e933`
uses probe source SHA256
`694febe34066e63aa777978742a37300037c54e8d4f43c32a8147b1c90c846ff`.
Prior source pins and negative receipts remain unchanged. The retained
`native-fault.jsonl` reports the call 0 invocation's access violation:
read of address 0, instruction `0x00007ffbdb7d2186`, arm-time module snapshot
`C:\Windows\System32\xrt_coreutil.dll`, base `0x00007ffbdb6e0000`,
module offset `0xf2186`. This is a captured native fault location, not a
diagnosis of version compatibility, input, packing, device or ownership cause.

Strict session initialization completed and the flushed log reaches
`synthetic_call_0_invoke` without a return or call 1. Session provider inventory
is `["RyzenAILightExecutionProvider", "CPUExecutionProvider"]`; that inventory
alone does not establish CPU fallback or successful NPU placement. The source
retains disabled fallback, but execution attribution remains unavailable.
There is no child `admission.json`, returned output or successful latency;
the created ORT profile is zero bytes. Guard exit is 3221225477, owned job
closure and final 630-file stage verification pass, with the 18-GiB reserve held.
Separate static version/module investigation is ongoing; no cause is claimed.
The stock 1768.47 / 46.355 / 60% control and unfinished full-NPU-MTP status remain
unchanged. This publication read saved receipts only; no artifact hashes were
recomputed and no hardware was launched.

## Separate successful native MTP state metadata receipt

Root's `server/.local/mtp-state-20261004/mtp-state-capture-a04197fc0a0e4e4cbaccec5f956dcf21`
records a successful eight-call count1 metadata capture with unchanged source
pins, stock-output parity, and cleanup/recovery proven. All eight entries
observe L48 kind 1 and scatter flag 0. Selected scopes contain 331 original
kernel launches, 8 FD attention launches, 0 scatter launches and 0 captured raw
host descriptors. Descriptor capture was enabled but its exact scatter
callsite never occurred. Observer HIP calls and device-pointer dereferences
are zero. The five-file trace is 9234 bytes; its recorded `records.json` SHA256
is `c205a7959dc3f329ec1eac78e213ba0de3475fa848fcac6014f97d672b3264f2`.

The first failed pre-engine hash-timeout receipt remains unchanged with zero
samples and its original false cleanup/recovery fields. The positive receipt
qualifies branch/mode and launch metadata for this instrumented cohort, with
unmeasured overhead. FD lifetime/ownership, private state commit/discard,
acceptance and NPU speed remain unqualified. Details are in the
[state observer note](../research/halogen-mtp-state-tap-source-review-20261004.md)
and [full-head ABI note](../research/halogen-mtp-full-head-state-abi-20261004.md).

## Follow-up at 07:00 UTC / 09:00 Berlin

The [static XRT diagnosis](../research/halogen-qmoe-xrt-fault-20261004.md)
identifies the immediate fault as a null object passed to `xrt::bo::size()`.
System32 and DriverStore copies are byte-identical. The four relevant provider
options match AMD's pinned example; no source-backed single runtime change
has been identified. Caller, missing buffer role and upstream cause remain
unknown. No unchanged crash is repeated and real-bank conversion is deferred
until a working runtime admission exists.

The [upstream checkpoint](../research/halogen-update-checkpoint-20261004-0700.md)
still finds the pinned Halogen 0.16.2 and matching AMD Windows driver package.
No engine, driver, firmware or BIOS update was made.

At this checkpoint, a separate root-owned greedy coding comparison was running depth2 / depth1 /
depth2, using the unchanged client and six requests per cell. The exact
32K-input, 64K-capacity, Exact-cache workflow and 18-GiB reserve match the
previous greedy depth matrix. Depth1 was already slower in the short-story
screen; this new run only fills the missing coding comparison. Its results
were pending at this checkpoint and must not replace the historical 8K stock control. No speed
or acceptance gain is qualified at this checkpoint.

## Follow-up at 07:28 UTC / 09:28 Berlin

The direct stock receipt `server/.local/optimization9h-20261004/stock8k-final-no-observer-1`
passed with `error=null`, proven cleanup, unchanged source seal, and terminal
controller/backend state `stopped`. The backend outcome records recovery.
All twelve retained requests preserve corresponding historic prompt, request
and output hashes. Each of the three cells has one excluded warmup and three
measured repetitions; all cache/disk-restore counts and reasoning output are
zero. No ADLX or MTP state/timing observer was enabled; the ordinary stock
preflight/private-registration preload and harness memory monitoring remain.

| Measured cell, n=3 | Prefill tok/s | Decode tok/s | Actual request wall s |
|---|---:|---:|---:|
| PP8192/TG1 serial | 1661.0181 ± 4.5741 | — | 4.9559 ± 0.0144 |
| PP8192/TG128 MTP | 1584.5019 ± 5.1858 | 47.0600 ± 0.5563 | 7.9116 ± 0.0436 |
| PP8192/TG128 serial | 1615.9214 ± 11.9475 | 35.9416 ± 0.2911 | 8.6678 ± 0.0748 |

MTP accepted 207/345 drafts, or 60%. The retained measured-plus-warmup memory
minima were 24,680,947,712 available and 122,965,147,648 commit-headroom bytes.
The controller's lifecycle available minimum was 24,624,709,632 bytes; no
aggregate lifecycle commit minimum is recorded. The 18-GiB floor held. These
host-memory scopes do not measure VRAM peaks. Recorded profile, client,
coordinator, runtime and source-seal pins are copied into the evidence JSON;
only `cold/samples.jsonl` has a saved raw-artifact hash published for this new
receipt. Earlier artifact hashes are not reused for it.

The completed [depth1 report](halogen0162-greedy-depth1-results-20261004/README.md)
is a separate depth2/depth1/depth2 coding matrix. All 18 requests completed with
matched hashes, token counts and retrieval results; coding/review remain
ungraded. Depth1's 6.001-point acceptance increase accompanies 1.857% longer
actual wall, 2.757% longer normalized time and 5.608% lower calibrated decode
than warmed stockB. It is rejected; depth2 remains selected.

No optimization gain is promoted. Full live NPU MTP remains unfinished. At this
checkpoint, the separate `model_root` session-configuration source candidate
had no runtime receipt; its subsequent negative receipt is below. The window
remained active at that checkpoint until 08:39:15 UTC. This publication
read saved metadata only and performed no tests, rehash loops or hardware runs.

## Subsequent `model_root` session-configuration candidate failure

The separate receipt
`server/.local/optimization9h-20261004/qmoe-light-admission-35fbd2d784664032ab28cd0d4c761ef8`
pins probe source
`f24261d262c1f632f9be67eef6723880ff3e5c86d54583d2f7f1924e4cdc6aa0`
and unchanged guard source
`9610d697f13f62ccbee6a9f621b54ed04a57a0313ba33a649d293010ca3b2eed`.
Root's source review identifies the candidate change as the official OGA v0.14
session option `model_root=str(model_path.parent)` before `SetupProvider`.
Saved stdout independently confirms that exact bank/graph directory as
`qmoe-pack-admission-5306a9a57ecd44d79255fce2cc89378b`.

Strict session initialization completes; call 0 prepare/invoke is flushed,
but there is no return marker or call 1. The native collector again records
access violation `0xc0000005`, read address 0, `RBX=0`, in the arm-time snapshot
of System32 `xrt_coreutil.dll` at offset `0xf2186`. This run's RIP is
`0x00007ffbdb9a2186`, module base `0x00007ffbdb8b0000`; earlier absolute
addresses and source pins remain in their own receipts. The upstream cause
and successful NPU execution attribution remain unresolved.

The child exits 3221225477. The guard proves owned-job closure and final
verification of all 630 staged ORT 1.29 files; it does not record child-finally
cleanup or a broader recovery certificate. Its minima are 43,867,795,456
available and 209,941,692,416 commit-headroom bytes, above the 18-GiB floor.
There is no `admission.json`, returned output or successful latency; the ORT
profile is zero bytes. The session provider list remains inventory only.

This supported configuration candidate did not resolve the fault. No supported
next NPU candidate is currently identified, no large hardware job is active,
and full live NPU MTP remains unfinished. Root publishes the static details in
the [XRT diagnosis](../research/halogen-qmoe-xrt-fault-20261004.md). This update
copied saved metadata and pins without tests, artifact rehashing or hardware.

## Follow-up at 08:23 UTC / 10:23 Berlin

The advertised HOST_ACCESSIBLE allocator candidate stopped before inference
because Light exposes no allocator with that advertised category. A separate
native CAPI candidate obtains a session allocator through OGA's requested
Cpu/device/default key. Its first attempt stopped at an extra returned-name
comparison; ORT source review showed that comparison was not part of OGA's
contract. The corrected candidate logs `RMM`, type0/mem0/CPU-device0, allocates
all three tensors through the session allocator, and reaches call 0. It then
raises an access violation with no output or profile qualification. The early
snapshot's module attribution is unknown. No unchanged crash is repeated;
real-bank conversion remains deferred. The parent proves owned-job closure,
the 18-GiB reserve, and final sealed-stage integrity. Python cleanup after a
ctypes exception does not establish native session cleanup.

No throughput or acceptance measurement replaces the 1661.02 / 47.060 / 60%
stock row. The user's Laya/Jev proposal is evaluated separately in the
[sidecar feasibility note](../research/halogen-laya-jev-sidecar-feasibility-20261004.md).
A target-trained parallel drafter is a plausible research direction; the
published decision models and other Qwen DFlash checkpoints are not ready
native heads for our Flash-Next target. No new model was downloaded or trained.

## Window closeout after 08:39:15 UTC / 10:39:15 Berlin

The agreed hardware-work window has ended. No qualified overall gain or full
native NPU MTP implementation was achieved. Retain stock depth 2 and the
matched 8K control: PP-only 1661.0181 tok/s, MTP decode 47.0600 tok/s and
acceptance 60%. These are separate PP/TG cohorts, not cold 128K/260K rates.
The prefill decline remains unisolated, while decode remains approximately 47.

Controller/backend were stopped with zero active controller requests. The
native attempt's Windows PIDs 31052 and 40280 were absent. Root additionally
closed the retained WSL lifetime helper locally after verifying Ubuntu-24.04,
boot ID, PID 703 starttime 397, repository cwd and the exact
`root-mtp-state-wsl-lifetime` command marker. Scoped SIGTERM was followed by
`pid_exists_after:false`, observed at 08:36:29 UTC. This resolves the retained
helper lifecycle; it does not prove that the faulted native helper returned
through allocator/session/provider cleanup. No Remote Desktop Commander was
used for this closure.

The final source comparison found an independent NPU-service contract, but
no documented Flash-Next external-drafter seam in the checked public Halogen
0.16.2 deployment sources. The [Laya/Jev assessment](../research/halogen-laya-jev-sidecar-feasibility-20261004.md)
now records that distinction and GPU/NPU resource contention. Documentation
closeout uses existing receipts and source review; no new hardware run is
claimed. The objective remains incomplete rather than being declared
successful when the time window expires.

## Source-only follow-up after the hardware window

The [separate retained allocator-session candidate](../research/halogen-qmoe-retained-allocator-20261004.md)
now implements OGA's exact 96-byte holder graph with fresh default options
and empty Light provider options. Existing MSVC compiled it with warnings
treated as errors. Graph-byte identity, Python syntax and receipt ABI were
checked; the distinct export was inspected without loading the DLL.
At this source-only checkpoint, runtime attempts and returns were both zero.
The original executed native source and raw receipts remain unchanged.
A scoped wrapper correction stops
sentinel hashes from being emitted after a returned call fails output
validation. This is source/build and evidence-storage progress, not a
throughput gain, first-call repair or completed native NPU MTP. No hardware
work had been restarted after the deadline at that checkpoint. The separately
authorized 09:33 UTC execution below supersedes the runtime-zero state.

## Final heartbeat shutdown at 09:18–09:20 UTC / 11:18–11:20 Berlin

The bounded heartbeat fired after its explicit 08:39:15 UTC deadline. Root
updated automation `halogen-neun-stunden-optimierung-und-zahlenstatus` to
`PAUSED`, preserving its name, prompt, schedule and target thread. The app
confirmed the update, and its saved `automation.toml` independently records
`status = "PAUSED"` with update time `1791105567619` milliseconds since epoch.
No new native measurement was launched.

Current local observations show controller/backend `stopped`, zero controller
requests, no listeners on the owned ports 8731/8840 and no matching owned
Windows Python measurement processes. WSL lists Ubuntu-24.04 as `Stopped`;
it was not restarted for inspection. The live agent inventory contains only
the active root and completed subagents. Main was clean and synchronized
before this final record. The latest code/preparation commit was `6a60c2a`.

At this 09:20 UTC shutdown checkpoint, the full goal remained `blocked`, not
achieved. The retained allocator-session variant was compiled/prepared with
zero native sessions or inference calls, and post-window execution awaited
the human extension. The later authorization and execution are recorded below.
Full Flash-Next NPU MTP and an overall throughput/acceptance gain remain
unproved. The matched stock cells above remain the final measured result;
the 8K PP-only rate must not be presented as the same MTP request's prefill
rate or as a cold 128K/260K measurement.

## Separately authorized retained-allocator attempt at 09:33 UTC

The user's subsequent “freigabe erteilt” authorized the prepared single
synthetic NPU attempt, with at most two calls, a 90-second child limit and
22/18-GiB admission/monitored reserves. This did not renew the nine-hour window
or reactivate its paused heartbeat. Root used local PowerShell and excluded
concurrent engines and measurement processes before launching it once.

The holder and strict execution sessions were created, but the first synthetic
call raised a read access violation. No returned-call marker, validated output,
normal native receipt or usable profile was produced. The child later exited
with `0xC0000409`; the captured AV was `0xC0000005`, with unknown faulting module.
Parent receipts confirm job closure, latch release and final ORT-stage integrity.
Monitored physical/commit headroom minima were 42.617 / 198.352 GiB.

[Detailed execution evidence](../research/halogen-qmoe-retained-allocator-admission-20261004.md)
preserves the failed result separately from the historical source/build receipt.
No unchanged retry or real-bank conversion followed. Full NPU MTP and a speed
or acceptance gain remain unproved. The matched stock 8K results remain
1661.0181 PP-only; the MTP request cohort is 1584.5019 prefill / 47.0600 decode
tok/s with 60% acceptance.
