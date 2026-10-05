# Native WSL lookup placement, regular 8K — 5 October 2026

The native WSL n-gram file placement does not establish a useful gain on this
frozen regular decode workload. It is not adopted for the colleague's current
server. All windows use the original GPU kernels and no NPU substitution.

| Window | Prefill tok/s | MTP decode tok/s | Acceptance | Whole request seconds |
|---|---:|---:|---:|---:|
| stock_before | 1321.262342 | 41.622021 | 60.0% (207/345) | 9.299025 |
| native_lookup | 1316.039681 | 41.899131 | 60.0% (207/345) | 9.332566 |
| stock_after | 1277.138669 | 41.280099 | 60.0% (207/345) | 9.552444 |

Actual input/output are **8192/128 tokens**. Capacity is 262144 positions;
this is not a 128K or 260K occupied-input result. The frozen nonrepetitive prose
request is greedy, seed1, thinking off, cache Off, native MTP depth2, PLD3,3.
Each window has one excluded warmup and three measured requests. Engine rates
are calibrated using the retained WSL monotonic/raw and Windows QPC probes.
Every output has hash `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`, and every measured request
accepts69 of115 draft tokens. The low post-restoration warmup is excluded;
Stock B's first measured sample remains included without post-hoc trimming.

Relative to Stock A, native placement changes mean prefill by
-5.222661 tok/s
(-0.395%) and decode by
+0.277110 tok/s
(+0.666%). Stock A/B mean drift is
44.123673 prefill and
0.341922 decode tok/s.
Native clears none of the three mean guards. At matched repetitions it clears
0/3 prefill, 1/3 decode and 0/3 whole-request guards. These are descriptive
drift checks, not a statistical significance claim. They do not justify a
regular8K decode promotion. Earlier sampled32K article initial-prefill placement
results have a separate workload scope.

The original coordinator completed Stock A and native measurement, then failed
before launching cache advice because its owned child received relative
`wsl.exe`. No advice helper process or fadvise call ran. Ordinary native engine
cleanup and recovery both completed normally. The failed original result is
preserved unchanged. A separately reviewed resume used the absolute Windows
WSL executable and measured only the missing Stock B. It repeated neither
earlier window and made no advice call. The supplemental resume exited0 with
`passed=true`, no errors and `restored_original_open=true`.

Read-only Windows GPU counters cover all requests, including readiness before
warmup and a sample after the last response. Owned loggers exited and closed.
The [counter report](../research/halogen-gpu-counter-cohort-20261005.md) explains
their attribution limits; counters do not identify a power or thermal cause.

The original v2 profile remains ready at `http://127.0.0.1:8840/v1`, with native
MTP, capacity262144, the original installed ROCr, and NPU substitution off.
Measured physical/commit minima are at least
26.835445/
119.478710 GiB, above the18-GiB reserve.
Models, drivers, BIOS, voltages and global WSL settings were preserved.

[Sanitized results and receipt hashes](halogen0162-native-lookup-stock8k-20261005.json)
retain all three samples/window, original failure, successful normal cleanup,
supplemental completion and guards. Raw evidence remains in ignored local
directories. The broader optimization goal remains incomplete; no NPU token
rate or acceptance delta is supplied by this GPU-only cohort.
