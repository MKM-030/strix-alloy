# Halogen 0.16.2 private ROCr Stock8K result — 2026-10-05

The private poll-backoff candidate completed the targeted engine cohort with
**42.39 decode tok/s**, unchanged **60% acceptance (207/345)**, and exact output
parity. Its observed decode gain was **1.42–1.79% over the installed-stock
bookends** and **0.99% over the matching source-built control**. The original
profile and installed runtime were restored; the restored instance was left open.

| Window | Prefill tok/s | Decode tok/s | Accepted / drafted |
|---|---:|---:|---:|
| Installed stock before | 1340.39 | 41.8004 | 207 / 345 |
| Source-built stock | 1312.30 | 41.9759 | 207 / 345 |
| Private candidate | 1356.50 | 42.3920 | 207 / 345 |
| Installed stock after | 1317.77 | 41.6484 | 207 / 345 |

These are arithmetic means of three measured requests, after one warmup per
window. Native phase rates use the retained per-request guest-clock calibration
against Windows QPC. Raw responses, calibration records and matching owned-run
engine-log bounds are preserved; raw log rates are supplemental, uncalibrated
measurements. Acceptance uses the native per-response draft counters.

Candidate raw decode averaged **39.131 tok/s**; its monotonic/raw clock ratio
was approximately **1.083335**, yielding the calibrated 42.392 tok/s. Raw-clock
agreement with QPC was within about 4 parts per million, with 0.646–0.713 ms
handshake uncertainty. Mean Windows whole-request time was **9.0806 s**,
versus 9.2292 s, 9.3163 s and 9.3133 s for stock-before, source-stock and
stock-after. The shorter host request time corroborates the modest observed
benefit. The clock difference's cause is unestablished.

| Candidate versus | Prefill change | Decode change |
|---|---:|---:|
| Installed stock before | +1.20% | +1.42% |
| Source-built stock | +3.37% | +0.99% |
| Installed stock after | +2.94% | +1.79% |

Every request used the frozen 8192-token prose prompt and produced 128 tokens:
temperature 0, seed 1, thinking off, cache off, ordinary greedy MTP2 with
PLD `3,3`, one slot, context capacity 262144. All 16 warmup/measured continuations
shared output SHA-256
`0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`.
Prompt SHA-256 was
`0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`;
normalized request SHA-256 was
`f3da94c411cd865b84c3638b09416e642ca14f3c0777cfbeaef4940bf70a6810`.
No window used the NPU.

The original image digest stayed pinned. `/proc` mapping checks on `flash_serve`
before and after each window verified the actual loaded HSA bytes and the
unchanged engine SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Loaded HSA SHA-256 values were:

- Installed stock, both bookends: `1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5`.
- Source-built stock: `2ba2eafa07cfcedb3754a7708858f2c054bc07c9e4e24fe4820b5340cda95af5`.
- Candidate: `cf1f4447cd92330c6a551042eff1ad95de2df4e276c09dfbfe7a252b5fa89434`.

The singleton lifecycle retained the 18 GiB physical/commit reserve. Request
telemetry minima were **26.082 GiB physical / 118.801 GiB commit headroom**.
Retained backend guard logs stayed above **25.372 / 118.102 GiB**; that broader
scope includes the stock-before process's preceding lifetime. The first three
windows proved owned stop, cleanup and memory recovery. The restoration receipt
shows stock-after ready/idle, completed4/cancelled0, original profile SHA-256
`39faa5d1c98289be76d76a396aafd6ae4fe44cba673e61354a8d63f4540b3de7`,
and the installed HSA runtime. The result has `passed=true`, `errors=[]` and
`restored_original_open=true`.

Separate component replay showed about **99.4% lower idle CPU**, from
1.89–1.98 process CPU cores for source-built stock to 0.0114–0.0120 for the
candidate, with exact BF16 parity. Its single Python-observed async wake was
1363.733 µs versus 174.178 µs. These component observations have their own scope;
the table above provides the engine token measurements.

This is one prompt cohort with three measured repetitions per window. It does
not establish a general speed gain or statistical significance. Candidate
decode remains **12.46% below the historical 48.4236 tok/s**; that earlier rate
was not recovered. No default promotion follows this result.

Evidence: [cohort result](../../server/.local/optimization9h-20261004/rocr-engine-stock8k-33bb30dc863e4d8ea008ee1c47cb9c1a/result.json),
[restoration receipt](../../server/.local/optimization9h-20261004/rocr-engine-stock8k-33bb30dc863e4d8ea008ee1c47cb9c1a/restored-original.json),
[component comparison](../../server/.local/optimization9h-20261004/alloy-rocr-component-16a35be771404bd7a7ac3d1b43526528/patch-comparison.json).
Exact identities, numerical values and receipt hashes are in the
[machine-readable report](halogen0162-rocr-stock8k-20261005.json).
