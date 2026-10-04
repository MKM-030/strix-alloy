# Halogen 0.16.2 persisted matmul plan: rejected

A fresh machine-specific hipBLASLt plan did not improve the matched 8K workload.
The frozen run also changed deterministic decode outputs, so it fails the
existing output-parity gate. Stock defaults remain selected.

| Exact 8192 input, stock depth 2 | Stock control | Frozen trained plan |
| --- | ---: | ---: |
| Separate serial PP8192 / TG1, tok/s | 1731.31 ± 3.91 | 1716.62 ± 18.11 |
| MTP TG128, tok/s | 46.59 ± 0.08 | 44.48 ± 0.44 |
| Serial TG128, tok/s | 35.78 ± 0.42 | 35.26 ± 0.60 |
| MTP acceptance | 60.00% | 55.00% |

Both runs use v2, 262144 capacity, cache Off, temperature 0, seed 1 and thinking
disabled. Each of the three cells has one excluded warmup and three measured
repetitions: twelve recorded requests and nine measured requests per run. These
are calibrated native phase rates, not tokens divided by total request time.
The prefill headline and MTP decode headline come from separate requests.

Frozen prefill is descriptively 0.85% lower and MTP decode 4.54% lower. There was
no stock bookend: the output-parity failure and absence of a useful gain already
prevent promotion. Sequential timings cannot isolate a causal kernel effect.
No broader coding/quality or restart-promotion suite was run for this rejected
candidate. Acceptance counts are 69/115 per stock MTP request and 66/120 per
frozen request. This experiment does not improve drafter accuracy.

## Training and frozen qualification

The opt-in training profile used only `engine.matmul_tuning={"mode":"train"}`.
It selected eight algorithms for unseen buckets and wrote a fresh owned
container-local `/tmp/strix-alloy-matmul.plan`. Training times include additional
GEMMs and are excluded from every throughput comparison above.

All twelve training requests completed. The coordinator then rejected a stale
`active_requests=1` controller snapshot after the client returned. Controller
publication runs on a monitor cadence; backend/run/profile identities and
memory reserve still matched. Normal shutdown and recovery passed, and the
native engine wrote 22 buckets. The original failed coordinator result is
retained. A bounded five-second retry of only the idle counter was added outside
request timing before the frozen run; identity/reserve failures remain fatal.

The extracted file is 1460 bytes, `HGNTUNE3`, 22 buckets, `gfx1151`, 20 WGPs and
hipBLASLt version field 100401. SHA256 is
`9dcfe4789a8a45ed3717f62ce221521606fec5d271f9d648940bf36a42a06d3b`.
Its recorded identity, digest and read-only metadata were checked before
startup and after shutdown. Frozen startup used `ALGOS=1` and a read-only bind at
`/candidate/frozen-matmul.plan`. Both Docker log streams were checked before
readiness; the complete final native log contains no plan-refusal warning.
Read-only metadata is not a proof of effective write ACLs.

Prompt and request hashes match stock for all twelve corresponding requests.
All eight TG128 output hashes differ from stock, including warmups, while the
four TG1 outputs match. Within the frozen run, all repeated outputs match and
MTP/serial outputs agree. This establishes repeatability for this run, not
equivalence to the stock output or general quality.

The frozen coordinator exited 0, the source seal stayed fixed, and owned
controller/backend shutdown, cleanup and recovery passed. Physical and commit
headroom remained above 18 GiB. Exact minima, phase rows, source/image/plan pins,
hash comparisons and raw artifact hashes are in the
[evidence JSON](halogen0162-matmul-20261004.json). Raw training and frozen files
remain under ignored `server/.local/optimization9h-20261004` directories.

The rejected plan is an experimental artifact. No production profile selects
it, and omitting the new tuning object preserves the original environment.
