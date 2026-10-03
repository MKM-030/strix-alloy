# Halogen 0.16.2/v2: occupied 128K and 260K synthetic workloads

Measured 3 October 2026 on the 128 GiB Ryzen AI Max+ 395 / Radeon 8060S Windows 11/WSL2 host, using the final stock compute profile, MTP depth 2, cache Off and one 262144-position slot. No driver, BIOS, firmware or global WSL setting was changed. Measured source commit: `2bb5642f266dae3030ab95b2ca18d033da73be33`.

Each row is **one cold measured request**, with no benchmark warmup, collected over two owned service runs. The backend's ordinary readiness probes precede measurement. Cold means zero prompt-cache reuse; model/OS caches were not globally evicted. Actual input counts include the chat template. Both lengths use the same allocated capacity; these are occupied-input measurements.

| Workload | Actual input / output | Prefill raw / calibrated, tok/s | Decode raw / calibrated, tok/s | Accepted / drafted | Client wall, s |
|---|---:|---:|---:|---:|---:|
| prefill128k | 128,034 / 22 | 1620.70 / 1620.70 | 61.80 / 61.80 | 15 / 16 (93.75%) | 79.82 |
| decode128k | 128,048 / 2,048 | 1389.78 / 1422.45 | 63.88 / 65.38 | 1487 / 1583 (93.94%) | 122.31 |
| prefill260k | 260,028 / 22 | 1368.39 / 1368.54 | 62.30 / 62.31 | 15 / 16 (93.75%) | 191.41 |
| decode260k | 260,042 / 2,048 | 1342.67 / 1351.25 | 64.56 / 64.98 | 1487 / 1583 (93.94%) | 224.72 |

The requests with a 32-token output cap are separate prefill probes; actual early-EOS counts are retained. The 2048-output requests measure whole-answer MTP decode, and their acceptance values should accompany those decode rates. Acceptance is accepted draft tokens divided by drafted tokens; it varies with the requested output.

Raw engine phase rates, calibrated rates and independent Windows request wall time remain separate. Calibration multiplies the engine rate by the observed guest monotonic/raw ratio, checked against Windows QPC over the entire request. A clock-rate change within a request can leave phase uncertainty; this is not a GPU speedup or a TTFT measurement. The JSON retains every ratio and interval.

Per-request sampled minima: **21.77 GiB physical RAM**, **112.99 GiB commit headroom**, sampled every 0.2 seconds. The minimum across both controllers' full-run physical observations was **21.75 GiB**. The 18 GiB physical/commit reserve remained enforced. Both owned controllers exited 0; backend cleanup and memory recovery passed, and both terminal controller states are stopped.

The earlier attempt with the game active was stopped by the memory guard before measurement (17.57 GiB physical minimum). Its guard failure, stopped-engine evidence and recovery remain retained. A subsequent restart was refused by its retained ownership lock, also before measurement. After the user closed the game and authorized retry, the lock was archived only after confirming the exact owner, exited engine/controller, idle ports and successful cleanup/recovery. Neither failed attempt contributes a performance sample.

The first 128K prefill completed correctly but ended naturally after 22 output tokens. Its harness then incorrectly required all 32 requested tokens and stopped normally. That original aggregate remains `passed=false`; the valid retained request, exact counts, source seal and cleanup receipt are preserved separately. The continuation measures the remaining three requests and accepts an early-EOS prefill probe. The new publication verifies all four recordings without rewriting any original aggregate.

## Workload recipe and comparison limits

Use the same synthetic filler as the [earlier published workload](../../backends/halogen-wsl2/docs/benchmarks/parallel260k-20260925.md):

```python
filler = "The unified memory architecture changes how inference engines schedule work across the accelerator and the host processor. "
prefill_prefix = "Start your answer with CONTEXT_CHECK. Summarize the supplied filler in one sentence.\n"
prefill_suffix = "\nStart with CONTEXT_CHECK."
decode_prefix = "Begin with the exact marker STEADY-BASELINE-SESSION-01. Write 150 numbered technical paragraphs about reliable inference sessions; keep writing until the output cap.\n"
# 7111 repetitions for the decimal 128000 target; 14444 for the 260000 target.
```

One user message; temperature 0; thinking disabled; reasoning_effort low; drafter mtp; cache_prompt false; non-streamed response. Use max_tokens 32 for prefill and 2048 for decode. Each input/output count, zero cache reuse, reported finish reason, marker and draft counters is checked. Both prefill probes finish naturally after 22 tokens; both decode requests reach 2048 tokens with a length finish. Prompt and request hashes are retained in [the sanitized JSON](halogen0162-long-context-20261003.json); the 260K prefill hash matches the historical receipt, and the long prompt matches its documented recipe.

The historical 260K reference used Halogen **0.13.8/w4b**, with 790.920 tok/s prefill on the 32-output probe and 64.599 tok/s whole-answer decode. The new results use **0.16.2/v2**, so any difference includes checkpoint and setup changes. The old 66.55 tok/s native 20-second token-window metric was not repeated.

Repeated filler and predictable numbered paragraphs demonstrate request completion and throughput at depth. They do not establish retrieval accuracy, realistic 260K coding quality, repeatability or concurrent-session throughput. These are single observations, distinct from the three-repetition [short-context upgrade results](halogen0162-upgrade-20261003.md).
