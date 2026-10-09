# Halogen 0.17.3: qualified natural 16K after power recovery

The corrected phase measurement is fully qualified. The model remains ready on gateway port 8840 in its visible PowerShell 5.1 console. No serving acceleration is claimed from the measurement correction. The slower scratch-free GPU candidate and NPU paths remain disabled.

| Run | Prefill tok/s | MTP+PLD decode tok/s | Accepted / drafted |
| --- | ---: | ---: | ---: |
| Warmup, excluded | 1196.23 | 36.48 | 60 / 133 |
| 1 | 1841.20 | 44.73 | 60 / 133 |
| 2 | 1833.84 | 39.93 | 60 / 133 |
| 3 | 1826.05 | 44.48 | 60 / 133 |
| Measured mean | **1833.70** | **43.05** | **180 / 399 = 45.11%** |

All three measured runs are included, including the slower second Decode run. Sample SD is 7.58 Prefill and 2.70 Decode tok/s. Acceptance is combined API MTP+PLD draft-token accounting; MTP-only acceptance was not isolated. This is a natural-story workload and is not the earlier synthetic 8K calibration that produced the historical 48.42 tok/s result.

Each request contains exactly 16384 actual input tokens: a single War and Peace prefix, a story task, and explicit Thinking Off framing. There is no repeated padding. Each generates 128 ordinary tokens at temperature 0 / seed 1. Cache Off, MTP depth 2 / PLD 3,3, context capacity 262144, prefill chunk and arena both 8192. One excluded warmup plus three measured requests completed without cancellation or retry. Every output SHA256 and draft counter pair matches the frozen baseline.

The first live duration adapter incorrectly required the same request object pointer at Decode start and end. Halogen moves that request from stack to heap. The corrected adapter uses an unambiguous active signed request ID and verifies the exact native start timestamp, preserved by the pinned move operations. Prefill retains its original object/thread/stack requirements. Real starts and scheduling/progress clocks are unchanged; selected reporting ends return native start plus the directly measured RAW elapsed time. This is a reporting correction, with instrumentation overhead, not a speed optimization.

Runtime evidence contains 16 phase records, eight completely consumed phase pairs and four moved Decode objects, bound to native D request IDs 3–6 and the four responses in order. All status values are zero. Every RAW phase delta equals the translated reporting duration; stored Prefill values, token counts and native D rounding agree. The exact post-ready arm marker device/inode, current backend/API identities and complete journal snapshots are bound. All four whole-request RAW/QPC observations independently pass the original 0.1% check. No whole-request ratio was used to rescale phase rates.

Startup admission remained 35 GiB physical / 131 GiB commit; request entry required 22/22 GiB and runtime guard 18/18 GiB. Fresh GPU/process checks found no League/Riot or other GPU counter above the declared threshold before the series. The user reported re-enabling Performance Mode; no controlled mode comparison was performed. Models, drivers, BIOS, voltages and global WSL settings were preserved.

The [first adapter cohort](halogen0173-phase-pairing-v1-rejected-20261009.md) remains rejected and unchanged. The independent [GPU component](../research/halogen0173-scratchfree-moe-20261009.md) was exact but 13.31% slower by mean latency; it was never substituted into serving and was not repeated during the corrected cohort. There is no new NPU tok/s gain or NPU-on/off serving measurement.

[Numeric evidence and hashes](halogen0173-natural16k-raw-20261009.json) · [Source and ownership proof](../../scripts/benchmarks/experimental/halogen0173_phase_clock/README.md).

Private raw responses, clock endpoints, memory frames, native journals, root qualification and lifecycle handles remain under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/phase-clock-real16k-v2-20261009`. Own cohort/clock-probe processes exited; the ready server remains open and is not restarted after this measurement.
