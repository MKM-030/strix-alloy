# GUFO: two simultaneous small sessions on Windows

28 September 2026. **Two native GUFO sessions completed successfully, with real width-2 batching and identical answers to the single-session reference.** One measured pair, not a repeated performance distribution or a long-context capacity test.

Same IQ4_XS Flash Next weights, shared Q8_0 MTP sidecar, draft 3/min 1/full vocabulary/length policy, greedy seed 42, thinking off, prompt-cache bypass. Two 4,096-token session capacities share one model. Actual inputs are only 31 and 24 tokens, not two filled 4K contexts. Each output allowance is 1,024 tokens; both finish naturally.

| Measurement | Single session, sequential requests (27 Sept) | Two simultaneous requests (28 Sept) |
|---|---:|---:|
| Code: native decode, 376 output tokens | 51.79 tok/s | 32.60 tok/s |
| Proof: native decode, 703 output tokens | 51.62 tok/s | 39.08 tok/s |
| Both answers: first submit to last finish | 21.797 s | 18.656 s |
| Both answers: total output / whole group interval | 49.50 tok/s | **57.84 tok/s** |

For this exact pair, whole-group throughput increased **16.84%**. Individual responses got slower: code HTTP time rose from 7.719 to 12.187 seconds and proof from 14.062 to 18.656 seconds. Parallelism helps aggregate work here, not individual latency. This is one sequential baseline and one parallel pair, without randomization/repetitions; do not generalize the percentage to all prompts.

The 57.84 figure is **not pure aggregate decode**: it includes prefill, scheduling and unequal tails. It uses 1,079 native output tokens divided by the common 18.656-second group interval. Fixed-window aggregate decode is unavailable; individual rates are not added and streamed text chunks are not treated as token counts. Earlier [standard PP2048/8192](gufo-pp-20260927.md) measurements remain separate and were not repeated here.

Both native reports give `requested_logical_concurrency=2`, `physical_execution_width=2`, `execution_plan=batched-w2`, and the HTTP requests overlap. Width is the request's peak observed execution width, not proof that every decode cycle or both unequal tails stayed batched. MTP acceptance was 245/269 (91.08%) for code and 477/532 (89.66%) for proof. Both prompts and visible answers match the C1 reference exactly, with 376/703 output tokens and `finish_reason=stop`. The code and proof remain correct by inspection; generated code was not executed. This does not resolve the separate RAID-answer correctness failure or qualify general model quality.

## Memory and shutdown

- Fresh eleven-frame baseline minimum: **49.175 GiB Windows physical memory available**.
- Minimum during model load/inference: **42.726 GiB available**.
- Sampled adapter-wide GPU committed peak: **67.895 GiB / 72.902 decimal GB**; shared peak **4.556 GiB**, already part of adapter usage, not extra memory to add.
- Engine's load-complete device-use report: **67,933 MiB / 66.341 GiB**, a different counter/scope from the adapter peak.
- Minimum system commit headroom during load/inference: **137.476 GiB**.
- Owned exit 0; all 66 telemetry queries completed; cleanup and memory recovery confirmed. The new run's incomplete latch was removed by normal successful cleanup. Historical failed-run latches and records are preserved.

These are sampled peaks/lower bounds on true instantaneous maxima. Different host baselines and session occupancy prevent interpreting them as an isolated GUFO/Halogen capacity comparison. This small-session run did not measure 2x260k; the subsequent [separate no-snapshot 2x260k experiment](gufo-no-snapshot-260k-20260928.md) did.

## Admission correction and provenance

At the user's request, the private run lowered the prior 50 GiB **start requirement** to 49 GiB. It is not 49 GiB reserved forever: `49 - 4 host allowance - 20 shared allowance - 1 desktop-variation reserve = 24 GiB` predicted physical headroom. The runtime physical stop floor stays 24 GiB. Commit admission stays 91 GiB: `91 - 77 model/host commitment - 2 desktop reserve = 12 GiB`. No BIOS, carve, driver, services, pagefile or persistent system setting changed. The prior failed attempts are documented in [the complete-answer report](gufo-complete-small-parallel-20260927.md).

Raw run: `C:\Projects\strix-alloy-research\reports\small-c2-49-20260928-v1-runs\20260928T065810Z-385d45173c3e417c9143b8153a9e6ed8`.

Result SHA256: `E74A933449429E7D4F580464A923820BB8CC7F8BA6FA5EC9BDC4ABED31F420CE`. The manifest records exact argv, workload, source/model/sidecar/runtime identities, review bindings and historical disposition. Native GUFO source `cff564964e8506c0abb3e530cecb55332187ac6c`, executable `E7F5B899C54C747EE5038C0598016394D2A70F25EE69AFBB1E02859FD223D943`, TheRock 10.2/gfx1151. Independent audit: `C:\Projects\strix-alloy-research\reports\small-c2-49-audit-20260928.md`.

This one-use research run is complete; do not replay its consumed admission adapter. It is not a persistent service/installer release. No publication or push was performed.
