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
qualified NPU speed or acceptance result. The bounded lookup mmap-advice
ablation is the next direct prefill experiment. The selected-expert
[NPU replay](../research/halogen-npu-top10-20261004.md) remains a partial graph;
no full Halogen MTP, acceptance or GPU speed gain is claimed from it.
