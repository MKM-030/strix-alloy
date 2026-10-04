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
