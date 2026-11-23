# Halogen 0.20.7 publisher decode comparison and grouped INT4 verification

The publisher's **74.57 tok/s** is the arithmetic mean of the engine's
Decode rates over ten short greedy prompt shapes. It used the 0.20.7 v2
checkpoint and its new draft head on native Ubuntu, kernel 7.0, 128 GB
of RAM, a 100 GiB TTM limit and about 85 W sustained package power. The
separate publisher measurements report **70.2 tok/s** over eight English
essay prompts and **67.8 tok/s** over two examples explaining a long
document. [Publisher methodology](https://github.com/peonist-ai/halogen-flash-server/blob/dea807d22a638c67553abea876344a8192054a94/docs/performance.md)

Our WSL2 replay of the ten shipped prompts averaged **71.21 API Decode
tok/s** and accepted **4,887/6,021 head drafts (81.17%)**. The per-request
mean of output tokens divided by complete Windows HTTP time was 74.77
tok/s. Those rates use different clocks and intervals. The replay used
Cache Off and its API phase times exceeded the complete Windows intervals.
[Local replay](halogen0207-publisher-replay-20261123.md) ·
[Phase clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

| Local replay category | Mean API Decode tok/s | Pooled native MTP acceptance | Emitted tokens per native round |
| --- | ---: | ---: | ---: |
| Code | 90.21 | 86.24% | 4.70 |
| Proof | 84.17 | 84.53% | 4.23 |
| Procedure | 67.77 | 80.39% | 2.83 |
| Chat | 54.91 | 74.10% | 2.32 |
| Prose | 59.00 | 77.30% | 2.30 |
| Frozen 8,192-token novel prefix, separate cohort | 57.44 | 65.98% | 2.06 |
| Frozen 16,384-token novel prefix, separate cohort | 55.24 | 64.52% | 1.94 |

Code and proof commit more than four tokens per verification round. The
frozen novel prefixes commit about two. With the 8K round cost and timing
scope observed in the recovery cohort, 74.57 tok/s would take about 2.68
output tokens per round. At unchanged rounds it would instead take about
27.7 ms of API phase time per round versus the observed 36.0 ms. This is
the scale of the required improvement under the two assumptions.
[Frozen novel recovery cohort](halogen0207-performance-after-recovery-20261122.md)

The existing configuration already uses the official r2-HT4 head, greedy
MTP, the native cost policy and the OEM Performance mode. The local
[r2 comparison](halogen0207-official-r2-comparison-20261122.md) found a
slight 8K API Decode increase and longer requests. Prior comparisons
showed [forced prefetch](halogen0207-decode-prefetch-20261123.md) increased
HTTP time, [KV8](halogen0207-kv8-natural-8k16k-20261123.md) changed the
output, and [sampled top-k-one](halogen0207-top-k-one-mtp-20261123.md)
reduced acceptance and throughput. The saved 8K counts give aggregate
acceptance. Third-draft acceptance remains unmeasured. The publisher's fixed-depth
notes describe slower prose at depth three. [MTP options](https://github.com/peonist-ai/halogen-flash-server/blob/bfe1cee6117579a9876784bfea1ffdc79c902e27/docs/FLAGS.md#L188-L191)

## Two-row INT4 group experiment

The pinned engine has grouped routed-INT4 GPU kernels for short
verification batches. The experiment passes `HALOGEN_I4R_DEC_GROUP=2`
through the managed profile. It lets two rows with the same routed
expert reuse INT4 weight traffic. The engine has a separate four-row
grouping choice for batches of six rows and above. The two-row kernels
also use more registers and local GPU memory. The expected benefit
depends on expert overlap and the cost of making grouped work items.

Each arm uses one 32K BF16 slot, the exact 8,192- and 16,384-token inputs,
128 output tokens, cache off, Thinking Off, temperature 0 and seed 1.
Each size has an excluded warmup and three measured requests in each of
the stock, group-2 and stock windows. The experiment records complete
Windows HTTP time, native timings and MTP counts, and compares exact
output bytes. Live container settings and engine logs establish the
configuration. Kernel-level dispatch remains outside this measurement.

| Actual input | Arm | API Prefill tok/s | API Decode tok/s | Native MTP accepted/drafted | Mean full HTTP |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | Stock before | 1,972.10 | 54.87 | 192/291 (65.98%) | 6.284 s |
| 8,192 | Group 2 | 1,953.37 | 55.90 | 192/291 (65.98%) | 6.352 s |
| 8,192 | Stock after | 1,965.14 | 55.71 | 192/291 (65.98%) | 6.315 s |
| 16,384 | Stock before | 2,003.22 | 54.88 | 180/279 (64.52%) | 10.509 s |
| 16,384 | Group 2 | 1,993.78 | 52.92 | 180/279 (64.52%) | 10.553 s |
| 16,384 | Stock after | 1,998.58 | 54.80 | 180/279 (64.52%) | 10.531 s |

All 24 outputs matched the frozen 128-token reference for their input
size. Native MTP rounds and accepted/drafted counts also matched across
arms. Prompt lookup and grammar drafting recorded zero drafts. Group 2
increased complete HTTP time by **0.59–1.08% at 8K** and **0.21–0.41% at
16K** against the two stock windows. The slightly higher 8K API Decode
rate came with slower end-to-end delivery. The grouped setting remains
an opt-in trial and the normal profile uses stock settings.

The API phase sums exceeded their Windows HTTP intervals in 10 of
18 measured requests. Full HTTP supplies the timing comparison and
the API phase rates retain their native scope. The minimum physical or
commit reserve sampled during requests was 29.08 GiB. The gated lifecycle
restored the normal 0.20.7 server on port 8840. The gateway, ServiceNow
router, Native Voice, TTS and ASR all passed their readiness checks.

The raw responses, independent Windows QPC request boundaries and
per-arm container settings are retained under
`server/.local/halogen-update-20261122/primary0207/i4r-dec-group-prep-v1/group2-run-v1`.

| Local artifact | SHA-256 |
| --- | --- |
| Completed campaign handle | `c350108e0a940ff3282280387589ed8eae5b741648e2b0c8e909c62b075dd8fe` |
| Independent replay of the raw responses | `02219534ea58d11a269e6e346abdd8abd43972819e38a208a69050e192deccb8` |
| Candidate container and native log evidence | `76cd340e6adb27e20041f12999e238e9aacc7092c19dc79662d5ce8079e7c6b1` |
| Restored service readiness | `6f4afed0ac1d6e8df21e5fe8c80787758819e73223625eccb91e0264bfaafa71` |
