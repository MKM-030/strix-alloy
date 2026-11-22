# Halogen 0.20.7 official r2 comparison at 8K and 16K

The official r2 draft head raised measured 8K decode from 57.11 to 57.85 tok/s
and native MTP acceptance from 65.98% to 67.01%. Whole-request time rose from
6.172 to 6.179 s at 8K and from 10.368 to 10.401 s at 16K. The existing HT4
profile remains the serving default.

| Actual input tokens | Draft head | Prefill tok/s | Decode tok/s | MTP head accepted/drafted | Mean HTTP time (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | HT4 before | 2,095.09 | 57.11 | 192/291 (65.98%) | 6.172 |
| 8,192 | r2 | 2,076.24 | 57.85 | 195/291 (67.01%) | 6.179 |
| 16,384 | HT4 before | 1,986.34 | 54.10 | 180/279 (64.52%) | 10.368 |
| 16,384 | r2 | 2,047.64 | 53.98 | 174/276 (63.04%) | 10.401 |

The table covers 16 completed HTTP responses on 22 November 2026. Each head
completed one excluded warmup and three measured requests per size. Tests used
identical frozen non-repetitive novel prefixes, Halogen API and engine 0.20.7,
the v2 checkpoint, a single 32,768-position slot and the `REV:N Performance`
power scheme. Both arms used paired 8192 prefill settings, native MTP cost
control, PLD 3,3, temperature 0, seed 1, Thinking Off, Vision Off, and
`prompt_cache_policy=no_store`. Every response had 128 output tokens, zero
reused prompt tokens and an identical output SHA-256 within each input size.
The lowest observed request reserve was 25.29 GiB.

Prefill and decode are arithmetic means of the native API phase rates. Native
head acceptance pools accepted and proposed tokens. Windows QPC measures HTTP
time from dispatch through response EOF. Two HT4 16K phase sums exceeded their
HTTP intervals. The phase rates remain native API observations. Relative to the
first HT4 arm, r2 changed prefill/decode by −0.90%/+1.30% at 8K and
+3.09%/−0.23% at 16K. The full HTTP means rose by 0.10% and 0.31%,
respectively. Each head had one measurement window. Differences between the
two windows limit attribution to the draft head.

## Native activation and incomplete control

The engine logs recorded the 54-tensor HT4 and 36-tensor r2 overlays, identical
cost-calibration fingerprints, automatic concurrency, and zero host bytes in
both copy phases. The second phase reported 66,652,069,248 cumulative device
bytes for HT4 and 66,687,364,672 for r2.

An earlier startup attempt rejected the private backend token before creating a
backend. The second attempt used the backend's 43-character URL-safe token
format and completed all eight r2 responses. The collector then rejected the
8K cohort because it expected native head rounds plus accepted drafts to equal
126 for a 128-token completion. The four saved r2 8K responses each reported
62 rounds and 65 accepted drafts, totaling 127. Offline replay checked all
16 raw responses against their saved samples, including the output bytes,
timings, cache status and draft counters.

The terminal campaign retains the first control and the original validator
error. The second HT4 control never ran. The promotion rule required r2 to
improve whole HTTP time against both controls at each size. The first control
already defeated that requirement at both sizes, so the second control was
omitted. The private candidate shut down, and the standard HT4 server was
restored on port 8840. Authenticated gateway and engine health passed, and the
local router on port 8831 reported healthy.

For a separate complete stock baseline, see the
[post-recovery Performance cohort](halogen0207-performance-after-recovery-20261122.md).

## Reproducibility

Local evidence is under
`server/.local/halogen-update-20261122/primary0207/r2-head-prep-v1`.
The two inputs reuse the frozen requests detailed in the
[post-recovery baseline](halogen0207-performance-after-recovery-20261122.md).

| Evidence | SHA-256 |
| --- | --- |
| `official-r2-comparison-run-v1/handle.json` | `a2a30e66d71079d0ba58967529b5794ac533f7ea2faf16af285be3f01ff78cf3` |
| `official-r2-comparison-run-v2/handle.json` | `fefd463f4d0773bf91220ebcb7230437cedbc49eb2c8b1fe2f26e8118f32c6d0` |
| `official-r2-comparison-run-v2/before/summary.json` | `0c1bbce23285313f3361ff186a6a2b3dbfa66f9e45db235d8f23f56496aa36f2` |
| `official-r2-comparison-run-v2/candidate/handle.json` | `1c7fa0c0d35ca6c07065af832cf7e39fb5f2796ccc5fd22b2f3fc89ad9937aa6` |
| `official-r2-comparison-run-v2/candidate-offline-replay-v1.json` | `7953c2c6954467fadd18e33a87c1bfa4676577a31fd5216fa9f67ca9ca81b3e2` |
| `official-r2-comparison-run-v2/candidate-terminal.json` | `db032501af927be7b097b3716695f7eb1a1adb36065a6d1bf8f8f93c7762d8c3` |
| `official-r2-comparison-run-v2/post-restore-serving-health.json` | `7528f4c3a5ce92eb69064e2b2233ee206a8e608443369818402777fa9a6b7dfa` |

The output SHA-256 values matched at both sizes.

| Actual input tokens | Output SHA-256 |
| ---: | --- |
| 8,192 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` |
| 16,384 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` |
