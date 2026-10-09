# Halogen 0.17.3 after power recovery: native API observations

The normal server was restarted once after a proven Windows reboot and remains ready/open in its visible PowerShell 5.1 console on port 8840. The user reported re-enabling Performance Mode. No controlled mode comparison or new serving speed gain is established.

**Clock qualification failed.** The following phase rates are unchanged native API observations, not independently qualified physical-time benchmarks or new Reddit-post values. Original measured repetition 2 has MONOTONIC/RAW=1.040758190934 while RAW/QPC=1.000000292045. The unchanged 0.1% clock gate rejected it. The actual native 0.17.3 phase clock producer has not been fully established; a whole-request ratio cannot reconstruct phase-local durations. Acceptance counts do not depend on this time ratio.

The frozen request uses 16,384 actual input tokens: one natural War and Peace prefix, a story task and explicit ThinkingOff framing. It contains no repeated calibration padding. Each request generates 128 ordinary tokens at temperature 0 / seed 1. Cache Off; MTP depth 2 / PLD 3,3; context capacity 262144; prefill chunk and arena both 8192. One excluded warmup plus three measured repetitions. This workload differs from the earlier synthetic 8K calibration and cannot establish a gain over the historical 48.42 tok/s figure.

| Run | Prefill API tok/s | Decode API tok/s | Accepted / drafted | Clock gate |
| --- | ---: | ---: | ---: | --- |
| Warmup, excluded | 1120.036 | 29.767 | 60/133 | Pass |
| 1 | 1856.986 | 40.149 | 60/133 | Pass |
| 2 | 1797.516 | 41.118 | 60/133 | Fail |
| 3 | 1683.691 | 40.871 | 60/133 | Fail |

Measured mean: **1779.40 Prefill API tok/s; 40.71 Decode API tok/s**. Sample SD: 88.06 / 0.50 tok/s. Acceptance **180/399 = 45.11%**, combined API MTP+PLD draft-token accounting; native MTP-only acceptance is not isolated. All four output hashes and counter pairs match.

The initial client stopped after saving repetition 2 because its clock gate failed. Original response, failure, client and receipts remain unchanged. A separate sealed continuation sent only missing repetition 3. No completed request was repeated; there were exactly four completed requests and zero cancellations. Repetition 2 has preserved clock endpoints but no saved client wall/minimum-memory row. Continuous server guards remained active; the final server state reports a lifetime physical minimum above 30 GiB. Measurement entry requires 22/22 GiB, runtime 18/18 GiB; normal startup remains 35 GiB physical / 131 GiB commit.

The latest CPU arithmetic finding was implemented and screened separately with no GPU/NPU access: complete 8192-token / 131072-ID preparation has median elapsed times 0.197425 ms with dynamic signed division and 0.0780625 ms with admitted literal-divisor arithmetic, saving 0.119450 ms. The archived outputs match exactly. This absolute saving does not justify binary attachment or another engine cohort; the server remains on the normal profile. No component time is converted into serving tok/s. The NPU remains disabled.

Official release sources were refreshed at 11:52:15 UTC; no actionable update was found or installed. Models, drivers, BIOS, voltages and global WSL settings were preserved. Own clients and clock probes exited; the server was not restarted after measurement.

[Numeric evidence](halogen0173-performance-recovery-20261009.json) · [CPU component](../research/halogen0173-cpu-id-reciprocal-20261009.md)

Private raw evidence is retained under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/power-recovery-20261009`, including the original failed collection, sealed continuation and final live-identity receipt.
