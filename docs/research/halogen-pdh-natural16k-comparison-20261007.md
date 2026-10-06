# Natural16K comparison with explicit PDH admission — 7 October 2026

The checked-copy serving comparison is **incomplete and rejected**. The retained
stock-before window passed its complete post-warmup PDH epoch. The continuation
recorded a candidate warmup and one measured request, then rejected the candidate
for an unresolved System PID 4 Copy-counter violation. Stock-after was not run.
No candidate speed gain, complete consumer execution, NPU integration or adoption
is qualified. [Sanitized evidence summary](halogen-pdh-natural16k-comparison-20261007.json).

| Window | Measured requests | Prefill tok/s | Decode tok/s | Native acceptance | Admission |
| --- | ---: | ---: | ---: | ---: | --- |
| Stock before, retained complete window | 3 | 1229.044357 | 36.188585 | 186 / 387 = 48.0620% | Passed full PDH epoch |
| Checked-copy candidate, exploratory partial row | 1 of 3 | 1206.149566 | 36.264197 | 62 / 129 = 48.0620% | Rejected; invalid cohort |
| Stock after | 0 | — | — | — | Not run |

The candidate's excluded warmup recorded 658.815588 prefill and 29.297160 decode
tok/s, with 62 accepted of 129 drafted tokens. Its single measured row is retained
for diagnosis; it is not a valid candidate average or a stock/candidate speed
comparison. No percentage speed delta is computed from this incomplete cohort.

The shared request uses exactly 16,384 authored natural-prose input tokens and
128 generated tokens, with 262,144-position capacity, temperature 0, seed 1,
thinking off, prompt cache Off, native MTP depth 2, stock PLD 3,3, and paired
8,192-token prefill chunk and arena. Stock used one excluded warmup followed by
three measured requests. Both retained candidate responses have the same request,
prompt and output hashes as stock, the same 62 / 129 native acceptance per request,
and zero prompt-cache and disk-restore counts. This partial parity does not
replace the missing candidate requests and final stock bookend. These are
separate data from the [historical 8K 48.42 tok/s workload](../benchmarks/halogen0162-pld-stock8k-20261004.md).

## Why admission failed

The policy gates every interval from the acknowledged post-warmup baseline
through the final collection, including idle margins: an unadmitted Copy counter
above 2%, or another engine above 1%, rejects the epoch. System PID 4 has no
whitelist. Candidate raw line 20, sample index 19, recorded **2.0850772653677128%**
on the System PID 4 `Copy#0` counter, above its 2% threshold. The source of that
activity remains unresolved; it is not established as Halogen work or another
application's work. No sample was removed and no unchanged retry was performed.

The candidate coverage receipt reports `passed=false`,
`full_epoch_validation_passed=false`, and a second error,
`closed_before_validated_measurement_end`. It retained no validated measured
request brackets or measured-end marker. The collector preserved 32 samples and
8,137,726 raw bytes, ended through its owned marker with exit code 0, and closed
its owned job. That terminal cleanup succeeded while measurement admission failed.
The valid stock epoch retained 99 samples and 24,560,989 raw bytes, with zero
coverage errors, complete epoch validation, exit code 0 and owned-job closure.

Only the candidate's before-counter receipt exists; its consumer counters begin
at zero. The after-counter read was not reached, and no candidate
`window-result.json` was produced. There is no final hit, gather/RMS/M1 skip,
seed-rewrite or retirement delta, so complete consumer execution cannot be
claimed from activation or the partial response rates.

## Preparation and restoration scope

The original matrix remains failed and unchanged. Its first stock window was
reused only through explicit sealed resume inputs and complete evidence
revalidation. The corrected ready plan uses the actual canonical backend source
hash `0c8266c74f09cdec7fb3acb6287bf21da38f86305dcad7a9bb8783112846be05`;
the correction changes metadata, not the sealed stock compute, request, client,
counter or native collector bytes. The isolated continuation also fixes the
comparison of the frozen original coordinator's control-role pin. Preparation
succeeded before this continuation launched. Neither preparation fix establishes
a throughput benefit.

The continuation ended with exit code 1 and a failed `matrix-result.json`;
`original_ready_open=true` and `recovery_pending=false` confirm restoration.
Its errors retain `Original client input phase contract changed` and
`Benchmark stop accounting contaminated`. The PDH adapter requires six input
callbacks, and the rejected partial epoch ended before that contract was fulfilled;
the error does not establish that source bytes changed. The coordinator did not
reach its post-measurement
accounting update. These errors are preserved without overriding the rejected
measurement or treating the stop-accounting discrepancy as proof of a foreign
request.

The new `final-ready.json` and an independent root verification confirm a fresh,
visible Windows PowerShell 5.1 HistoricalStock server with ConsoleTrace, context
capacity 262,144, authenticated local health HTTP 200, zero active requests,
zero completed/cancelled requests, and the advertised `halogen-v2` alias. The
verification used read-only health/model discovery, with no inference request.
Physical and commit headroom were 25.102 and 117.592 GiB; the entire continuation
retained minima of 24.550 and 116.985 GiB, above both runtime floors. The new
server stays open; the candidate remains disabled. Automation remains paused.
